"""Fine-tuned brain (NP_BRAIN=finetuned): a small open model, LoRA-tuned on finetune/data, does two jobs.
  ROUTE : question (+ role, + optional previous question) -> JSON {"tool": <governed tool> | "none" | "refuse", "args": {...}}
  ANSWER: tool result (governed draft text + SQL rows + citations) -> a short answer that uses ONLY numbers in that result.
Code stays the authority: guards run before the model, the JSON is schema-checked, args are validated against the data
and the caller's scope, every number in a model answer must appear in the governed result, and any failure falls back
to the deterministic rules router or the template answer. The same prompt builders are used to make the training data
(finetune/make_dataset.py), so training and serving prompts cannot drift apart."""
import json, logging, os, re
LOG = logging.getLogger("nimbuspay.model")   # failure lines carry the error TYPE only, never a key or prompt

ROUTE_SYSTEM = ("You are the NimbusPay adoption-metrics router. Read the user's question and reply with ONE line of JSON: "
                "{\"tool\": <tool>, \"args\": {...}}. Use a governed tool name, \"refuse\" with args.reason for unsafe or "
                "ungoverned asks, or \"none\" if no governed tool fits. Never answer the question and never write a number.\n"
                "Tools: {tools}\nRefusal reasons: {reasons}\n"
                "Args: region (\"Region A\".. for m01), agent (agent ID for agent_health/agent_value), metric (M06-M09 for outcome), "
                "clarify (for none: \"agent\" if one unnamed agent is meant, \"topic\" if several separate asks have no main one; plain none otherwise).")
ANSWER_SYSTEM = ("You write the final answer for the NimbusPay adoption-metrics assistant. Use ONLY the governed result below. "
                 "Lead with the direct answer in 1 to 3 short sentences, keep every caveat, never add, round or compute a number, "
                 "and end with 'Source:' and the metric IDs.")

REFUSE_REASONS = ["write", "pii", "individual", "small_group", "scope", "forecast", "causal", "ungoverned", "injection", "gaming", "harmful"]
ARG_KEYS = {"m01": {"region"}, "agent_health": {"agent"}, "agent_value": {"agent"}, "outcome": {"metric"}, "refuse": {"reason"}, "none": {"clarify"}}
CLARIFY_SLOTS = {"agent", "topic"}   # none + clarify: ask the user instead of guessing (see Agent.ask and conversation.py)
OUTCOME_METRICS = {"M06", "M07", "M08", "M09"}
FT_GENERATE = None     # optional callable(messages, kind) -> str; the Colab notebook and the tests plug a generator in here


def ft_model():
    return os.environ.get("FT_MODEL", "gowtham-nimbuspay-agent")


def tool_names():
    from .agent import INTENT_HELP
    return list(INTENT_HELP)


def route_messages(q, role, prev=None):
    sys = ROUTE_SYSTEM.replace("{tools}", ", ".join(tool_names())).replace("{reasons}", ", ".join(REFUSE_REASONS))
    user = f"Role: {role}\n" + (f"Previous question: {prev}\n" if prev else "") + f"Question: {q}"
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def route_target(tool, args=None):
    return json.dumps({"tool": tool, "args": args or {}}, separators=(", ", ": "))


def _rows_txt(rows, limit=12):
    if not rows: return "none"
    out = [", ".join(str(c) for c in r) for r in list(rows)[:limit]]
    return "\n".join(out) + (f"\n(+{len(rows) - limit} more rows)" if len(rows) > limit else "")


def answer_messages(q, role, r):
    cites = ", ".join(f"{c['metric']} {c['version']}" for c in r["citations"]) or "none"
    user = (f"Role: {role}\nQuestion: {q}\nTool: {r['intent']} ({r['type']})\nGoverned draft: {r['text']}\n"
            f"SQL rows:\n{_rows_txt(r.get('rows'))}\nCitations: {cites}\nData as of: {r['data_as_of']}")
    return [{"role": "system", "content": ANSWER_SYSTEM}, {"role": "user", "content": user}]


# ---------- number faithfulness ----------
_NUM = re.compile(r"(?<![A-Za-z0-9.])(?<![A-Za-z]-)\d[\d,]*(?:\.\d+)?")


def numbers_in(text):
    """Numbers as written (metric IDs like M01, agent IDs like AG-KYC-04 and team IDs like TEAM-A1 are not numbers)."""
    out = set()
    for m in _NUM.findall(str(text)):
        s = m.rstrip(",").replace(",", "")
        try: out.add(float(s))
        except ValueError: pass
    return out


def allowed_numbers(r):
    src = [r["text"], r.get("data_as_of") or "", " ".join(c["version"] for c in r["citations"])]
    for row in r.get("rows") or []:
        src += [str(c) for c in row]
    allowed = set()
    for s in src:
        allowed |= numbers_in(s)
    return allowed


def unfaithful_numbers(answer, r):
    """Numbers in the answer that are not in the governed result. Empty set = faithful."""
    ok = allowed_numbers(r)
    return {x for x in numbers_in(answer) if x not in ok}


def gold_answer(r):
    """Reference short answer made only from the governed draft's own sentences (so it is faithful by construction)."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(\[])", r["text"]) if s.strip()]
    keep = sents[:1]
    if len(sents) > 1 and len(sents[0]) + len(sents[1]) < 450: keep.append(sents[1])
    for s in sents[len(keep):]:
        if len(keep) >= 3: break
        if re.search(r"caveat|correlation|not a|not the same|approximate|placeholder|can't|cannot|don't|no prior|still ramping|suppressed|restatement|care", s, re.I):
            keep.append(s)
    txt = " ".join(keep)
    src = ", ".join(dict.fromkeys(c["metric"] for c in r["citations"]))
    return txt + (f" Source: {src} ({r['citations'][0]['version']}, data as of {r['data_as_of']})." if src else "")


# ---------- structured output (Ollama `format` = JSON schema) ----------
REQUIRED_ARGS = {"outcome": {"metric"}, "refuse": {"reason"}}   # a route without these is never acted on (clarify instead)


def json_schema_on():
    """FT_JSON_SCHEMA=1: the route call passes a JSON schema as Ollama `format` (tool enum, required args).
    Default 0 = plain format "json": the output is still always valid JSON, and parse_route() rejects unknown tools or args
    (rules fallback). Why off by default: Ollama re-orders the schema's properties alphabetically, so the constrained decoder
    forces {"args": ..., "tool": ...} while the model was trained to write "tool" first. Measured on the exported smoke model
    (finetune/modal/README.md): schema mode agreed with the HF model's routes on 0/40 rows, plain "json" on 9/40."""
    return os.environ.get("FT_JSON_SCHEMA", "0").strip().lower() not in ("0", "false", "no", "off", "")


def route_schema(agents=None):
    """JSON schema for the route output. Labels are exactly the ones the training data uses (finetune/make_dataset.py):
    every governed tool name, "none" (optional args.clarify agent|topic) and "refuse" (required args.reason)."""
    def obj(tool, props=None, required=()):
        return {"type": "object", "properties": {"tool": {"type": "string", "enum": [tool]},
                "args": {"type": "object", "properties": props or {}, "required": list(required), "additionalProperties": False}},
                "required": ["tool", "args"], "additionalProperties": False}
    agent = {"type": "string", "enum": sorted(agents)} if agents else {"type": "string"}
    special = {"m01": obj("m01", {"region": {"type": "string"}}),
               "agent_health": obj("agent_health", {"agent": agent}),
               "agent_value": obj("agent_value", {"agent": agent}),
               "outcome": obj("outcome", {"metric": {"type": "string", "enum": sorted(OUTCOME_METRICS)}}, ["metric"])}
    variants = [special.get(t) or obj(t) for t in tool_names()]
    variants.append(obj("none", {"clarify": {"type": "string", "enum": sorted(CLARIFY_SLOTS)}}))
    variants.append(obj("refuse", {"reason": {"type": "string", "enum": REFUSE_REASONS}}, ["reason"]))
    return {"anyOf": variants}


# ---------- model I/O ----------
# Brain chain (each step only if configured / reachable): remote endpoint (FT_REMOTE_URL, e.g. the Modal 7B) -> local Ollama
# (FT_MODEL, the laptop 1.5B) -> the Agent's rules fallback. Nothing changes when FT_REMOTE_URL is not set.
import threading
_LOCAL = threading.local()                      # per request thread: which source answered the last model call
_REMOTE_STATE = {"down_until": 0.0, "last_error": "", "ok": 0, "fail": 0}
SOURCE_COUNTS = {}                              # source -> number of model calls it answered (shown in the Models tab)


def remote_url():
    return os.environ.get("FT_REMOTE_URL", "").strip().rstrip("/")


def remote_model():
    return os.environ.get("FT_REMOTE_MODEL", "gowtham-nimbuspay-agent-7b")


def remote_label():
    return os.environ.get("FT_REMOTE_LABEL", "Modal 7B")


def local_label():
    m = ft_model().lower()
    return "laptop " + ("7B" if "7b" in m else "1.5B")


def local_fallback_on():
    """FT_FALLBACK_LOCAL=0 turns off the local Ollama step (e.g. to evaluate the remote model alone)."""
    return os.environ.get("FT_FALLBACK_LOCAL", "1").strip().lower() not in ("0", "false", "no", "off")


def _float_env(name, default):
    try: return float(os.environ.get(name, default))
    except ValueError: return float(default)


def remote_timeout():
    """Per remote call (FT_REMOTE_TIMEOUT_S, default 6: includes the internet round trip)."""
    return _float_env("FT_REMOTE_TIMEOUT_S", "6")


def last_source():
    return getattr(_LOCAL, "source", None)


def last_remote_error():
    return getattr(_LOCAL, "remote_error", None)


def _set_source(src):
    _LOCAL.source = src
    if src: SOURCE_COUNTS[src] = SOURCE_COUNTS.get(src, 0) + 1


def keep_alive():
    """FT_KEEP_ALIVE (default 30m; the demo launcher sets 24h). A bare number is sent as a number of seconds (-1 = forever),
    because Ollama parses a string with Go's time.ParseDuration and rejects "-1" (no unit), which would fail every call."""
    v = os.environ.get("FT_KEEP_ALIVE", "30m").strip() or "30m"
    try: return int(v)
    except ValueError:
        try: return float(v)
        except ValueError: return v


def _chat_body(model, messages, kind, schema=None):
    body = {"model": model, "stream": False, "messages": messages,      # greedy, no repeat penalty: same decoding as the HF eval
            "options": {"temperature": 0, "repeat_penalty": 1.0, "num_predict": 96 if kind == "route" else 220}}
    if kind == "route":
        body["format"] = (schema or route_schema()) if json_schema_on() else "json"
    body["keep_alive"] = keep_alive()                                  # keep the model loaded between questions
    return body


def _ollama_chat(messages, kind, timeout=None, schema=None):
    from .agent import _http_json, ollama_host
    h = ollama_host(); h = h if h.startswith("http") else "http://" + h
    out = _http_json(h + "/api/chat", _chat_body(ft_model(), messages, kind, schema), timeout=timeout or _timeout_for(kind))
    return out["message"]["content"]


def _remote_chat(messages, kind, timeout=None, schema=None):
    """Ollama-compatible /api/chat on FT_REMOTE_URL with a bearer key (FT_REMOTE_KEY, never logged)."""
    from .agent import _http_json
    key = os.environ.get("FT_REMOTE_KEY", "")
    out = _http_json(remote_url() + "/api/chat", _chat_body(remote_model(), messages, kind, schema),
                     headers={"Authorization": "Bearer " + key} if key else None, timeout=timeout or _timeout_for(kind, remote=True))
    return out["message"]["content"]


def _remote_available():
    return bool(remote_url()) and __import__("time").time() >= _REMOTE_STATE["down_until"]


def ft_timeout():
    """Per route call timeout in seconds (FT_TIMEOUT_S, default 4). On timeout the Agent falls back to the rules engine."""
    try: return float(os.environ.get("FT_TIMEOUT_S", "4"))
    except ValueError: return 4.0


def answer_timeout():
    """Per answer call (FT_ANSWER_TIMEOUT_S, default 10): an answer is ~200 tokens, a route ~20, so it gets its own limit.
    On timeout the governed template answer is kept."""
    return _float_env("FT_ANSWER_TIMEOUT_S", "10")


def _timeout_for(kind, remote=False):
    if remote: return max(remote_timeout(), answer_timeout()) if kind == "answer" else remote_timeout()
    return answer_timeout() if kind == "answer" else ft_timeout()


def warmup(timeout=120):
    """Load the model into memory once (first call can take tens of seconds on a laptop; a cold Modal container longer).
    Returns seconds, or None on failure."""
    import time
    t = time.time()
    try:
        msgs = route_messages("What is licence utilisation this month?", "executive")
        if FT_GENERATE: FT_GENERATE(msgs, "route")
        else: generate(msgs, "route", timeout=timeout)
        return round(time.time() - t, 2)
    except Exception:
        return None


def warmup_all(timeout=120):
    """Startup warm-up of EVERY configured step, each on its own (generate() stops at the first step that answers, so with a
    remote configured the laptop model would stay cold). Direct calls: warm-ups are not counted in SOURCE_COUNTS.
    Returns {"remote": seconds | None (failed) | "off", "local": seconds | None | "off", "ready": bool, "line": str}."""
    import time
    msgs = route_messages("What is licence utilisation this month?", "executive")
    out = {}
    if FT_GENERATE:
        t = time.time()
        try: FT_GENERATE(msgs, "route"); out["generator"] = round(time.time() - t, 2)
        except Exception: out["generator"] = None
    use = {"remote": bool(remote_url()), "local": not remote_url() or local_fallback_on()} if not FT_GENERATE else {"remote": False, "local": False}
    for name, call in (("remote", _remote_chat), ("local", _ollama_chat)):
        if not use[name]: out[name] = "off"; continue
        t = time.time()
        try: call(msgs, "route", timeout=timeout); out[name] = round(time.time() - t, 2)
        except Exception as e: out[name] = None; out[name + "_error"] = type(e).__name__
    ok = [v for k, v in out.items() if k in ("generator", "remote", "local") and isinstance(v, (int, float))]
    out["ready"] = bool(ok)
    fmt = lambda k: ("off" if out.get(k) == "off" else f"warm in {out[k]} s" if isinstance(out.get(k), (int, float))
                          else f"NOT READY ({out.get(k + '_error', 'failed')})")
    out["line"] = (("READY" if out["ready"] else "NOT READY (answers will use the rules engine)") + f": fine-tuned brain | "
                   + f"{remote_label()} {fmt('remote')} | {local_label()} ({ft_model()}) {fmt('local')}")
    return out


def generate(messages, kind, schema=None, timeout=None):
    """One model call through the chain: FT_GENERATE (notebook / tests) > remote (FT_REMOTE_URL) > local Ollama (FT_MODEL).
    Raises if every configured step fails (the Agent then uses the rules engine). eval_finetuned.py uses this same function.
    After a remote failure the remote is skipped for FT_REMOTE_COOLDOWN_S (default 30 s) so a dead endpoint costs one timeout."""
    import time
    _LOCAL.source = None; _LOCAL.remote_error = None
    if FT_GENERATE:
        out = FT_GENERATE(messages, kind); _set_source(os.environ.get("FT_GENERATE_LABEL") or None); return out
    err = None
    if _remote_available():
        try:
            out = _remote_chat(messages, kind, timeout=timeout, schema=schema)
            _REMOTE_STATE["ok"] += 1; _set_source(remote_label()); return out
        except Exception as e:
            err = e; _REMOTE_STATE["fail"] += 1; _REMOTE_STATE["last_error"] = type(e).__name__ + ": " + str(e)[:120]
            _LOCAL.remote_error = remote_label() + " failed (" + type(e).__name__ + ")"
            _REMOTE_STATE["down_until"] = time.time() + _float_env("FT_REMOTE_COOLDOWN_S", "30")
            LOG.warning("model step failed: step=remote kind=%s error=%s", kind, type(e).__name__)
    if remote_url() and not local_fallback_on():
        raise err or RuntimeError("remote endpoint cooling down after a failure")
    try:
        out = _ollama_chat(messages, kind, timeout=timeout, schema=schema)
    except Exception as e:
        LOG.warning("model step failed: step=local model=%s kind=%s error=%s", ft_model(), kind, type(e).__name__); raise
    _set_source(local_label()); return out


def _local_ready():
    from .agent import _http_json, ollama_host
    try:
        h = ollama_host(); h = h if h.startswith("http") else "http://" + h
        tags = _http_json(h + "/api/tags", timeout=1.0)
        names = {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}
        return ft_model() in names or ft_model() + ":latest" in names
    except Exception:
        return False


def ready():
    """True if some model step can answer: FT_GENERATE, a configured remote endpoint (checked per call, with fallback),
    or the local Ollama model."""
    if FT_GENERATE: return True
    if remote_url(): return True
    return _local_ready()


def chain_info():
    """For /api/brain and the Models tab. Never includes the key."""
    from urllib.parse import urlparse
    import time
    r = remote_url()
    return dict(remote=dict(configured=bool(r), host=urlparse(r).netloc if r else None, model=remote_model() if r else None,
                            label=remote_label() if r else None, calls_ok=_REMOTE_STATE["ok"], calls_failed=_REMOTE_STATE["fail"],
                            cooling_down=bool(r) and time.time() < _REMOTE_STATE["down_until"], last_error=_REMOTE_STATE["last_error"] or None),
                local=dict(model=ft_model(), label=local_label(), fallback=local_fallback_on() or not r, ready=_local_ready()),
                answered=dict(SOURCE_COUNTS), order=([remote_label()] if r else []) + ([local_label()] if (local_fallback_on() or not r) else []) + ["rules"])


def parse_route(text, agents, regions):
    """Strict schema check. Returns {"tool", "args"} or None (None = fall back to rules)."""
    try:
        m = re.search(r"\{.*\}", str(text), re.S)
        d = json.loads(m.group(0) if m else text)
    except Exception:
        return None
    if not isinstance(d, dict) or set(d) - {"tool", "args"}: return None
    tool, args = d.get("tool"), d.get("args") or {}
    if not isinstance(tool, str) or not isinstance(args, dict): return None
    if tool not in tool_names() and tool not in ("none", "refuse"): return None
    if set(args) - ARG_KEYS.get(tool, set()): return None
    if any(not isinstance(v, str) for v in args.values()): return None
    if tool == "refuse" and args.get("reason") not in REFUSE_REASONS: return None
    if "clarify" in args and args["clarify"] not in CLARIFY_SLOTS: return None
    if "agent" in args and args["agent"] not in agents: return None
    if "metric" in args and args["metric"] not in OUTCOME_METRICS: return None
    if "region" in args:
        mm = re.fullmatch(r"region ([a-z])", args["region"].strip().lower())
        if not mm or not any(x.lower().startswith("region " + mm.group(1)) for x in regions): return None
        args = {**args, "region": "Region " + mm.group(1).upper()}
    return {"tool": tool, "args": args}


def route(q, role, prev, agents, regions):
    try:
        return parse_route(generate(route_messages(q, role, prev), "route", schema=route_schema(agents)), agents, regions)
    except Exception:
        _LOCAL.source = None
        return None


def answer(q, role, r):
    """Model answer if it passes the number check, else None (keep the template)."""
    try:
        a = str(generate(answer_messages(q, role, r), "answer")).strip()
    except Exception:
        return None, "model error"
    if not a or len(a) > 1200: return None, "empty or too long"
    bad = unfaithful_numbers(a, r)
    if bad: return None, "number not in governed result: " + ", ".join(f"{x:g}" for x in sorted(bad))
    return a, ""
