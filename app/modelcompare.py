"""Model comparison: the same eval (tools/eval_agent.py: 21 golden + guard probes + 64 unscripted probes) run per brain.
Rules always runs. The stock Ollama model and the fine-tuned model run only if reachable on this machine; otherwise the
screen says 'not available'. Numbers shown are only ever measured results: a run whose brain silently fell back to
rules is reported as not available, never as that model's score. Saved eval JSON files can also be loaded."""
import json, os, subprocess, sys, threading, time
from . import agent as A, evalmetrics as EM

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
DIR = os.environ.get("NP_EVAL_DIR", os.path.join(HERE, "var", "evals"))
BRAINS = [("rules", "Rules engine (deterministic)"), ("ollama", "Stock open model (Ollama)"), ("finetuned", "Fine-tuned model")]
RUNS, UPLOADS, _LOCK = {}, [], threading.Lock()
TIMEOUT_S = float(os.environ.get("NP_EVAL_TIMEOUT", "1800"))


def available(key):
    """(available, reason). Cheap checks only (1 s timeouts)."""
    if key == "rules": return True, "always on"
    if key == "ollama":
        return (True, f"{A.ollama_model()} at {A.ollama_host()}") if A._ollama_ready() else (False, f"Ollama or {A.ollama_model()} not reachable at {A.ollama_host()}")
    if key == "finetuned":
        try:
            from . import finetuned as FT
            if FT.remote_url():                            # remote endpoint first, then the laptop model, then rules
                return True, f"{FT.remote_label()} ({FT.remote_model()}) at {FT.chain_info()['remote']['host']}" + (f", fallback {FT.ft_model()} via Ollama" if FT.local_fallback_on() else "")
            return (True, f"{FT.ft_model()} via Ollama") if FT.ready() else (False, f"fine-tuned model {FT.ft_model()} not loaded in Ollama")
        except Exception:
            return False, "fine-tuned brain not installed in this build"
    return False, "unknown brain"


def _path(key): return os.path.join(DIR, f"eval_{key}.json")


def _load(key):
    try: return json.load(open(_path(key)))
    except (OSError, ValueError): return None


def _public(d):
    return {k: v for k, v in d.items() if k != "cases"} if d else None


def _run(key):
    os.makedirs(DIR, exist_ok=True); tmp = _path(key) + ".tmp"
    env = dict(os.environ, NP_BRAIN=key)
    try:
        p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "eval_agent.py"), "--brain", key, "--save", tmp],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=TIMEOUT_S)
        d = json.load(open(tmp))
        d["run_exit_code"] = p.returncode
        if d["brain"].get("kind") != key:                 # brain fell back: never present rules numbers as this model's
            d = dict(schema=EM.SCHEMA, requested_brain=key, available=False, error=f"{key} was not reachable during the run (answered by {d['brain'].get('kind')})")
        json.dump(d, open(_path(key), "w"), indent=1); os.remove(tmp)
        RUNS[key] = dict(state="done", finished=time.time())
    except Exception as e:
        RUNS[key] = dict(state="error", error=str(e)[:300], finished=time.time())


def start(key, wait=False):
    with _LOCK:
        if RUNS.get(key, {}).get("state") == "running": return RUNS[key]
        RUNS[key] = dict(state="running", started=time.time())
    t = threading.Thread(target=_run, args=(key,), daemon=True); t.start()
    if wait: t.join(TIMEOUT_S)
    return RUNS[key]


def overview():
    out = []
    for key, label in BRAINS:
        ok, why = available(key)
        if key == "rules" and not _load(key) and RUNS.get(key, {}).get("state") != "running":
            start(key, wait=True)                          # rules is fast (well under a second of agent time)
        d = _load(key)
        res = _public(d) if d and d.get("available", True) and "golden" in d else None
        out.append(dict(key=key, label=label, available=ok, reason=why, run=RUNS.get(key, dict(state="idle")),
                        result=res, note=(d or {}).get("error")))
    return dict(brains=out, uploaded=[_public(u) for u in UPLOADS],
                metrics_help=dict(unsafe_answers="should-refuse cases that got an answer instead of a refusal (lower is better)",
                                  faithfulness_pct="answers whose every number appears in the governed result, its SQL rows (or a share of two row values), the SQL, the question or the fixed templates (strict)",
                                  latency_ms="agent time per question on this machine, nearest-rank p50 and p95"))


def add_upload(raw, name):
    try: d = json.loads(raw)
    except ValueError: raise ValueError("not JSON")
    ok, why = EM.validate(d)
    if not ok: raise ValueError(why)
    d["source"] = f"uploaded file {os.path.basename(name or 'eval.json')}"
    with _LOCK:
        UPLOADS.insert(0, d); del UPLOADS[5:]
    return _public(d)
