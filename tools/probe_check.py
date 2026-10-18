"""Shared grader for the unscripted probe set (tests/data/probes.json). Used by tests/test_probes.py and tools/eval_agent.py."""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load():
    d = json.load(open(os.path.join(ROOT, "tests", "data", "probes.json")))
    return d["panel24"], d["extra"]

def grade(agent, p):
    """Return (ok, response, reason)."""
    per = p.get("persona", "executive")
    r = agent.ask(p["q"], per)
    cites = [c["metric"] for c in r["citations"]]
    if p["expect"] == "answer":
        if r["type"] not in ("answer", "caveat"): return False, r, "not answered"
        if not cites: return False, r, "no citations"
    else:
        if r["type"] != "refuse": return False, r, "should refuse"
        if not r.get("safe_alternative"): return False, r, "no safe alternative"
    if p.get("intent") and r["intent"] != p["intent"]: return False, r, f"intent {r['intent']} != {p['intent']}"
    if p.get("cites") and p["cites"] not in cites: return False, r, f"missing citation {p['cites']}"
    if p.get("text") and p["text"] not in r["text"]: return False, r, f"text lacks {p['text']!r}"
    if p.get("suggest") and len(r.get("suggestions") or []) != 3: return False, r, "no 3 suggestions"
    return True, r, ""
