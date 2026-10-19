"""Pitch-day hardening (19 Oct 2026 code review, prep/AGENT_CODE_REVIEW.md): launcher + readiness check, warm-up of every
model step, safe replies when a tool fails, audit-log locking and escaping, the individual guard's everyday wording and the
off-domain check inside a session. The model is mocked (no network, no GPU)."""
import io, json, os, re, sys, threading, pytest
from fastapi.testclient import TestClient
from conftest import ROOT, BASE
from app import agent as A, finetuned as FT, server as S

sys.path.insert(0, os.path.join(ROOT, "tools"))
from test_remote_brain import make_server            # mocked Ollama-compatible endpoints


class Gen:
    def __init__(self, route): self.route, self.calls = route, []
    def __call__(self, messages, kind):
        self.calls.append(messages); return self.route


@pytest.fixture
def hybrid(monkeypatch):
    monkeypatch.setenv("NP_BRAIN", "finetuned"); monkeypatch.setenv("FT_MODE", "hybrid"); monkeypatch.setenv("FT_ANSWER", "0")
    def use(route):
        g = Gen(route); FT.FT_GENERATE = g; A.brain(refresh=True); return g
    yield use
    FT.FT_GENERATE = None; monkeypatch.setenv("NP_BRAIN", "rules"); A.brain(refresh=True)


@pytest.fixture
def client():
    c = TestClient(S.app, raise_server_exceptions=False)
    yield c
    c.post("/api/load/baseline")


def _upload_without(c, event_type):
    ev = open(os.path.join(BASE, "events.csv"), encoding="utf-8").read().splitlines()
    i = ev[0].split(",").index("event_type")
    kept = "\n".join([ev[0]] + [l for l in ev[1:] if l.split(",")[i] != event_type]).encode()
    files = {"events": ("events.csv", io.BytesIO(kept), "text/csv")}
    files.update({k: (k + ".csv", open(os.path.join(BASE, k + ".csv"), "rb"), "text/csv") for k in ("seats", "registry")})
    assert c.post("/api/upload", files=files).status_code == 200


# ---------- (5) tool failures give a safe reply, never a 500 ----------
@pytest.mark.parametrize("missing, q, intent", [("connector_call", "Which connector has the highest failure rate this week?", "M11"),
                                                 ("agent_run", "What was agent error rate yesterday?", "M10")])
def test_upload_without_needed_events_gives_safe_caveat(client, missing, q, intent):
    _upload_without(client, missing)
    res = client.post("/api/ask", json={"question": q, "persona": "executive"})
    assert res.status_code == 200
    r = res.json()
    assert r["type"] == "caveat" and r["intent"] == intent and "No " in r["text"] and not re.search(r"\d+(\.\d+)?%", r["text"])


def test_tool_exception_becomes_safe_reply(client, monkeypatch):
    def boom(self, q, persona): raise ZeroDivisionError("bad data")
    monkeypatch.setattr(A.Agent, "m01", boom)
    res = client.post("/api/ask", json={"question": "What is licence utilisation this month?", "persona": "executive"})
    assert res.status_code == 200
    r = res.json()
    assert r["type"] == "caveat" and r["intent"] == "M01" and r["error"] == "ZeroDivisionError" and "won't guess" in r["text"]
    assert not re.search(r"\d", r["text"])                                  # no number on a failed tool


# ---------- (6) audit writes are serialised; (3) the limit is clamped ----------
def test_parallel_asks_never_break_the_shared_audit_db(client):
    errors = []
    def worker():
        try:
            for _ in range(10):
                res = client.post("/api/ask", json={"question": "What is licence utilisation this month?", "persona": "manager"})
                assert res.status_code == 200 and res.json()["type"] == "answer" and not res.json().get("error")   # shared sqlite: DB_LOCK
        except Exception as e: errors.append(repr(e))
    ts = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errors and isinstance(S.S.audit_lock, type(threading.Lock()))
    assert len(client.get("/api/audit?limit=-1").json()) == 1 and len(client.get("/api/audit?limit=100000").json()) <= 1000


def test_hostile_persona_is_stored_as_text_and_the_ui_escapes_every_audit_cell(client):
    client.post("/api/ask", json={"question": "What is licence utilisation?", "persona": "<img src=x onerror=alert(1)>"})
    assert client.get("/api/audit?limit=1").json()[0]["persona"].startswith("guest (requested: <img")
    js = open(os.path.join(ROOT, "app", "static", "app.js"), encoding="utf-8").read()
    row = re.search(r"A\.map\(a => `(<tr>.*?</tr>)`\)", js).group(1)
    cells = re.findall(r"<td>(.*?)</td>", row)
    assert len(cells) == 7 and all(re.fullmatch(r"\$\{esc\(a\.\w+\)\}", c) for c in cells)


def test_ui_never_leaves_a_frozen_bubble():
    js = open(os.path.join(ROOT, "app", "static", "app.js"), encoding="utf-8").read()
    ask = js[js.index("async function ask("):js.index("function chatClick")]
    assert "catch (e2)" in ask and "didn't answer" in ask
    assert ask.index("catch (e2)") < ask.index("m.streaming = false")


# ---------- (2) warm-up: every configured step, clear READY / NOT READY line ----------
@pytest.fixture
def chain(monkeypatch):
    FT.FT_GENERATE = None; FT.SOURCE_COUNTS.clear(); FT._REMOTE_STATE.update(down_until=0.0, last_error="", ok=0, fail=0)
    for k in ("FT_REMOTE_URL", "FT_REMOTE_KEY", "FT_FALLBACK_LOCAL", "FT_MODEL"): monkeypatch.delenv(k, raising=False)
    yield monkeypatch
    FT._REMOTE_STATE.update(down_until=0.0)


def test_warmup_all_warms_remote_and_laptop(chain):
    rs, RH, rurl = make_server("gowtham-nimbuspay-agent-7b"); ls, LH, lurl = make_server("gowtham-nimbuspay-agent")
    try:
        chain.setenv("FT_REMOTE_URL", rurl); chain.setenv("OLLAMA_HOST", lurl)
        w = FT.warmup_all(timeout=5)
        assert isinstance(w["remote"], float) and isinstance(w["local"], float) and w["ready"]
        assert len(RH.bodies) == 1 and len(LH.bodies) == 1                 # generate() alone would have stopped at the remote
        assert w["line"].startswith("READY") and "Modal 7B warm in" in w["line"] and "laptop 1.5B (gowtham-nimbuspay-agent) warm in" in w["line"]
        assert FT.SOURCE_COUNTS == {}                                       # warm-ups are not counted as answers
    finally:
        rs.shutdown(); ls.shutdown()


def test_warmup_all_reports_a_dead_step_and_not_ready(chain):
    ls, LH, lurl = make_server("gowtham-nimbuspay-agent")
    try:
        chain.setenv("FT_REMOTE_URL", "http://127.0.0.1:9"); chain.setenv("OLLAMA_HOST", lurl)
        w = FT.warmup_all(timeout=2)
        assert w["remote"] is None and isinstance(w["local"], float) and w["ready"] and "Modal 7B NOT READY" in w["line"]
    finally:
        ls.shutdown()
    chain.delenv("FT_REMOTE_URL"); chain.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    w = FT.warmup_all(timeout=2)
    assert not w["ready"] and w["remote"] == "off" and w["line"].startswith("NOT READY")


def test_keep_alive_number_is_sent_as_a_number(monkeypatch):
    for v, want in (("-1", -1), ("24h", "24h"), ("300", 300), ("", "30m")):
        monkeypatch.setenv("FT_KEEP_ALIVE", v); assert FT._chat_body("m", [], "route")["keep_alive"] == want
    monkeypatch.delenv("FT_KEEP_ALIVE"); assert FT._chat_body("m", [], "route")["keep_alive"] == "30m"


def test_preflight_ready_with_a_model_and_not_ready_without(hybrid):
    import preflight as PF
    hybrid('{"tool": "freshness", "args": {}}')
    lines = []
    ok, rep = PF.check(questions=[("manager", "can we trust these numbers", "answer", "freshness")], out=lines.append)
    assert ok and lines[-1].startswith("READY") and rep["questions"][0]["intent"] == "freshness" and rep["warnings"] == 0
    hybrid('{"tool": "trend", "args": {}}')
    ok, rep = PF.check(questions=[("manager", "can we trust these numbers", "answer", "freshness")], out=lines.append)
    assert ok and rep["warnings"] == 1 and "WARN" in lines[-2]
    FT.FT_GENERATE = None; os.environ["NP_BRAIN"] = "rules"
    ok, _ = PF.check(out=lines.append)
    assert not ok and lines[-1].startswith("NOT READY")


# ---------- (1) launcher: PowerShell 5.1 safe, demo settings, remote off unless -Remote ----------
def test_run_demo_ps1_is_powershell_51_safe_and_sets_the_demo_settings():
    raw = open(os.path.join(ROOT, "run_demo.ps1"), "rb").read()
    raw.decode("ascii")                                                     # PS 5.1 reads BOM-less files as ANSI: ASCII only
    s = raw.decode()
    code = "\n".join(l for l in s.splitlines() if not l.strip().startswith("#"))
    assert "&&" not in code and "||" not in code and "?." not in code and " ? " not in code
    for k, v in (("NP_BRAIN", "finetuned"), ("FT_MODEL", "gowtham-nimbuspay-agent"), ("FT_KEEP_ALIVE", "24h"), ("FT_TIMEOUT_S", "8"),
                 ("FT_ANSWER", "0"), ("PYTHONUTF8", "1")):
        assert f'$env:{k} = "{v}"' in s, k
    assert "[switch]$Remote" in s and "Remove-Item Env:FT_REMOTE_URL" in s and "Remove-Item Env:FT_REMOTE_KEY" in s
    assert s.index("if ($Remote)") < s.index("Remove-Item Env:FT_REMOTE_URL")
    assert "python tools/preflight.py" in s and "NOT READY" in s and "python -m app" in s and "-Rules" in s
    assert not re.search(r"(FT_REMOTE_KEY|MODAL_TOKEN\w*)\s*=\s*\"", s)    # never a key in the file


def test_demo_script_uses_powershell_the_right_model_and_model_questions():
    import preflight as PF
    d = open(os.path.join(ROOT, "docs", "DEMO_SCRIPT.md"), encoding="utf-8").read()
    assert "qwen2.5:3b" not in d and "NP_BRAIN=rules python" not in d and "gowtham-nimbuspay-agent" in d and "run_demo.ps1" in d
    assert "can we trust these numbers" in d and "Q01 does not" in d
    for _, q, _, _ in PF.MODEL_QUESTIONS: assert q in d, q


# ---------- guard wording: everyday ways to single out people ----------
@pytest.mark.parametrize("q", ["Which three folks use it the least?", "Who on TEAM-A1 hasn't touched the tool?", "rank my colleagues by usage",
                               "which teammates never open the copilot", "who in my team didn't use it this month"])
def test_individual_guard_everyday_wording(base, q):
    r = A.Agent(*base).ask(q, "manager")
    assert r["type"] == "refuse" and r["intent"] == "individual" and r["mode"] == "rules (guard)"


@pytest.mark.parametrize("q, intent", [("how are folks finding the assistant?", None), ("Which teams haven't used it?", "team_usage"),
                                       ("Which team uses it least?", "team_usage")])
def test_individual_guard_wording_keeps_group_questions(base, q, intent):
    r = A.Agent(*base).ask(q, "manager")
    assert r["intent"] != "individual" and (intent is None or r["intent"] == intent)


# ---------- off-domain check inside a session ----------
def test_off_domain_question_in_a_session_is_not_trusted_to_a_data_tool(hybrid, base):
    hybrid('{"tool": "m01", "args": {}}')                                 # a model that routes everything to M01
    ag = A.Agent(*base)
    for q in ("tell me a joke about cats", "write me a poem", "what is the capital of France?"):
        r = ag.ask(q, "manager", prev="What is licence utilisation this month?")
        assert r["type"] == "refuse" and r["intent"] == "unmatched" and r["fallback_reason"] == "off-domain model route ignored", q


def test_follow_up_shaped_questions_in_a_session_still_reach_the_model(hybrid, base):
    g = hybrid('{"tool": "m01", "args": {"region": "Region C"}}')
    ag = A.Agent(*base)
    for q in ("pls tell me and in C??", "hi! and in C", "why?"):
        r = ag.ask(q, "manager", prev="What is utilisation in Region A?")
        assert r["intent"] == "M01" and r["mode"].startswith("Fine-tuned"), q
    assert A.looks_followup("what about that one?") and not A.looks_followup("tell me a joke and a poem")


def test_session_api_off_domain_turn_after_an_answer(hybrid, base):
    hybrid('{"tool": "m01", "args": {}}')
    c = TestClient(S.app); sid = "s-hardening01"
    c.post("/api/load/baseline")
    assert c.post("/api/ask", json={"question": "What is licence utilisation this month?", "persona": "manager", "session_id": sid}).json()["intent"] == "M01"
    r = c.post("/api/ask", json={"question": "tell me a joke about cats", "persona": "manager", "session_id": sid}).json()
    assert r["intent"] == "unmatched"


# ---------- follow-up regression: 'and Region B?' (19 Oct, reported from the UI) ----------
# Root cause: with no usable session (no session_id, or one the validator rejects), 'and Region B?' reached the router with
# no context. Rules said 'unmatched' and the fine-tuned model refused it as out of SCOPE for a Manager, who sees every region.
def test_follow_up_region_in_a_session_still_resolves(client):
    sid = "s-regression-followup-0001"
    client.post("/api/load/baseline")
    for persona in ("manager", "executive"):
        assert client.post("/api/ask", json={"question": "What is licence utilisation?", "persona": persona, "session_id": sid + persona}).json()["intent"] == "M01"
        r = client.post("/api/ask", json={"question": "and Region B?", "persona": persona, "session_id": sid + persona}).json()
        assert r["type"] == "answer" and r["intent"] == "M01" and "Region B" in r["text"]
        assert r["followup"]["interpreted_as"] == "What is licence utilisation for Region B?"


@pytest.mark.parametrize("q", ["and Region B?", "And Region B", "what about region b?", "Region B?"])
def test_region_fragment_without_context_asks_which_metric(base, q):
    r = A.Agent(*base).ask(q, "manager")
    assert r["type"] == "clarify" and r["intent"] == "clarify_metric" and "Region B" in r["text"]
    assert any("Region B" in o["q"] for o in r["options"]) and not re.search(r"\d+(\.\d+)?%", r["text"])


def test_region_fragment_out_of_scope_is_still_refused_first(base):
    r = A.Agent(*base).ask("and Region B?", "analyst")
    assert r["type"] == "refuse" and r["intent"] == "scope" and r["mode"] == "rules (guard)"


def test_model_scope_refusal_is_ignored_for_a_role_that_sees_every_region(hybrid, base, monkeypatch):
    monkeypatch.setenv("FT_MODE", "pure")                                  # pure: every question goes to the model
    g = hybrid('{"tool": "refuse", "args": {"reason": "scope"}}')        # what run 3 said for a context-less 'and Region B?'
    ag = A.Agent(*base)
    r = ag.ask("is utilisation any better over in region b", "manager")
    assert g.calls, "the model must have been consulted for this test to mean anything"
    assert r["intent"] != "scope" and "outside your access scope" not in r["text"]
    assert r.get("fallback_reason") == "model scope refusal ignored (this role sees every region)"
    r = ag.ask("is utilisation any better over in region b", "analyst")   # a scoped role: the refusal stands
    assert r["type"] == "refuse" and r["intent"] == "scope"
    assert A.region_fragment("and Region B?", ag.regions()) == "Region B" and A.region_fragment("and Region Z?", ag.regions()) is None
    assert A.region_fragment("What is utilisation in Region B?", ag.regions()) is None


def test_fragment_with_a_valid_session_is_not_intercepted(hybrid, base):
    hybrid('{"tool": "m01", "args": {"region": "Region B"}}')
    r = A.Agent(*base).ask("and Region B?", "manager", prev="What is licence utilisation?")
    assert r["intent"] == "M01" and r["mode"].startswith("Fine-tuned")


# ---------- P1-11: the model correctly saying 'none' is not shown as a failure ----------
def test_model_none_is_labelled_no_governed_match_not_fallback(hybrid, base):
    hybrid('{"tool": "none", "args": {}}')
    r = A.Agent(*base).ask("tell me a joke about cats", "manager")
    assert r["intent"] == "unmatched" and r["mode"].endswith("(no governed match)") and r["mode"].startswith("Fine-tuned")
    assert r["answered_by"] != "rules" and "fallback_reason" not in r


# ---------- P1-6 structured logs; P1-9 read-only public mode; P1-10 no model eval during the demo ----------
def test_one_structured_log_line_per_ask_without_the_question_text(client, caplog):
    import logging
    S.LOG.propagate = True
    try:
        with caplog.at_level(logging.INFO, logger="nimbuspay"):
            client.post("/api/ask", json={"question": "What is licence utilisation this month?", "persona": "manager"})
    finally:
        S.LOG.propagate = False
    line = [r.getMessage() for r in caplog.records if r.name == "nimbuspay" and r.getMessage().startswith("ask ")][-1]
    d = json.loads(line[4:])
    assert d["intent"] == "M01" and d["persona"] == "manager" and "latency_ms" in d and "utilisation" not in line


def test_model_step_failure_is_logged_with_the_error_type_only(chain, caplog):
    import logging
    chain.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    with caplog.at_level(logging.WARNING, logger="nimbuspay.model"):
        with pytest.raises(Exception): FT.generate(FT.route_messages("x", "manager"), "route", timeout=1)
    assert any("step=local" in r.getMessage() and "error=" in r.getMessage() for r in caplog.records)


def test_readonly_public_mode_blocks_load_and_upload(client, monkeypatch):
    monkeypatch.setenv("NP_READONLY_PUBLIC", "1")
    assert client.post("/api/load/baseline").status_code == 403
    assert client.post("/api/upload", files={k: (k + ".csv", io.BytesIO(b"a"), "text/csv") for k in ("events", "seats", "registry")}).status_code == 403
    assert client.post("/api/ask", json={"question": "What is licence utilisation?", "persona": "manager"}).status_code == 200
    monkeypatch.delenv("NP_READONLY_PUBLIC")
    assert client.post("/api/load/baseline").status_code == 200


def test_demo_mode_refuses_a_live_model_eval(client, monkeypatch):
    monkeypatch.setenv("NP_DEMO", "1")
    r = client.post("/api/models/run/finetuned")
    assert r.status_code == 409 and "live demo" in r.json()["detail"]
    assert '$env:NP_DEMO = "1"' in open(os.path.join(ROOT, "run_demo.ps1"), encoding="utf-8").read()
