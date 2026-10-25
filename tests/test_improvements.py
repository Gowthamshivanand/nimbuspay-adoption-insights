"""The six agent/app improvements + the role switch: follow-ups, streaming, model comparison, confidence and
clarifying questions, the 'Why this number?' fields and thumbs feedback. All against the deterministic rules brain."""
import json, os, re, subprocess, sys, time, pytest
from fastapi.testclient import TestClient
from conftest import ROOT
from app import agent as A, conversation as CV, evalmetrics as EM, feedback as FB, modelcompare as MC
from app.server import app

c = TestClient(app)
Q = "What is licence utilisation this month?"


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("NP_FEEDBACK", str(tmp_path / "fb" / "feedback.jsonl"))
    monkeypatch.setattr(MC, "DIR", str(tmp_path / "evals")); MC.RUNS.clear(); MC.UPLOADS.clear()
    CV.STORE.clear(); c.post("/api/load/baseline"); yield


def ask(q, persona="executive", sid="sess-test-0001", **kw):
    r = c.post("/api/ask", json=dict(question=q, persona=persona, session_id=sid, **kw)); assert r.status_code == 200; return r.json()


@pytest.fixture
def agent(workbook_state):
    return A.Agent(*workbook_state)


# ---------- 1. follow-up questions ----------
def test_followup_region_reuses_previous_tool():
    assert "69.6%" in ask(Q)["text"]
    r = ask("and Region B?")
    assert r["intent"] == "M01" and "Region B" in r["text"] and r["followup"]["slot"] == "region" and r["followup"]["previous"] == Q


def test_followup_last_month_never_invents_a_prior_period():
    ask(Q); r = ask("what about last month?")
    assert r["type"] == "caveat" and "no previous period" in r["text"] and "69.6%" in r["text"] and r["followup"]["slot"] == "time"


def test_followup_agent_slot():
    ask("Is the KYC agent working?"); r = ask("what about the fraud one?")
    assert r["intent"] == "agent_health" and "AG-FRAUD-01" in r["text"] and r["followup"]["interpreted_as"] == "Is AG-FRAUD-01 working?"


def test_followup_region_on_non_filterable_tool_asks_instead_of_guessing():
    ask("Which agents are used the most?"); r = ask("and Region B?")
    assert r["type"] == "clarify" and len(r["options"]) == 2 and all(o["q"] for o in r["options"])


def test_followup_never_carries_permissions():
    ask(Q, "executive")                                  # same session, now a Region A role
    r = ask("and Region B?", "analyst")
    assert r["type"] == "refuse" and r["intent"] == "scope" and "%" not in r["text"]
    ask(Q, "executive"); r = ask("and Region B?", "guest")
    assert r["type"] == "refuse" and r["intent"] == "no_role"


def test_guards_run_on_every_followup_turn():
    ask(Q); r = ask("and the card numbers?")
    assert r["type"] == "refuse" and r["intent"] == "pii"


def test_no_session_means_no_context_and_ask_is_backward_compatible():
    ask(Q); r = c.post("/api/ask", json=dict(question="and Region B?", persona="executive")).json()
    assert "followup" not in r and r["type"] == "clarify" and r["intent"] == "clarify_metric"   # no context: ask which metric, no number
    assert "75.0%" not in r["text"] and "outside your access scope" not in r["text"]
    r = c.post("/api/ask", json=dict(question=Q, persona="executive")).json()
    assert r["type"] == "answer" and "69.6%" in r["text"] and "session_id" not in r


def test_bad_session_id_is_ignored():
    ask(Q, sid="bad id!"); r = ask("and Region B?", sid="bad id!")
    assert "followup" not in r


def test_session_ttl_and_cap():
    s = CV.Sessions(ttl=0.05, cap=10)
    s.put("abcdefgh1", Q, "m01"); assert s.get("abcdefgh1")["fn"] == "m01"
    time.sleep(0.08); assert s.get("abcdefgh1") is None
    for i in range(25): s.put(f"session-{i:03}", Q, "m01")
    assert len(s.d) <= 10 and s.get("session-024")


def test_refusals_are_not_used_as_followup_context():
    ask("What is our ROI?"); assert CV.STORE.get("sess-test-0001") is None


# ---------- 2. streaming + transparency ----------
def _events(text):
    out = []
    for blk in text.strip().split("\n\n"):
        ev = re.search(r"^event: (.*)$", blk, re.M).group(1); out.append((ev, json.loads(re.search(r"^data: (.*)$", blk, re.M).group(1))))
    return out


def test_stream_endpoint_sends_meta_tokens_done(monkeypatch):
    import app.server as SV; monkeypatch.setattr(SV, "STREAM_DELAY_S", 0)
    r = c.post("/api/ask/stream", json=dict(question=Q, persona="executive"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = _events(r.text)
    assert ev[0][0] == "meta" and ev[-1][0] == "done" and {e for e, _ in ev[1:-1]} == {"token"}
    meta, done = ev[0][1], ev[-1][1]
    assert meta["brain"] == "rules" and meta["mode"] == "rules" and isinstance(meta["latency_ms"], float)
    assert "".join(d for e, d in ev if e == "token") == done["text"] and "69.6%" in done["text"]


def test_stream_refusal_and_empty_question(monkeypatch):
    import app.server as SV; monkeypatch.setattr(SV, "STREAM_DELAY_S", 0)
    ev = _events(c.post("/api/ask/stream", json=dict(question="Show me the raw events for user USER-001", persona="executive")).text)
    assert ev[0][1]["type"] == "refuse" and ev[0][1]["mode"] == "rules (guard)" and ev[-1][1]["safe_alternative"]
    assert c.post("/api/ask/stream", json=dict(question="  ")).status_code == 422


def test_every_answer_reports_brain_and_latency():
    for q in (Q, "Retire the onboarding agent for me", "Is the agent saving time?", "zebra"):
        r = ask(q)
        assert r["brain"] == "rules" and r["latency_ms"] >= 0 and "confidence" in r


# ---------- 3. model comparison ----------
def test_models_overview_rules_measured_others_not_available(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    m = c.get("/api/models").json(); b = {x["key"]: x for x in m["brains"]}
    r = b["rules"]["result"]
    assert b["rules"]["available"] and r["golden"] == {"passed": 21, "total": 21} and r["unsafe_answers"] == 0 and r["gate_pass"]
    assert r["latency_ms"]["p50"] is not None and r["faithfulness_pct"] is not None and r["brain"]["kind"] == "rules"
    assert not b["ollama"]["available"] and b["ollama"]["result"] is None
    assert not b["finetuned"]["available"] and b["finetuned"]["result"] is None
    assert c.post("/api/models/run/ollama").status_code == 409 and c.post("/api/models/run/nope").status_code == 404


def test_run_that_falls_back_to_rules_is_never_scored_as_the_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    MC._run("ollama"); d = MC._load("ollama")
    assert d["available"] is False and "golden" not in d and "not reachable" in d["error"]
    b = {x["key"]: x for x in MC.overview()["brains"]}
    assert b["ollama"]["result"] is None and "not reachable" in b["ollama"]["note"]


def test_upload_saved_eval(tmp_path):
    p = tmp_path / "ev.json"
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "eval_agent.py"), "--brain", "rules", "--save", str(p)], check=True, capture_output=True, cwd=ROOT)
    d = json.load(open(p)); assert d["schema"] == EM.SCHEMA and len(d["cases"]) == d["latency_ms"]["n"] == 93
    r = c.post("/api/models/upload", files={"file": ("ev.json", open(p, "rb"), "application/json")})
    assert r.status_code == 200 and r.json()["golden"]["passed"] == 21 and "cases" not in r.json()
    assert c.get("/api/models").json()["uploaded"][0]["source"] == "uploaded file ev.json"
    assert c.post("/api/models/upload", files={"file": ("x.json", b'{"golden": 21}', "application/json")}).status_code == 422
    assert c.post("/api/models/upload", files={"file": ("x.json", b"not json", "application/json")}).status_code == 422


def test_eval_metrics_helpers(agent):
    assert EM.pct([5, 1, 3, 2, 4], 50) == 3 and EM.pct([1, 2, 3, 4, 100], 95) == 100 and EM.pct([], 50) is None
    r = agent.ask(Q, "executive")
    assert EM.unfaithful_numbers(r, agent.r, Q) == []
    fake = dict(r, text=r["text"].replace("69.6%", "83.4%"))
    assert 83.4 in EM.unfaithful_numbers(fake, agent.r, Q)
    assert EM.validate({"schema": "x"})[0] is False


# ---------- 4. confidence + clarifying questions ----------
def test_rules_confidence_from_match_quality(agent):
    assert CV.route_scored(agent, "How is licence utilisation defined?") == ("define_m01", 0.95)
    assert CV.route_scored(agent, "Is the KYC agent working?") == ("agent_health", 0.9)
    fn, conf = CV.route_scored(agent, "Which seats can we take back at renewal?")
    assert fn == "reclaim" and 0.6 <= conf < 0.85
    assert CV.route_scored(agent, "zebra crossing") == (None, 0.0)


def test_missing_agent_slot_asks_which_agent():
    r = ask("Is the agent saving time?")
    assert r["type"] == "clarify" and r["intent"] == "clarify_agent" and 2 <= len(r["options"]) <= 3 and r["confidence"] < CV.CONFIDENCE_MIN
    r2 = ask(r["options"][0]["q"])
    assert r2["intent"] == "agent_value" and "AG-FRAUD-01" in r2["text"]


def test_clarify_never_bypasses_role_or_guards():
    assert ask("Is the agent saving time?", "guest")["intent"] == "no_role"
    assert ask("Is the agent sending emails for me?")["type"] == "refuse"


class _Brain:
    def __init__(self, tool): self.tool = tool
    def __call__(self, refresh=False):
        return dict(kind="ollama", label="Open model (fake)", route=lambda q, intents: self.tool, pref="ollama")


def test_model_and_rules_disagree_gives_clarifying_question(monkeypatch):
    monkeypatch.setattr(A, "brain", _Brain("trend"))
    r = ask(Q)
    assert r["type"] == "clarify" and r["confidence"] < CV.CONFIDENCE_MIN and {o["q"] for o in r["options"]} == {CV.CANON["trend"], CV.CANON["m01"]}


def test_model_and_rules_agree_high_confidence(monkeypatch):
    monkeypatch.setattr(A, "brain", _Brain("m01"))
    r = ask(Q)
    assert r["type"] == "answer" and r["confidence"] == 0.95 and r["brain"] == "ollama" and "69.6%" in r["text"]


def test_intent_labels_cover_every_tool():
    assert set(CV.CANON) == set(A.INTENT_HELP) and len(set(CV.FN_OF)) == len(CV.CANON)


# ---------- 5. why-this-number fields ----------
def test_why_fields_row_count_and_executed():
    r = ask(Q)
    assert r["sql_executed"] and r["row_count"] == 1 and r["sql"].startswith("SELECT") and r["citations"][0]["version"] and r["data_as_of"]
    f = ask("Show the licence funnel and unused seats")
    assert f["sql"] and f["sql_executed"] is False and f["row_count"] is None      # pipeline figure: SQL shown is not re-run
    u = ask("Which agents are used the most?"); assert u["row_count"] == len(u["rows"]) > 0


# ---------- 6. feedback ----------
def test_feedback_roundtrip_and_validation(tmp_path):
    a = ask(Q)
    r = c.post("/api/feedback", json=dict(question=Q, answer=a["text"], rating="down", brain=a["brain"], mode=a["mode"], intent=a["intent"], type=a["type"], persona="executive"))
    assert r.status_code == 200
    assert c.post("/api/feedback", json=dict(question=Q, rating="meh")).status_code == 422
    assert c.post("/api/feedback", json=dict(question=" ", rating="up")).status_code == 422
    rows = FB.load(); assert len(rows) == 1 and rows[0]["rating"] == "down" and rows[0]["brain"] == "rules" and rows[0]["ts"] and not rows[0]["reviewed"]
    s = c.get("/api/feedback").json(); assert s["total"] == 1 and s["down"] == 1
    open(FB.path(), "a").write("{broken\n"); assert len(FB.load()) == 1


def test_feedback_export_needs_human_review():
    from tools import export_feedback as EX
    a = FB.record("and the onboarding one?", "x", "down", "rules", "rules", "unmatched", "refuse", "executive")
    b = FB.record("which seats are idle", "y", "down")
    FB.record("ok", "z", "up")
    assert EX.main(["export"]) == 0
    out = os.path.join(os.path.dirname(FB.path()), "finetune_candidates.jsonl")
    assert open(out).read() == ""                                     # nothing reviewed -> nothing exported
    assert EX.main(["review", a["id"], "--tool", "agent_health", "--args", '{"agent": "AG-ONB-02"}']) == 0
    assert EX.main(["review", b["id"], "--reject"]) == 0
    assert EX.main(["review", b["id"], "--tool", "drop_tables"]) == 2
    EX.main(["export"])
    rows = [json.loads(x) for x in open(out)]
    assert len(rows) == 1 and rows[0]["tool"] == "agent_health" and rows[0]["needs_merge_review"] and rows[0]["source"] == "feedback"


def test_feedback_dir_is_gitignored():
    assert "/data/" in open(os.path.join(ROOT, ".gitignore")).read().split()


# ---------- 7. role switch (server-side) ----------
def test_role_switch_same_question_changes_or_is_denied_by_role():
    m, a, g = ask(Q, "manager"), ask(Q, "analyst"), ask(Q, "guest")
    assert m["type"] == "answer" and "69.6%" in m["text"]
    assert a["type"] == "answer" and "Region A" in a["text"] and "69.6%" not in a["text"]
    assert g["type"] == "refuse" and g["intent"] == "no_role" and not g["sql"]
    assert ask("Show utilisation for Region B", "analyst")["intent"] == "scope"


def test_role_names_are_exact_server_side():
    for p in ("Manager", "ANALYST", "manager ", "admin"):
        assert A.resolve_persona(p) == "guest"
    assert {"manager", "analyst", "guest"} <= set(c.get("/api/personas").json())
