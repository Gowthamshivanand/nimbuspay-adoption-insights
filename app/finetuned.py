"""Fine-tuned brain (NP_BRAIN=finetuned): a small open model, LoRA-tuned on finetune/data, does two jobs.
  ROUTE : question (+ role, + optional previous question) -> JSON {"tool": <governed tool> | "none" | "refuse", "args": {...}}
  ANSWER: tool result (governed draft text + SQL rows + citations) -> a short answer that uses ONLY numbers in that result.
Code stays the authority: guards run before the model, the JSON is schema-checked, args are validated against the data
and the caller's scope, every number in a model answer must appear in the governed result, and any failure falls back
to the deterministic rules router or the template answer. The same prompt builders are used to make the training data
(finetune/make_dataset.py), so training and serving prompts cannot drift apart."""
import json, os, re

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
    return os.environ.get("FT_MODEL", "nimbuspay-router")


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


# ---------- model I/O ----------
def _ollama_chat(messages, kind):
    from .agent import _http_json, ollama_host
    h = ollama_host(); h = h if h.startswith("http") else "http://" + h
    body = {"model": ft_model(), "stream": False, "messages": messages,
            "options": {"temperature": 0, "num_predict": 96 if kind == "route" else 220}}
    if kind == "route": body["format"] = "json"
    out = _http_json(h + "/api/chat", body, timeout=float(os.environ.get("OLLAMA_TIMEOUT", "30")))
    return out["message"]["content"]


def generate(messages, kind):
    return (FT_GENERATE or _ollama_chat)(messages, kind)


def ready():
    if FT_GENERATE: return True
    from .agent import _http_json, ollama_host
    try:
        h = ollama_host(); h = h if h.startswith("http") else "http://" + h
        tags = _http_json(h + "/api/tags", timeout=1.0)
        names = {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}
        return ft_model() in names or ft_model() + ":latest" in names
    except Exception:
        return False


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
        return parse_route(generate(route_messages(q, role, prev), "route"), agents, regions)
    except Exception:
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
