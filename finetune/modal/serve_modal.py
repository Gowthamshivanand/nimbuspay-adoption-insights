"""Serve the fine-tuned 7B (merged, GGUF q4_k_m) on your own Modal GPU as an Ollama-compatible endpoint for the app.
No Modal shared / per-token endpoints: this is one GPU container running Ollama behind a small bearer-auth proxy.

Endpoints (all except /health need  Authorization: Bearer <NP_SERVE_KEY>):
  GET  /health                 {"ok", "model", "ready"}  (no secrets, no model call)
  GET  /api/tags               Ollama model list
  POST /api/chat               Ollama chat; supports "format": <JSON schema> (the app's FT_JSON_SCHEMA route format)
  POST /v1/chat/completions    OpenAI-compatible chat (response_format json_schema), via Ollama
The model name in a request is always replaced with the served model, so the endpoint can't be used to pull other models.

One-time setup on the Modal account that serves (see finetune/modal/README.md):
  modal secret create nimbuspay-serve-key NP_SERVE_KEY=<long random string>
  the export zip (or its GGUF + Modelfile) in the Volume "gowtham-nimbuspay-models" under NP_SERVE_DIR (default runs/7b-latest)
Deploy / keep warm / stop:
  modal deploy finetune/modal/serve_modal.py                        # L4, scale to zero after NP_SCALEDOWN_S idle (default 300 s)
  modal run finetune/modal/serve_modal.py::keep_warm --n 1          # keep 1 container awake (billed every second) ...
  modal run finetune/modal/serve_modal.py::keep_warm --n 0          # ... and back to scale-to-zero
  modal app stop gowtham-nimbuspay-serve                            # stop everything (redeploy to use again)
  python finetune/modal/remote_check.py --wait 600                  # warm up + latency check from the laptop (stdlib only)
Deploy-time settings (environment variables when you run `modal deploy`): NP_SERVE_GPU=L4|A10, NP_MIN_CONTAINERS=0|1,
NP_SCALEDOWN_S=300, NP_SERVE_DIR=runs/7b-latest, NP_SERVE_MODEL=gowtham-nimbuspay-agent-7b."""
import glob, hmac, json, os, shutil, subprocess, sys, time, zipfile

import modal

APP_NAME = "gowtham-nimbuspay-serve"
VOLUME_NAME = "gowtham-nimbuspay-models"
GPU = os.environ.get("NP_SERVE_GPU", "L4")
if GPU not in ("L4", "A10", "L40S", "A100-40GB", "A100-80GB", "H100"): raise SystemExit("NP_SERVE_GPU must be L4 or A10 (or a bigger GPU)")
MIN_CONTAINERS = int(os.environ.get("NP_MIN_CONTAINERS", "0"))
SCALEDOWN_S = int(os.environ.get("NP_SCALEDOWN_S", "300"))
CORES, MEM_GIB = 2, 12
PRICES = {"L4": 0.000222, "A10": 0.000306, "L40S": 0.000542, "A100-40GB": 0.000583, "A100-80GB": 0.000694, "H100": 0.001097}
RUNTIME_ENV = {"NP_SERVE_MODEL": os.environ.get("NP_SERVE_MODEL", "gowtham-nimbuspay-agent-7b"),
               "NP_SERVE_DIR": os.environ.get("NP_SERVE_DIR", "runs/7b-latest"),
               "OLLAMA_MODELS": "/vol/ollama-models", "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_NUM_PARALLEL": "4",
               "OLLAMA_KEEP_ALIVE": "-1"}

app = modal.App(APP_NAME)
vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = (modal.Image.debian_slim(python_version="3.12")
         .apt_install("curl", "zstd", "ca-certificates", "pciutils")
         .run_commands("curl -fsSL https://ollama.com/install.sh | sh")
         .pip_install("fastapi>=0.110", "httpx>=0.27"))


def hourly_cost(gpu=GPU):
    return round(3600 * (PRICES[gpu] + CORES * 0.0000131 + MEM_GIB * 0.00000222), 2)


def check_bearer(header, key):
    """Constant-time bearer check. No key configured = everything refused (never an open endpoint)."""
    if not key: return False
    want = "Bearer " + key
    return hmac.compare_digest((header or "").encode(), want.encode())


def find_model_files(d):
    """(gguf, modelfile) in d: the GGUF named on the Modelfile's FROM line (the one that was evaluated and shipped),
    unpacking an export zip first if that is what's there."""
    if not os.path.exists(os.path.join(d, "Modelfile")):
        for z in sorted(glob.glob(os.path.join(d, "*.zip"))):
            out = "/tmp/model"; os.makedirs(out, exist_ok=True)
            with zipfile.ZipFile(z) as zf: zf.extractall(out)
            d = out; break
    mf = os.path.join(d, "Modelfile")
    if not os.path.exists(mf): return None, None
    src = next((l.split(None, 1)[1].strip() for l in open(mf, encoding="utf-8") if l.upper().startswith("FROM ")), "")
    g = os.path.normpath(os.path.join(d, src)) if src.startswith(".") else None
    return (g if g and os.path.exists(g) else None), mf


@app.cls(image=image, gpu=GPU, volumes={"/vol": vol}, cpu=CORES, memory=MEM_GIB * 1024, env=RUNTIME_ENV,
         secrets=[modal.Secret.from_name("nimbuspay-serve-key", required_keys=["NP_SERVE_KEY"])],
         min_containers=MIN_CONTAINERS, max_containers=1, scaledown_window=SCALEDOWN_S, timeout=600, startup_timeout=900)
@modal.concurrent(max_inputs=8)
class Serve:
    @modal.enter()
    def start(self):
        t = time.time(); self.model = os.environ["NP_SERVE_MODEL"]; self.ready = False
        self.proc = subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import httpx
        for _ in range(120):
            try: httpx.get("http://127.0.0.1:11434/api/tags", timeout=1); break
            except Exception: time.sleep(0.5)
        names = {m["name"] for m in httpx.get("http://127.0.0.1:11434/api/tags", timeout=5).json().get("models", [])}
        if self.model not in names and self.model + ":latest" not in names:
            gguf, mf = find_model_files(os.path.join("/vol", os.environ["NP_SERVE_DIR"]))
            if not (gguf and mf): raise RuntimeError(f"No GGUF + Modelfile in volume {VOLUME_NAME}:{os.environ['NP_SERVE_DIR']}")
            work = "/tmp/create"; os.makedirs(work, exist_ok=True)
            shutil.copy(mf, os.path.join(work, "Modelfile"))
            os.symlink(gguf, os.path.join(work, os.path.basename(gguf)))
            subprocess.run(["ollama", "create", self.model, "-f", "Modelfile"], cwd=work, check=True)
            vol.commit()                           # next cold start skips the create
        # load the weights into GPU memory now, so the first real question is fast
        body = {"model": self.model, "stream": False, "keep_alive": -1, "options": {"temperature": 0, "num_predict": 8},
                "messages": [{"role": "user", "content": "Role: executive\nQuestion: What is licence utilisation this month?"}]}
        httpx.post("http://127.0.0.1:11434/api/chat", json=body, timeout=600)
        self.ready = True
        print(f"ready in {time.time() - t:.0f}s: {self.model} on {GPU} (about ${hourly_cost()}/h while awake, estimate)", flush=True)

    @modal.exit()
    def stop(self):
        try: self.proc.terminate()
        except Exception: pass

    @modal.asgi_app()
    def web(self):
        import httpx
        from fastapi import FastAPI, Request, HTTPException
        from fastapi.responses import JSONResponse
        api = FastAPI(title="gowtham-nimbuspay-agent-7b"); key = os.environ.get("NP_SERVE_KEY", "")
        client = httpx.AsyncClient(base_url="http://127.0.0.1:11434", timeout=120)

        def auth(req):
            if not check_bearer(req.headers.get("authorization"), key): raise HTTPException(401, "missing or wrong bearer token")

        @api.get("/health")
        async def health(): return {"ok": True, "model": self.model, "ready": self.ready}

        @api.get("/api/tags")
        async def tags(req: Request):
            auth(req); return JSONResponse((await client.get("/api/tags")).json())

        async def forward(path, req):
            auth(req)
            try: body = await req.json()
            except Exception: raise HTTPException(400, "JSON body required")
            if not isinstance(body, dict): raise HTTPException(400, "JSON object required")
            body.update(model=self.model, stream=False)
            if path == "/api/chat": body["keep_alive"] = -1
            r = await client.post(path, json=body)
            return JSONResponse(r.json(), status_code=r.status_code)

        @api.post("/api/chat")
        async def chat(req: Request): return await forward("/api/chat", req)

        @api.post("/v1/chat/completions")
        async def openai_chat(req: Request): return await forward("/v1/chat/completions", req)

        return api


@app.local_entrypoint()
def keep_warm(n: int = 1):
    """Set the number of always-awake containers on the DEPLOYED app (1 during the pitch slot, 0 afterwards)."""
    Serve_ = modal.Cls.from_name(APP_NAME, "Serve")
    Serve_().update_autoscaler(min_containers=n)
    print(f"min_containers = {n}." + (f" One {GPU} container stays awake: about ${hourly_cost()}/h (estimate) until you run keep_warm --n 0 "
                                      f"or `modal app stop {APP_NAME}`." if n else " Scale-to-zero: no cost while idle."))


if __name__ == "__main__":
    print(__doc__)
    print("Cost while awake (estimate from list prices, GPU + 2 cores + 12 GiB): " + ", ".join(f"{g} ${hourly_cost(g)}/h" for g in ("L4", "A10")))
