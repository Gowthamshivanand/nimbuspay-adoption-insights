"""Conversation layer around Agent.ask: follow-up questions, confidence + clarifying questions, transparency fields.
Every turn still goes through Agent.ask, so the code guards and the role check run on EVERY turn. The session only
remembers the previous question and which governed tool answered it; it never stores or carries a role or permission."""
import os, re, threading, time
from . import agent as A

TTL_S = float(os.environ.get("NP_SESSION_TTL", "900"))         # follow-up context expires after 15 min idle
MAX_SESSIONS = 500
CONFIDENCE_MIN = float(os.environ.get("NP_CONFIDENCE_MIN", "0.5"))
SID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

# One canonical, askable question per governed tool: used for clarifying-question options.
CANON = {"m01": "What is licence utilisation this month?", "define_m01": "How is licence utilisation defined?",
         "m02_regions": "Compare habitual users across my markets", "cohort": "How is the newest country doing since launch?",
         "m11": "Which connector has the highest failure rate this week?", "m16": "How many agents are unregistered?",
         "why_drop": "Why did licence utilisation drop in launch cohort 2?", "m19": "What is our AI value score?",
         "m17": "How many hours did AI save us this quarter?", "m18": "What is our cost per verified hour?",
         "m10": "What was agent error rate yesterday?", "mau": "Why is vendor MAU higher than our active users?",
         "why_low": "Why is our AI value score so low?", "funnel": "Show the licence funnel and unused seats",
         "counting": "How are interactions counted?", "renewal": "What renewal outcome do you recommend?",
         "m20": "How many events have no interaction ID?", "m04": "How many interactions per active user?",
         "agent_health": "Is the KYC agent working?", "agent_value": "Is the fraud agent saving analysts time?",
         "reliability": "How reliable are our agents?", "agent_usage": "Which agents are used the most?",
         "build_compare": "Compare engineer-built and drag-and-drop agents", "team_usage": "Which team uses it least?",
         "region_compare": "Which region has the best adoption?", "trend": "Is usage going up or down?",
         "freshness": "Is our data up to date?", "alerts": "What should leadership worry about?",
         "reclaim": "Which seats can we take back at renewal?", "outcome": "What is the task success rate?"}

FOLLOW = r"^\W*(and|also|plus|then|now|ok(ay)?|what about|how about|same (for|but)|and what about|and how about)\b"
TIME_SLOT = r"\b(last|previous|prior) (month|quarter|period|week|year)\b|\bmonth before\b|\bvs\.? last\b"
VAGUE_AGENT = r"\b(the|this|that|our|my|your) (ai )?(agent|assistant|bot|copilot)\b(?!s)"
HEALTH_WORDS = r"(working|doing|healthy|reliab|\bok\b|okay|fail|error|broken|breaking)"
AGENT_TOOLS = ("agent_health", "agent_value")


def intent_of(fn):
    """The `intent` label a governed tool puts on its answer (the tools label themselves this way)."""
    if not fn: return None
    if fn == "define_m01": return "define_M01"
    if fn == "m02_regions": return "M02"
    return fn.upper() if re.fullmatch(r"m\d\d", fn) else fn


FN_OF = {intent_of(f): f for f in CANON}


class Sessions:
    """Small in-memory store: session_id -> previous answered question + tool. TTL and size-capped."""
    def __init__(self, ttl=TTL_S, cap=MAX_SESSIONS):
        self.ttl, self.cap, self.d, self.lock = ttl, cap, {}, threading.Lock()

    def get(self, sid):
        if not sid: return None
        with self.lock:
            v = self.d.get(sid)
            if v and time.time() - v["ts"] > self.ttl:
                self.d.pop(sid, None); return None
            return dict(v) if v else None

    def put(self, sid, q, fn):
        if not sid: return
        with self.lock:
            if len(self.d) >= self.cap and sid not in self.d:
                for k in sorted(self.d, key=lambda k: self.d[k]["ts"])[: max(1, self.cap // 10)]: self.d.pop(k, None)
            self.d[sid] = dict(q=q, fn=fn, ts=time.time())

    def clear(self, sid=None):
        with self.lock:
            (self.d.pop(sid, None) if sid else self.d.clear())


STORE = Sessions()


def valid_sid(sid):
    return sid if isinstance(sid, str) and SID.match(sid) else None


def route_scored(agent, q):
    """Deterministic router + a confidence from match quality: a specific (first-pass) pattern or a named agent is strong;
    a general pattern loses 0.1 for each other governed tool that also matched (floor 0.6); no match is 0."""
    ql = q.lower(); fn = agent.route(q)
    if not fn: return None, 0.0
    if any(re.search(p, ql) for p, f in agent.INTENTS_FIRST if f == fn): return fn, 0.95
    if fn in AGENT_TOOLS and agent._agent_in(ql): return fn, 0.9
    others = {f for p, f in agent.INTENTS_FIRST + agent.INTENTS if f != fn and re.search(p, ql)}
    return fn, round(max(0.6, 0.85 - 0.1 * len(others)), 2)


def _clarify(agent, text, options, conf, intent="clarify"):
    r = agent._resp("clarify", text, intent=intent)
    r.update(options=options[:3], confidence=conf, mode="rules (clarify)", brain="rules")
    return r


def _agent_options(agent, make_q):
    ids = [a for a in ("AG-FRAUD-01", "AG-KYC-04", "AG-ONB-02") if a in agent.agents]
    return [dict(label=f"{agent.agents[a]['name']} ({a})", q=make_q(a)) for a in ids[:3]]


def needs_clarify(agent, q, fn):
    """Missing required slot: a question about ONE unnamed agent ('is the agent saving time?'). Ask which one."""
    ql = q.lower()
    if fn in AGENT_TOOLS + ("m17", "reliability", "m10") and re.search(VAGUE_AGENT, ql) and not agent._agent_in(ql) \
            and (re.search(A.VALUE_WORDS, ql) or re.search(HEALTH_WORDS, ql)):
        opts = _agent_options(agent, lambda a: re.sub(VAGUE_AGENT, a, q, count=1, flags=re.I))
        if opts: return _clarify(agent, "Which agent do you mean? I won't guess, because the answer differs by agent.", opts, 0.4, "clarify_agent")
    return None


def _agent_slot(agent, ql):
    for aid in agent.agents:
        if aid.lower() in ql: return aid
    for pat, aid in A.AGENT_ALIAS:
        if re.search(pat, ql) and aid in agent.agents: return aid
    return None


def followup(agent, q, prev):
    """If q is a follow-up to prev ('and Region B?', 'what about the KYC agent?', 'what about last month?'), return
    (rewritten question, kind) or a ready clarify response. Otherwise None: the question stands on its own."""
    if not prev: return None
    ql = q.lower().strip()
    short = len(re.findall(r"[a-z0-9]+", ql)) <= 6
    if not (re.search(FOLLOW, ql) or (short and not agent.route(q))): return None
    if agent.route(re.sub(FOLLOW, "", ql)) and not short: return None       # a full new question, not a follow-up
    pq, pfn = prev["q"], prev["fn"]
    regions, aid = A._regions_in(ql), _agent_slot(agent, ql)
    if re.search(TIME_SLOT, ql): return (pq, "time")
    if regions:
        reg = ", ".join(regions)
        if pfn == "m01":
            base = re.sub(r"\s*\b(for|in)?\s*region [a-z]\b", "", pq, flags=re.I).rstrip(" ?.")
            return (f"{base} for {reg}?", "region")
        return _clarify(agent, f"Region filtering is available for licence utilisation (M01). For {reg}, which do you want?",
                        [dict(label=f"Licence utilisation for {reg}", q=f"What is licence utilisation for {reg}?"),
                         dict(label="Compare all markets I can see", q="Which region has the best adoption?")], 0.45, "clarify_followup")
    if aid:
        verb = "saving time" if pfn == "agent_value" or pfn == "m17" else "working"
        return (f"Is {aid} {verb}?", "agent")
    return None


def respond(agent, q, persona=None, session_id=None, store=STORE):
    """One conversational turn. Adds: confidence, brain, latency_ms, sql_executed, row_count, followup, session_id."""
    t0 = time.perf_counter(); sid = valid_sid(session_id)
    persona = A.resolve_persona(persona)
    prev = store.get(sid)
    asked, fu_kind, r = q, None, None
    fu = followup(agent, q, prev)
    if isinstance(fu, dict): r = fu
    elif fu: asked, fu_kind = fu
    A.SQL_TRACE.rows = []
    try:
        if r is None:
            guard = agent.guards(asked, persona)
            rfn, rconf = route_scored(agent, asked)
            if not guard and persona != A.LEAST_PRIVILEGE:
                r = needs_clarify(agent, asked, rfn)
            if r is None:
                r = agent.ask(asked, persona)              # guards + role check run here, on every turn
                if r["mode"] == "rules (guard)" or r["intent"] == "no_role":
                    conf, basis = 1.0, "deterministic code guard / role check"
                elif r["intent"] == "unmatched":
                    conf, basis = 0.0, "no governed tool matched"
                elif r["mode"].startswith("rules"):
                    conf, basis = rconf, "rules match quality"
                elif isinstance(r.get("confidence"), (int, float)):
                    conf, basis = r["confidence"], "model-reported"
                else:
                    same = intent_of(rfn) == r["intent"]
                    conf = 0.95 if same else (0.6 if not rfn else 0.45)
                    basis = "model and rules agree" if same else ("model only (rules found no match)" if not rfn else "model and rules disagree")
                    mfn = FN_OF.get(r["intent"])
                    if conf < CONFIDENCE_MIN and mfn and rfn and mfn != rfn and r["type"] != "refuse":
                        r = _clarify(agent, "I'm not sure which governed metric you mean. Pick one:",
                                     [dict(label=A.INTENT_HELP[f], q=CANON[f]) for f in (mfn, rfn) if f in CANON], conf)
                r.setdefault("confidence", conf); r["confidence"] = r["confidence"] if r["type"] == "clarify" else conf
                r["confidence_basis"] = basis
        executed = list(A.SQL_TRACE.rows or [])
    finally:
        A.SQL_TRACE.rows = None
    if fu_kind == "time" and r["type"] in ("answer", "caveat"):
        r["type"] = "caveat"
        r["text"] = (f"This data set holds one closed 28-day period ({agent.r.get('period')}), so there is no previous period to compare "
                     f"and I won't estimate one. The closed-period figure again: " + r["text"])
    if fu_kind: r["followup"] = dict(previous=prev["q"], interpreted_as=asked, slot=fu_kind)
    r.setdefault("confidence_basis", "clarifying question")
    r["brain"] = r.get("brain") or ("rules" if str(r.get("mode", "rules")).startswith("rules") else A.brain()["kind"])
    r["sql_executed"] = bool(executed) and bool(r.get("sql"))
    r["row_count"] = len(r["rows"]) if isinstance(r.get("rows"), list) else (executed[0] if r["sql_executed"] else None)
    r["persona"] = persona
    if sid:
        r["session_id"] = sid
        if r["type"] in ("answer", "caveat"):
            fn = agent.route(asked) or FN_OF.get(r["intent"])
            if fn: store.put(sid, asked, fn)
    r["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return r
