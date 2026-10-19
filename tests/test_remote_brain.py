"""Remote fine-tuned brain (FT_REMOTE_URL, e.g. the Modal 7B) with fallback to the laptop model (local Ollama, FT_MODEL) and
then to the rules engine. Everything is mocked with local HTTP servers: no network, no Modal, no GPU. Also checks the Modal
training / serving helpers that run without the modal package (cost estimate, release rule vs run 2, no secrets in files)."""
import ast, json, os, re, sys, threading, time, pytest
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from app import agent as A, finetuned as FT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODAL_DIR = os.path.join(ROOT, "finetune", "modal")
Q, ROLE = "which bots are flakiest", "platform_engineer"          # the rules miss it, so hybrid asks the model


def make_server(name, route='{"tool": "reliability", "args": {}}', status=200, delay=0.0, key=None):
    class H(BaseHTTPRequestHandler):
        bodies, auths = [], []
        def log_message(self, *a): pass
        def _send(self, code, obj):
            b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            if self.path.startswith("/health"): return self._send(200, {"ok": True, "ready": True})
            self._send(200, {"models": [{"name": name + ":latest", "model": name + ":latest"}]})
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); H.bodies.append(body)
            H.auths.append(self.headers.get("Authorization"))
            if delay: time.sleep(delay)
            if key is not None and self.headers.get("Authorization") != "Bearer " + key: return self._send(401, {"detail": "no"})
            if status != 200: return self._send(status, {"error": "boom"})
            self._send(200, {"message": {"role": "assistant", "content": route}})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H); srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, H, f"http://127.0.0.1:{srv.server_port}"


@pytest.fixture
def env(monkeypatch):
    FT.FT_GENERATE = None; FT._REMOTE_STATE.update(down_until=0.0, last_error="", ok=0, fail=0); FT.SOURCE_COUNTS.clear()
    for k in ("FT_REMOTE_URL", "FT_REMOTE_KEY", "FT_REMOTE_MODEL", "FT_REMOTE_LABEL", "FT_FALLBACK_LOCAL", "FT_REMOTE_TIMEOUT_S",
              "FT_ANSWER", "FT_MODE", "FT_MODEL", "FT_JSON_SCHEMA", "FT_TIMEOUT_S", "FT_ANSWER_TIMEOUT_S"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NP_BRAIN", "finetuned"); monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")   # no local model by default
    servers = []
    def start(*a, **k):
        s = make_server(*a, **k); servers.append(s[0]); return s
    yield start
    for s in servers: s.shutdown()
    FT._REMOTE_STATE.update(down_until=0.0, last_error="", ok=0, fail=0)
    monkeypatch.setenv("NP_BRAIN", "rules"); A.brain(refresh=True)


def test_remote_answers_with_bearer_and_schema(env, base, monkeypatch):
    _, R, url = env("gowtham-nimbuspay-agent-7b", key="s3cret-test-key")
    monkeypatch.setenv("FT_REMOTE_URL", url + "/"); monkeypatch.setenv("FT_REMOTE_KEY", "s3cret-test-key")
    b = A.brain(refresh=True)
    assert b["kind"] == "finetuned" and b["label"] == "Fine-tuned model (Modal 7B, fallback laptop 1.5B)"
    r = A.Agent(*base).ask(Q, ROLE)
    assert r["intent"] == "reliability" and r["answered_by"] == "Modal 7B" and "remote_fallback" not in r
    assert R.auths[0] == "Bearer s3cret-test-key"
    body = R.bodies[0]
    assert body["model"] == "gowtham-nimbuspay-agent-7b" and body["format"] == "json"
    assert body["options"]["temperature"] == 0 and body["options"]["repeat_penalty"] == 1.0 and body["stream"] is False
    monkeypatch.setenv("FT_JSON_SCHEMA", "1"); A.Agent(*base).ask(Q, ROLE)
    assert isinstance(R.bodies[-1]["format"], dict) and "anyOf" in R.bodies[-1]["format"]


def test_remote_down_falls_back_to_laptop_then_skips_remote(env, base, monkeypatch):
    _, R, url = env("gowtham-nimbuspay-agent-7b", status=500)
    _, L, lurl = env("gowtham-nimbuspay-agent")
    monkeypatch.setenv("FT_REMOTE_URL", url); monkeypatch.setenv("FT_REMOTE_KEY", "k"); monkeypatch.setenv("OLLAMA_HOST", lurl)
    A.brain(refresh=True)
    r = A.Agent(*base).ask(Q, ROLE)
    assert r["answered_by"] == "laptop 1.5B" and r["intent"] == "reliability" and r["remote_fallback"].startswith("Modal 7B failed")
    assert L.bodies[0]["model"] == "gowtham-nimbuspay-agent" and L.auths[0] is None      # the key never goes to the local server
    n = len(R.bodies)
    r2 = A.Agent(*base).ask(Q, ROLE)                                                     # cooldown: the dead remote is not retried
    assert len(R.bodies) == n and r2["answered_by"] == "laptop 1.5B"
    info = FT.chain_info()
    assert info["remote"]["calls_failed"] == 1 and info["remote"]["cooling_down"] and info["answered"]["laptop 1.5B"] == 2


def test_remote_timeout_is_fast_and_falls_back(env, base, monkeypatch):
    _, R, url = env("gowtham-nimbuspay-agent-7b", delay=2.0)
    _, L, lurl = env("gowtham-nimbuspay-agent")
    monkeypatch.setenv("FT_REMOTE_URL", url); monkeypatch.setenv("FT_REMOTE_TIMEOUT_S", "0.3"); monkeypatch.setenv("OLLAMA_HOST", lurl)
    A.brain(refresh=True)
    t = time.time(); r = A.Agent(*base).ask(Q, ROLE)
    assert time.time() - t < 1.8 and r["answered_by"] == "laptop 1.5B"


def test_everything_down_means_rules(env, base, monkeypatch):
    monkeypatch.setenv("FT_REMOTE_URL", "http://127.0.0.1:9"); monkeypatch.setenv("FT_REMOTE_TIMEOUT_S", "0.5")
    A.brain(refresh=True)
    r = A.Agent(*base).ask("What is licence utilisation this month?", "executive")   # confident rules match: model not called
    assert r["answered_by"] == "rules" and r["mode"] == "rules (hybrid)"
    r = A.Agent(*base).ask(Q, ROLE)
    assert r["answered_by"] == "rules" and r["mode"] == "rules (fallback)" and r["fallback_reason"] == "invalid model output or timeout"


def test_remote_only_mode_skips_laptop(env, base, monkeypatch):
    _, R, url = env("gowtham-nimbuspay-agent-7b", status=503)
    _, L, lurl = env("gowtham-nimbuspay-agent")
    monkeypatch.setenv("FT_REMOTE_URL", url); monkeypatch.setenv("FT_FALLBACK_LOCAL", "0"); monkeypatch.setenv("OLLAMA_HOST", lurl)
    assert A.brain(refresh=True)["label"] == "Fine-tuned model (Modal 7B)"
    r = A.Agent(*base).ask(Q, ROLE)
    assert r["answered_by"] == "rules" and not L.bodies and FT.chain_info()["order"] == ["Modal 7B", "rules"]


def test_guards_still_first_and_marked_rules(env, base, monkeypatch):
    _, R, url = env("gowtham-nimbuspay-agent-7b", route='{"tool": "m01", "args": {}}')
    monkeypatch.setenv("FT_REMOTE_URL", url); A.brain(refresh=True)
    r = A.Agent(*base).ask("Show me the raw events for user USER-001", "executive")
    assert r["type"] == "refuse" and r["mode"] == "rules (guard)" and r["answered_by"] == "rules" and not R.bodies


def test_remote_model_refusal_is_attributed(env, base, monkeypatch):
    _, R, url = env("gowtham-nimbuspay-agent-7b", route='{"tool": "refuse", "args": {"reason": "harmful"}}')
    monkeypatch.setenv("FT_REMOTE_URL", url); A.brain(refresh=True)
    r = A.Agent(*base).ask(Q, ROLE)
    assert r["type"] == "refuse" and r["answered_by"] == "Modal 7B"


def test_default_unchanged_without_remote(env, base, monkeypatch):
    _, L, lurl = env("gowtham-nimbuspay-agent")
    monkeypatch.setenv("OLLAMA_HOST", lurl)
    assert A.brain(refresh=True)["label"] == "Fine-tuned model (gowtham-nimbuspay-agent)"
    r = A.Agent(*base).ask(Q, ROLE)
    assert r["answered_by"] == "laptop 1.5B" and "remote_fallback" not in r and len(L.bodies) == 1
    assert FT.chain_info()["order"] == ["laptop 1.5B", "rules"] and FT.chain_info()["remote"]["configured"] is False
    monkeypatch.setenv("FT_MODEL", "gowtham-nimbuspay-agent-7b"); assert FT.local_label() == "laptop 7B"


def test_rules_brain_has_no_new_fields(base, monkeypatch):
    monkeypatch.setenv("NP_BRAIN", "rules"); monkeypatch.setenv("FT_REMOTE_URL", "http://127.0.0.1:9"); A.brain(refresh=True)
    r = A.Agent(*base).ask(Q, ROLE)
    assert "answered_by" not in r and r["mode"] == "rules"
    assert "ft_chain" not in A.brain_info() or A.brain_info()["kind"] == "rules"


def test_api_brain_exposes_chain_without_key(env, monkeypatch):
    from fastapi.testclient import TestClient
    from app.server import app
    monkeypatch.setenv("FT_REMOTE_URL", "https://example--gowtham-nimbuspay-serve-serve-web.modal.run")
    monkeypatch.setenv("FT_REMOTE_KEY", "never-show-this-key")
    d = TestClient(app).get("/api/brain", params={"refresh": True}).json()
    assert d["kind"] == "finetuned" and d["ft_chain"]["remote"]["host"] == "example--gowtham-nimbuspay-serve-serve-web.modal.run"
    assert "never-show-this-key" not in json.dumps(d)


def test_answer_timeout_is_separate(env, monkeypatch):
    for k in ("FT_TIMEOUT_S", "FT_ANSWER_TIMEOUT_S", "FT_REMOTE_TIMEOUT_S"): monkeypatch.delenv(k, raising=False)
    assert FT._timeout_for("route") == 4.0 and FT._timeout_for("answer") == 10.0
    assert FT._timeout_for("route", remote=True) == 6.0 and FT._timeout_for("answer", remote=True) == 10.0
    monkeypatch.setenv("FT_ANSWER_TIMEOUT_S", "15"); monkeypatch.setenv("FT_TIMEOUT_S", "3")
    assert FT._timeout_for("route") == 3.0 and FT._timeout_for("answer") == 15.0


def test_slow_answer_within_answer_timeout_is_kept(env, base, monkeypatch):
    """A 1.2 s answer call survives (FT_ANSWER_TIMEOUT_S 10) even though the route timeout is 1 s."""
    _, L, lurl = env("gowtham-nimbuspay-agent", route="Agents are mostly within the gates. Source: M10.", delay=1.2)
    monkeypatch.setenv("OLLAMA_HOST", lurl); monkeypatch.setenv("FT_TIMEOUT_S", "1")
    out = FT.generate([{"role": "user", "content": "x"}], "answer")
    assert out.startswith("Agents") and FT.last_source() == "laptop 1.5B"
    with pytest.raises(Exception): FT.generate(FT.route_messages("hi", "executive"), "route")   # route keeps the 1 s limit


def test_warmup_goes_through_the_chain(env, monkeypatch):
    _, R, url = env("gowtham-nimbuspay-agent-7b")
    monkeypatch.setenv("FT_REMOTE_URL", url)
    assert FT.warmup() is not None and len(R.bodies) == 1


# ---------- Modal scripts (no modal package needed) ----------
sys.path.insert(0, os.path.join(ROOT, "finetune"))


def test_cost_estimate_and_prices_match():
    import ft_train as T
    assert T.cost_usd(3600, "A100-80GB") == 2.5 and T.cost_usd(3600, "L4") == 0.8 and T.cost_usd(3600, "H100") == 3.95
    assert T.cost_usd(3600, "L4", 2, 12) == 0.99
    tree = ast.parse(open(os.path.join(MODAL_DIR, "train_modal.py"), encoding="utf-8").read())
    prices = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "PRICES")
    assert prices == T.GPU_USD_PER_S


def test_config_defaults():
    import ft_train as T
    c = T.Config(model_choice="7B", work="/tmp/np_cfg_test").finalize()
    assert c.base_model == "Qwen/Qwen2.5-7B-Instruct" and c.ollama_name == "gowtham-nimbuspay-agent-7b" and c.epochs == 2
    assert (c.batch, c.grad_acc, c.eval_every, c.patience, c.qlora) == (4, 4, 100, 3, False)
    q = T.Config(model_choice="7B", qlora=True, work="/tmp/np_cfg_test").finalize()
    assert (q.batch, q.grad_acc) == (2, 8)
    s = T.Config(model_choice="1.5B", smoke=True, work="/tmp/np_cfg_test").finalize()
    assert s.base_model == "Qwen/Qwen2.5-0.5B-Instruct" and s.ollama_name == "gowtham-nimbuspay-agent" and s.max_steps > 0
    assert "FROM ./x.gguf" in T.modelfile_text("x.gguf") and "<|im_start|>" in T.modelfile_text("x.gguf")


def test_release_rule_vs_run2():
    import ft_train as T
    good = {"gate_pure_pass": True, "model": {"route": {"tool_acc": 91.0, "unsafe_routes": 10}}, "fresh_wording": {"tool_acc": 88.0}}
    assert T.compare_run2(good)["use_this_model"]
    for change in ({"gate_pure_pass": False}, {"model": {"route": {"tool_acc": 88.2, "unsafe_routes": 10}}},
                   {"fresh_wording": {"tool_acc": 83.5}}, {"model": {"route": {"tool_acc": 91.0, "unsafe_routes": 20}}}):
        assert not T.compare_run2({**good, **change})["use_this_model"], change


def test_modal_files_parse_and_hold_no_secrets():
    for f in ("train_modal.py", "serve_modal.py", "remote_check.py"):
        src = open(os.path.join(MODAL_DIR, f), encoding="utf-8").read(); ast.parse(src)
        assert not re.search(r"\bak-[A-Za-z0-9]{10,}|\bas-[A-Za-z0-9]{10,}|\bhf_[A-Za-z0-9]{20,}", src), f
    serve = open(os.path.join(MODAL_DIR, "serve_modal.py"), encoding="utf-8").read()
    assert 'os.environ.get("NP_SERVE_GPU", "L4")' in serve and "max_containers=1" in serve and "scaledown_window=SCALEDOWN_S" in serve
    assert "Secret.from_name(\"nimbuspay-serve-key\"" in serve


def test_serve_helpers_bearer_and_zip(tmp_path):
    ft_dir = os.path.join(ROOT, "finetune")                         # finetune/modal (this folder) must not shadow the modal package
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != ft_dir]
    if "modal" in sys.modules and not hasattr(sys.modules["modal"], "App"): del sys.modules["modal"]
    pytest.importorskip("modal")
    sys.path.insert(0, MODAL_DIR)
    import serve_modal as S, zipfile
    assert S.check_bearer("Bearer abc", "abc") and not S.check_bearer("Bearer abd", "abc") and not S.check_bearer(None, "abc")
    assert not S.check_bearer("Bearer ", "")                       # no key configured -> closed, never open
    z = tmp_path / "export.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("gowtham-nimbuspay-agent-7b-q4_k_m.gguf", b"GGUF"); zf.writestr("gowtham-nimbuspay-agent-7b-q8_0.gguf", b"GGUF")
        zf.writestr("Modelfile", "FROM ./gowtham-nimbuspay-agent-7b-q8_0.gguf\nPARAMETER temperature 0\n")
    g, mf = S.find_model_files(str(tmp_path))
    assert g.endswith("q8_0.gguf") and mf.endswith("Modelfile")              # the shipped file named in the Modelfile
    assert S.hourly_cost("L4") == 0.99 and S.hourly_cost("A10") == 1.29
