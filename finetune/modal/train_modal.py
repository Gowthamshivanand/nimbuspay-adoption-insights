"""Train the NimbusPay router on Modal (modal.com) and TEST WHAT YOU SHIP: the exported GGUF files are evaluated in Ollama,
the same runtime as the laptop, and the release decision uses those GGUF numbers (the HF numbers are shown beside them).

Pipeline (one `modal run`, four steps, each billed only while it runs; no Modal shared / per-token endpoints):
  1. train      GPU (A100-80GB for 1.5B, H100 for 7B): bf16 LoRA on the v4 data, full planned epochs with early stopping on
                validation loss every 100 steps (best checkpoint restored), HF eval exactly like Colab (route test incl. fresh
                wording, answers, public eval, hybrid + pure release gate), merge, save merged weights to the Volume.
  2. export     CPU: f16 GGUF + q8_0 (+ q5_k_m / q4_k_m) with llama.cpp, Modelfiles, template / tokenisation parity check
                (HF chat template string == Modelfile TEMPLATE, HF token ids == llama.cpp token ids, BOS / EOS).
  3. gguf_eval  GPU (L4), one container per quant in parallel: Ollama serves the GGUF; chat-vs-raw prompt check; the full
                finetune/eval_finetuned.py --mode both (route test, fresh wording, answers, hybrid + pure gate); agreement with HF.
  4. package    CPU: side-by-side HF vs GGUF table, release decision on the shipped GGUF, zip (shipped GGUF + Modelfile + reports).

  modal run finetune/modal/train_modal.py --smoke                 # CPU-only smoke test (tiny model, 12 steps, ~10-20 min, cents)
  modal run finetune/modal/train_modal.py --model 1.5B            # run 3: full 1.5B on A100-80GB, ships q8_0
  modal run finetune/modal/train_modal.py --model 7B              # 7B on H100, compares q8_0 / q5_k_m / q4_k_m
  options: --gpu H100|A100-80GB  --eval-gpu L4|A10  --quants f16,q8_0,q4_k_m  --ship q8_0  --qlora  --no-use-public
           --push-hf (Modal secret "huggingface" with HF_TOKEN; never stored in the repo)
  python finetune/modal/train_modal.py --estimate                 # time / cost estimates, runs nothing
Download:  modal volume get gowtham-nimbuspay-models runs/1.5b-latest/gowtham-nimbuspay-agent-export.zip .
Auth: run `modal setup` (or `modal token new`) yourself; nothing is hard-coded here."""
import json, os, shutil, subprocess, sys, time

import modal

HERE = os.path.dirname(os.path.abspath(__file__)); FT_DIR = os.path.dirname(HERE); REPO = os.path.dirname(FT_DIR)
APP_NAME = "gowtham-nimbuspay-train"
VOLUME_NAME = "gowtham-nimbuspay-models"
HF_CACHE_VOLUME = "gowtham-nimbuspay-hf-cache"
LLAMA_CPP_SHA = "5aeac37a35b44fde4bdffaec9159f2fcb253b622"      # llama.cpp commit the converter was tested with (18 Oct 2026)
# GPU $/s from modal.com/pricing (19 Oct 2026); must match ft_train.GPU_USD_PER_S (a test checks). CPU $/core/s, RAM $/GiB/s.
PRICES = {"H100": 0.001097, "A100-80GB": 0.000694, "A100-40GB": 0.000583, "L40S": 0.000542, "A10": 0.000306, "L4": 0.000222, "CPU": 0.0}
CPU_S, MEM_S = 0.0000131, 0.00000222
TRAIN_RES, EXPORT_RES, EVAL_RES = (4, 32), (8, 32), (4, 16)       # (cores, GiB) requested per step; billed too
# Per-step timeouts keep the worst case inside the approved $10 total (see README). Training stops itself earlier (budget_min).
DEFAULTS = {"7B": dict(gpu="H100", train_timeout_min=70, budget_min=40, eval_timeout_min=35, quants=["q8_0", "q5_k_m", "q4_k_m"]),
            "1.5B": dict(gpu="A100-80GB", train_timeout_min=45, budget_min=28, eval_timeout_min=20, quants=["f16", "q8_0", "q5_k_m", "q4_k_m"])}
EXPORT_TIMEOUT_MIN, EVAL_TIMEOUT_MIN, SMOKE_TIMEOUT_MIN = 30, 35, 30
# Estimates (NOT measured on Modal yet) per step, minutes. v4 data with the public mix: 10,688 rows, 3.39M tokens per epoch,
# 668 steps per epoch at batch 16, 2 epochs = 1,336 steps.
ESTIMATE = {"1.5B": dict(train=(20, 32), export=(3, 6), eval_each=(6, 12)), "7B": dict(train=(35, 55), export=(12, 20), eval_each=(15, 30))}

app = modal.App(APP_NAME)
models_vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
hf_cache = modal.Volume.from_name(HF_CACHE_VOLUME, create_if_missing=True)

_ignore = ["**/__pycache__/**", "**/*.pyc", "**/*.ipynb", "**/var/**", "**/.pytest_cache/**"]
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "build-essential", "cmake", "curl", "zstd", "ca-certificates", "pciutils")
    .pip_install("torch==2.14.1", "transformers==5.20.1", "peft==0.21.2", "accelerate==1.15.0", "bitsandbytes", "datasets",
                 "huggingface_hub", "safetensors", "sentencepiece", "protobuf", "numpy")
    .run_commands(
        f"mkdir -p /opt/llama.cpp && cd /opt/llama.cpp && git init -q && git remote add origin https://github.com/ggml-org/llama.cpp"
        f" && git fetch -q --depth 1 origin {LLAMA_CPP_SHA} && git checkout -q FETCH_HEAD",
        "pip install -q /opt/llama.cpp/gguf-py",
        "cmake -S /opt/llama.cpp -B /opt/llama.cpp/build -DGGML_CUDA=OFF -DLLAMA_CURL=OFF -DBUILD_SHARED_LIBS=OFF > /dev/null"
        " && cmake --build /opt/llama.cpp/build --target llama-quantize llama-tokenize -j 8 > /dev/null",
        "curl -fsSL https://ollama.com/install.sh | sh",
    )
    .env({"HF_HOME": "/hf", "PYTHONUTF8": "1", "TOKENIZERS_PARALLELISM": "false"})
    .add_local_dir(os.path.join(REPO, "app"), "/repo/app", ignore=_ignore)
    .add_local_dir(FT_DIR, "/repo/finetune", ignore=_ignore + ["modal/**"])
    .add_local_dir(os.path.join(REPO, "tools"), "/repo/tools", ignore=_ignore)
    .add_local_dir(os.path.join(REPO, "tests", "data"), "/repo/tests/data", ignore=_ignore)
    .add_local_dir(os.path.join(REPO, "src"), "/repo/src", ignore=_ignore)
)
VOLS = {"/vol": models_vol, "/hf": hf_cache}


def _T():
    for p in ("/repo", "/repo/finetune", "/repo/tools"):
        if p not in sys.path: sys.path.insert(0, p)
    import ft_train as T
    return T


def _cfg(T, o):
    return T.Config(model_choice=o["model"], qlora=o.get("qlora", False), epochs=o.get("epochs", 2), use_public=o.get("use_public", True),
                    time_budget_min=o.get("budget_min", 30), smoke=o.get("smoke", False), work="/tmp/work", repo_dir="/repo",
                    gpu=o.get("gpu", "CPU")).finalize()


def _rundir(o): return f"/vol/runs/{o['run_name']}"


# ---------- 1. train + HF eval + merge ----------
@app.function(image=image, volumes=VOLS, timeout=3600, cpu=TRAIN_RES[0], memory=TRAIN_RES[1] * 1024)
def train(o: dict) -> dict:
    t0 = time.time(); T = _T(); cfg = _cfg(T, o); vdir = _rundir(o); os.makedirs(vdir, exist_ok=True)
    from dataclasses import asdict
    print("config:", json.dumps({k: v for k, v in asdict(cfg).items() if k != "extra"}), flush=True)
    if shutil.which("nvidia-smi"): T.sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv", check=False)
    import torch
    print("torch", torch.__version__, "cuda build", torch.version.cuda, "cuda available", torch.cuda.is_available(), flush=True)
    if cfg.gpu != "CPU" and not torch.cuda.is_available():     # never train on CPU while paying for a GPU
        raise RuntimeError("GPU container but torch cannot use CUDA (driver / wheel mismatch); stopping before any training")
    train_rows, val_rows, test, public_eval = T.load_data(cfg)
    model, tok, hw = T.load_model(cfg); hf_cache.commit()
    tr = T.train(cfg, model, tok, train_rows, val_rows, hw)
    shutil.copytree(tr["adapter_dir"], f"{vdir}/adapter", dirs_exist_ok=True); models_vol.commit()
    gen = T.make_generator(model, tok)
    meta = dict(base_model=cfg.base_model, qlora=cfg.qlora, epochs=cfg.epochs, train_rows=len(train_rows), use_public=cfg.use_public,
                smoke=cfg.smoke, gpu=cfg.gpu, platform="modal", run_name=o["run_name"], ollama_name=cfg.ollama_name,
                **{k: v for k, v in tr.items() if k not in ("log_history", "adapter_dir")}, log_tail=tr["log_history"])
    rep = T.evaluate(cfg, gen, test, public_eval, meta); preds = rep.pop("_preds")
    json.dump(rep, open(f"{vdir}/eval_report_hf.json", "w"), indent=1, default=str)
    json.dump(dict(ids=[r["id"] for r in test], preds=preds), open(f"{vdir}/hf_preds.json", "w"))
    models_vol.commit()
    merged = T.merge_to_dir(cfg, model, tok, tr["adapter_dir"])
    shutil.copytree(merged, f"{vdir}/merged", dirs_exist_ok=True); models_vol.commit()
    el = time.time() - t0
    return dict(seconds=round(el), gpu=cfg.gpu, cores=TRAIN_RES[0], mem=TRAIN_RES[1], train_minutes=tr["train_minutes"], train_steps=tr["train_steps"],
                planned_steps=tr["planned_steps"], stop_reason=tr["stop_reason"], best_val_loss=tr["best_val_loss"],
                hf_tool_acc=rep["model"]["route"]["tool_acc"], hf_gate_pure=rep["gate_pure_pass"])


# ---------- 2. export GGUFs + template / tokenisation parity ----------
@app.function(image=image, volumes=VOLS, timeout=EXPORT_TIMEOUT_MIN * 60, cpu=EXPORT_RES[0], memory=EXPORT_RES[1] * 1024)
def export(o: dict) -> dict:
    t0 = time.time(); T = _T(); cfg = _cfg(T, o); vdir = _rundir(o)
    from transformers import AutoTokenizer
    quants = sorted(set(o["quants"]) | {o["ship"]})
    files = T.export_ggufs(cfg.ollama_name, f"{vdir}/merged", f"{vdir}/export", "/opt/llama.cpp", quants=quants)
    tok = AutoTokenizer.from_pretrained(f"{vdir}/merged")
    test = [json.loads(l) for l in open("/repo/finetune/data/test.jsonl", encoding="utf-8")]
    rows = [r for r in test if r["task"] == "route"][:4] + [r for r in test if r["task"] == "answer"][:2]
    parity = T.template_parity(tok, rows, files.get(o["ship"]) or files["f16"], "/opt/llama.cpp", n=len(rows))
    json.dump(parity, open(f"{vdir}/template_parity.json", "w"), indent=1, default=str)
    models_vol.commit()
    return dict(seconds=round(time.time() - t0), gpu="CPU", cores=EXPORT_RES[0], mem=EXPORT_RES[1], files={q: os.path.basename(p) for q, p in files.items()},
                sizes_gib={q: round(os.path.getsize(p) / 2 ** 30, 2) for q, p in files.items()}, parity_ok=parity["ok"], parity=parity["checks"])


# ---------- 3. evaluate one GGUF in Ollama (what the laptop / the Modal endpoint actually run) ----------
@app.function(image=image, volumes=VOLS, timeout=EVAL_TIMEOUT_MIN * 60, cpu=EVAL_RES[0], memory=EVAL_RES[1] * 1024)
def gguf_eval(o: dict, quant: str) -> dict:
    import urllib.request
    t0 = time.time(); T = _T(); cfg = _cfg(T, o); vdir = _rundir(o); exp = f"{vdir}/export"
    name = f"{cfg.ollama_name}-{quant.replace('_', '-')}"
    env = dict(os.environ, OLLAMA_MODELS="/tmp/ollama-models", OLLAMA_HOST="127.0.0.1:11434", OLLAMA_NUM_PARALLEL="4", OLLAMA_KEEP_ALIVE="-1")
    srv = subprocess.Popen(["ollama", "serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out = dict(quant=quant, gpu=o.get("eval_gpu", "CPU"))
    try:
        for _ in range(120):
            try: urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1); break
            except Exception: time.sleep(0.5)
        rep = T.eval_gguf_in_ollama(name, exp, quant, f"{vdir}/merged", f"{vdir}/hf_preds.json", f"/tmp/eval_{quant}.json",
                                    repo_dir="/repo", limit=40 if o.get("smoke") else 0, workers=4)
        rep["gguf"] = f"{cfg.ollama_name}-{quant}.gguf"
        json.dump(rep, open(f"{vdir}/eval_report_gguf_{quant}.json", "w"), indent=1, default=str); models_vol.commit()
        out.update(chat_vs_raw=rep["chat_vs_raw"], agreement=rep.get("agreement"), tool_acc=rep.get("model", {}).get("route", {}).get("tool_acc"),
                   gate_pure=(rep.get("pure") or {}).get("gate_pass"), gate_hybrid=(rep.get("hybrid") or {}).get("gate_pass"))
        out.update(ok=True)
    except Exception as e:
        out.update(ok=False, error=f"{type(e).__name__}: {str(e)[:300]}"); print("GGUF eval failed:", out["error"], flush=True)
    finally:
        srv.terminate()
    out.update(seconds=round(time.time() - t0), cores=EVAL_RES[0], mem=EVAL_RES[1])
    return out


# ---------- 4. package: side by side, decision on the GGUF, zip ----------
@app.function(image=image, volumes=VOLS, timeout=20 * 60, cpu=2, memory=8 * 1024)
def package(o: dict, quants: list) -> dict:
    t0 = time.time(); T = _T(); cfg = _cfg(T, o); vdir = _rundir(o)
    hf = json.load(open(f"{vdir}/eval_report_hf.json"))
    gg = {q: json.load(open(f"{vdir}/eval_report_gguf_{q}.json")) for q in quants if os.path.exists(f"{vdir}/eval_report_gguf_{q}.json")}
    if not gg: raise RuntimeError("no GGUF eval reports; nothing to ship")
    ship = T.pick_ship(cfg.model_choice, gg, o["ship"]) if o["ship"] in gg or cfg.model_choice == "7B" else next(iter(gg))
    table = T.side_by_side(hf, gg); T.print_side_by_side(table)
    decision = T.compare_run2(T.gguf_as_report(gg[ship])); decision["decided_on"] = f"GGUF {ship} in Ollama"
    T.print_run2(decision)
    parity = json.load(open(f"{vdir}/template_parity.json")) if os.path.exists(f"{vdir}/template_parity.json") else None
    report = dict(hf, gguf=gg, side_by_side=table, ship_quant=ship, template_parity=parity, decision=decision,
                  gate_pass=(gg[ship].get("hybrid") or {}).get("gate_pass"), gate_pure_pass=(gg[ship].get("pure") or {}).get("gate_pass"),
                  hf_gate_pass=hf.get("gate_pass"), hf_gate_pure_pass=hf.get("gate_pure_pass"), steps=o.get("steps"))
    rp = f"{vdir}/eval_report.json"; json.dump(report, open(rp, "w"), indent=1, default=str)
    exp = f"{vdir}/export"; ship_file = f"{cfg.ollama_name}-{ship}.gguf"
    open(f"/tmp/Modelfile", "w").write(T.modelfile_text(ship_file))
    files = [(f"{exp}/{ship_file}", ship_file), ("/tmp/Modelfile", "Modelfile"), (rp, "eval_report.json"), (f"{vdir}/eval_report_hf.json", "eval_report_hf.json")]
    files += [(f"{vdir}/eval_report_gguf_{q}.json", f"eval_report_gguf_{q}.json") for q in gg]
    if parity: files.append((f"{vdir}/template_parity.json", "template_parity.json"))
    z = T.zip_files(files, f"{vdir}/{cfg.ollama_name}-export.zip")
    latest = f"/vol/runs/{cfg.model_choice.lower()}{'-smoke' if cfg.smoke else ''}-latest"
    os.makedirs(latest, exist_ok=True)
    for f in (z, rp): shutil.copy(f, latest)
    models_vol.commit()
    if o.get("push_hf") and not cfg.smoke and os.environ.get("HF_TOKEN"):
        from huggingface_hub import HfApi
        api = HfApi(token=os.environ["HF_TOKEN"]); mid = f"{api.whoami()['name']}/{cfg.ollama_name}-qwen2.5-{cfg.model_choice.lower()}"
        api.create_repo(mid, exist_ok=True)
        for p, arc in files: api.upload_file(path_or_fileobj=p, path_in_repo=arc, repo_id=mid)
        api.upload_folder(folder_path=f"{vdir}/adapter", repo_id=mid, path_in_repo="lora_adapter"); report["hf_repo"] = mid
    return dict(seconds=round(time.time() - t0), gpu="CPU", cores=2, mem=8, ship=ship, zip=os.path.basename(z), side_by_side=table, decision=decision,
                zip_gib=round(os.path.getsize(z) / 2 ** 30, 2))


def step_cost(r):
    return round(r.get("seconds", 0) * (PRICES.get(r.get("gpu", "CPU"), 0) + r.get("cores", 0) * CPU_S + r.get("mem", 0) * MEM_S), 3)


def print_estimates():
    print("Estimates only (not measured on Modal). Per step: minutes x (GPU + requested CPU + RAM) at list price.")
    for m, d in DEFAULTS.items():
        e = ESTIMATE[m]; n = len(d["quants"])
        per = lambda g, res: PRICES[g] + res[0] * CPU_S + res[1] * MEM_S
        lo = e["train"][0] * 60 * per(d["gpu"], TRAIN_RES) + e["export"][0] * 60 * per("CPU", EXPORT_RES) + n * e["eval_each"][0] * 60 * per("L4", EVAL_RES)
        hi = e["train"][1] * 60 * per(d["gpu"], TRAIN_RES) + e["export"][1] * 60 * per("CPU", EXPORT_RES) + n * e["eval_each"][1] * 60 * per("L4", EVAL_RES)
        worst = (d["train_timeout_min"] * per(d["gpu"], TRAIN_RES) + EXPORT_TIMEOUT_MIN * per("CPU", EXPORT_RES) + n * d["eval_timeout_min"] * per("L4", EVAL_RES)) * 60
        print(f"  {m:4}: train on {d['gpu']} {e['train'][0]}-{e['train'][1]} min, export {e['export'][0]}-{e['export'][1]} min, "
              f"{n} GGUF evals on L4 {e['eval_each'][0]}-{e['eval_each'][1]} min each (parallel) -> ${lo:.2f}-${hi:.2f}; worst case at the timeouts ${worst:.2f}")
    print(f"  smoke (CPU only, 4 cores / 12 GiB + 8 cores export): about $0.05-0.20")
    print("Serving (serve_modal.py, 2 cores + 12 GiB) per hour awake: " + ", ".join(f"{g} ${(PRICES[g] + 2 * CPU_S + 12 * MEM_S) * 3600:.2f}" for g in ("L4", "A10")))


@app.local_entrypoint()
def main(model: str = "1.5B", gpu: str = "", eval_gpu: str = "L4", epochs: int = 2, use_public: bool = True, qlora: bool = False,
         smoke: bool = False, quants: str = "", ship: str = "q8_0", budget_min: float = 0, train_timeout_min: int = 0, push_hf: bool = False,
         skip_train: str = ""):
    if model not in DEFAULTS: raise SystemExit("--model must be 7B or 1.5B")
    d = DEFAULTS[model]; gpu = "CPU" if smoke else (gpu or d["gpu"]); eval_gpu = "CPU" if smoke else eval_gpu
    qs = [q.strip() for q in quants.split(",") if q.strip()] or (["q8_0"] if smoke else d["quants"])
    run = skip_train or f"{model.lower()}-{'smoke-' if smoke else ''}{time.strftime('%Y%m%d-%H%M%S')}"
    o = dict(model=model, gpu=gpu, eval_gpu=eval_gpu, epochs=epochs, use_public=use_public, qlora=qlora, smoke=smoke, quants=qs, ship=ship,
             budget_min=budget_min or (8 if smoke else d["budget_min"]), push_hf=push_hf, run_name=run)
    tmo = (SMOKE_TIMEOUT_MIN if smoke else (train_timeout_min or d["train_timeout_min"])) * 60
    print(f"Run {run}: {model} {'QLoRA' if qlora else 'bf16 LoRA'} on {gpu}, {epochs} epochs, public mix {'on' if use_public else 'off'}, "
          f"training cap {o['budget_min']} min, train timeout {tmo // 60} min, GGUF evals {qs} on {eval_gpu}, ship {ship}")
    steps = {}; t0 = time.time()
    hf_secret = [modal.Secret.from_name("huggingface", required_keys=["HF_TOKEN"])] if push_hf else []
    if not skip_train:
        steps["train"] = train.with_options(timeout=tmo, **({"cpu": 4, "memory": 12 * 1024} if smoke else {"gpu": gpu})).remote(o)
        print("train:", json.dumps(steps["train"]), f"cost ~${step_cost(steps['train'])}", flush=True)
    steps["export"] = export.remote(o); print("export:", json.dumps(steps["export"]), f"cost ~${step_cost(steps['export'])}", flush=True)
    ev = gguf_eval.with_options(**({"timeout": SMOKE_TIMEOUT_MIN * 60} if smoke else {"gpu": eval_gpu, "timeout": d["eval_timeout_min"] * 60}))
    evals = list(ev.starmap([(o, q) for q in qs]))
    for e in evals: print("gguf_eval:", json.dumps(e), f"cost ~${step_cost(e)}", flush=True)
    steps["gguf_eval"] = evals
    o["steps"] = steps
    pk = package.with_options(secrets=hf_secret).remote(o, [e["quant"] for e in evals if e.get("ok")])
    steps["package"] = pk
    total = sum(step_cost(s) for k, s in steps.items() if k != "gguf_eval") + sum(step_cost(e) for e in evals)
    print("\n== Side by side (HF training eval vs the GGUF files in Ollama) ==")
    for k, v in pk["side_by_side"].items(): print(f"  {k:24} {json.dumps(v)}")
    print(f"\nShipped: {pk['ship']}  ({pk['zip']}, {pk['zip_gib']} GiB). Decision (on the GGUF): "
          f"{'USE IT' if pk['decision']['use_this_model'] else 'KEEP run 2'}  {json.dumps(pk['decision']['checks'])}")
    print(f"Wall time {(time.time() - t0) / 60:.1f} min. Estimated compute cost of this run: ${total:.2f} "
          f"(list prices x container seconds; the Modal dashboard Usage page is the real figure).")
    sub = f"runs/{model.lower()}{'-smoke' if smoke else ''}-latest/{pk['zip']}"
    print(f"\nDownload:  modal volume get {VOLUME_NAME} {sub} .\nAll files:  modal volume ls {VOLUME_NAME} runs/{run}")
    json.dump(dict(run=run, steps=steps, estimated_cost_usd=round(total, 2)), open(f"modal_run_{run}.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    if "--estimate" in sys.argv: print_estimates()
    else: print(__doc__)
