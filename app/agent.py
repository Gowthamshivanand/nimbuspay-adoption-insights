"""Adoption Insights Agent. READ-ONLY. Zero-cost default: a deterministic intent router + templates over the
governed metrics, executing real SQL on the local warehouse. Every answer cites metric ID + version + data-as-of
and shows the SQL. Unsafe asks are refused with a safe alternative. Optional LLM mode (env key) only picks an
intent from the governed tool list; guards always run first and numbers always come from SQL, never the LLM."""
import json, os, re, urllib.request
from . import config as C

PERSONAS = {
    "executive": dict(label="Executive", regions=None),
    "regional_lead": dict(label="Regional lead (Region A)", regions=["Region A"]),
    "platform_engineer": dict(label="Platform engineer", regions=None),
    "fraud_ops_lead": dict(label="Fraud operations lead (Region A)", regions=["Region A"]),
    "finance": dict(label="Finance and Procurement", regions=None),
}
WRITE = r"\b(retire|delete|remove|disable|update|change|modify|drop table|insert|grant|revoke|turn off|shut down|reassign|send|email (them|him|her))\b"
PII = r"(card number|\bpan\b|cvv|aadhaar|account number|phone number|email address|home address|raw events?|\buser-\d+|password)"
INDIVIDUAL = r"(which (analysts?|users?|people|employees|staff|agents? users?)|who (uses|is using|used)|use the assistant least|least active (person|people|users?)|name the|rank (the )?(analysts|people|users|employees)|individual (usage|performance))"
FORECAST = r"(next (quarter|month|year)|will (be|it|utili[sz]ation)|forecast|predict|projection|going to be)"
CAUSAL = r"(\bcause[ds]?\b|caused|because of the (agent|ai)|did the .* (make|lead to|drive)|impact of the agent on)"
UNGOVERNED = r"(sentiment|happiness|productivity score|\broi\b|morale|nps|engagement score|lines of code)"


def _sql(db, sql, args=()):
    cur = db.execute(sql, args); return cur.fetchall()


def _scope(persona):
    return PERSONAS.get(persona, PERSONAS["executive"])["regions"]


def _scope_sql(regions, col="region"):
    if not regions: return "", ()
    return f" AND {col} IN ({','.join('?' * len(regions))})", tuple(regions)


class Agent:
    def __init__(self, result, db):
        self.r, self.db = result, db
        self.metrics = {m: v for m, v in result["metrics"].items()}

    # ---------- helpers ----------
    def _resp(self, kind, text, metrics=(), sql="", alt=None, intent="", rows=None):
        return dict(type=kind, text=text, intent=intent, safe_alternative=alt, sql=sql.strip() or None, rows=rows,
                    citations=[dict(metric=m, version=C.METRIC_VERSION, data_as_of=self.r["data_as_of"]) for m in metrics],
                    data_as_of=self.r["data_as_of"], label="Synthetic data", read_only=True)

    def refuse(self, why, alt, metrics=(), intent="refuse"):
        return self._resp("refuse", why, metrics, alt=alt, intent=intent)

    # ---------- guards (always deterministic, run before any intent or LLM) ----------
    def guards(self, q, persona):
        ql = q.lower()
        if re.search(WRITE, ql):
            return self.refuse("I can't do that: I am read-only and never change agents, seats, data or settings.",
                               "I can show this agent's usage, reliability and owner from the registry so the owner can decide and act through change control.", ["M16", "M10"], "write")
        if re.search(PII, ql):
            return self.refuse("I can't show raw events, user-level records or personal or card data. Raw PII never leaves the masked zone.",
                               "I can give aggregate, governed figures instead, for example licence utilisation (M01) or interactions per active user (M04) by region.", ["M01", "M04"], "pii")
        if re.search(INDIVIDUAL, ql):
            return self.refuse("I can't rank or single out individual people. Adoption metrics are for improving the product and enablement, not monitoring staff.",
                               "I can show team or region-level utilisation (M01) and habitual users (M02) for groups of at least %d people." % C.MIN_GROUP, ["M01"], "individual")
        m = re.search(r"team of (\d+)|(\d+)[- ]person team|team with (\d+)", ql)
        if m and int(next(g for g in m.groups() if g)) < C.MIN_GROUP:
            return self.refuse(f"I can't report a group smaller than {C.MIN_GROUP} people: it could identify individuals.",
                               "I can show the figure at region level, or for the team once it has at least %d assigned seats." % C.MIN_GROUP, ["LF4"], "small_group")
        regions = _scope(persona)
        if regions:
            asked = set(re.findall(r"region [a-z]\b", ql))
            outside = "outside my region" in ql or "other region" in ql or "another market" in ql or "outside my market" in ql
            if outside or any(a.title() not in [x.split(" (")[0] for x in regions] for a in asked):
                return self.refuse("That market is outside your access scope. Row-level security follows your SSO role (%s)." % ", ".join(regions),
                                   "I can show the same metric for your own region, or the company-wide total that renewal uses. Ask your sponsor for wider access if needed.", ["M01"], "scope")
        if re.search(FORECAST, ql):
            return self.refuse("I don't forecast. Governed metrics describe the closed period only; a forecast would be a guess presented as a fact.",
                               "I can show the current figure and its change versus the previous closed period when one exists.", ["M01"], "forecast")
        if re.search(CAUSAL, ql):
            return self.refuse("I can't say the agent caused that. Usage data shows correlation only; cause needs the agreed study (staggered rollout or holdout).",
                               "I can show the M09 study design and the before/after figures with their caveat, or the adoption trend for that workflow.", ["M09"], "causal")
        if re.search(UNGOVERNED, ql):
            return self.refuse("That isn't a governed metric, so I won't compute it on the fly.",
                               "Governed alternatives: M01 utilisation, M02 habitual users, M04 interactions per active user, M17 verified hours, M19 value score. Propose new metrics to the metric owner (cap of 25).", [], "ungoverned")
        return None

    # ---------- intents ----------
    def m01(self, q, persona):
        reg = _scope(persona); w, a = _scope_sql(reg)
        sql = f"SELECT SUM(active) AS active, SUM(assigned) AS assigned,\n  ROUND(100.0*SUM(active)/SUM(assigned),1) AS m01_pct\nFROM user_funnel WHERE assigned = 1{w};"
        act, asg, v = _sql(self.db, sql, a)[0]
        sc = f" for {', '.join(reg)}" if reg else ""
        return self._resp("answer", f"Licence utilisation{sc} is {v}% ({act} active users / {asg} assigned seats). Active = at least one qualifying interaction in the 28-day period.",
                          ["M01"], sql.replace("?", repr(reg[0]) if reg else "?"), intent="M01")

    def define_m01(self, q, persona):
        return self._resp("answer", "M01 Licence utilisation = Active users (LF4) / Assigned seats (LF2). Active means at least one qualifying interaction (an agent run that returned a response) in the 28-day period. Logins never count. Version " + C.METRIC_VERSION + ", working definition to agree.", ["M01"], intent="define_M01")

    def m02_regions(self, q, persona):
        reg = _scope(persona); w, a = _scope_sql(reg)
        sql = f"SELECT region, SUM(habitual) AS habitual, SUM(assigned) AS assigned,\n  ROUND(100.0*SUM(habitual)/SUM(assigned),1) AS m02_pct\nFROM user_funnel WHERE assigned = 1{w}\nGROUP BY region HAVING SUM(assigned) >= {C.MIN_GROUP} ORDER BY m02_pct DESC;"
        rows = _sql(self.db, sql, a)
        txt = "; ".join(f"{r[0]}: {r[3]}% ({r[1]}/{r[2]})" for r in rows)
        return self._resp("answer", f"Habitual users (active in 3+ of 4 weeks) by market: {txt}.", ["M02"], sql, intent="M02", rows=rows)

    def cohort(self, q, persona):
        sql = "SELECT region, SUM(assigned) AS lf2, SUM(provisioned) AS lf3, SUM(active) AS lf4, SUM(engaged) AS lf5, SUM(habitual) AS lf6\nFROM user_funnel WHERE region LIKE '%launch%'\nGROUP BY region;"
        rows = _sql(self.db, sql)
        if not rows:
            return self._resp("caveat", "No launch cohort is tagged in this data set.", ["LF4"], sql, intent="cohort")
        newest = sorted(rows, key=lambda r: ("new country" not in r[0].lower(), r[0]))[0]
        r = newest
        return self._resp("answer", f"{r[0]} funnel: assigned {r[1]} -> provisioned {r[2]} -> active {r[3]} -> engaged {r[4]} -> habitual {r[5]} (utilisation {round(100*r[3]/r[1],1) if r[1] else 'n/a'}%). It is still ramping, so judge it against its launch date, not mature markets.",
                          ["LF2", "LF4", "LF6", "M01"], sql, intent="cohort", rows=rows)

    def m11(self, q, persona):
        sql = "SELECT agent_id, COUNT(*) AS calls, SUM(status='failed') AS failed,\n  ROUND(100.0*SUM(status='failed')/COUNT(*),1) AS m11_pct\nFROM events_clean WHERE event_type = 'connector_call'\nGROUP BY agent_id ORDER BY m11_pct DESC;"
        rows = _sql(self.db, sql)
        top = rows[0]
        return self._resp("answer", f"Highest connector failure rate: connector calls from {top[0]} at {top[3]}% ({top[2]}/{top[1]}). Overall M11 is {self.metrics['M11']['value']}%. (This synthetic log records the calling agent, not the connector name.)",
                          ["M11"], sql, intent="M11", rows=rows)

    def m16(self, q, persona):
        sql = "SELECT DISTINCT e.agent_id, r.build_type_used\nFROM events_clean e JOIN agent_registry r ON r.agent_id = e.agent_id\nWHERE e.event_type <> 'login' AND r.registered = 0;"
        rows = _sql(self.db, sql)
        names = ", ".join(f"{a} (build type backfilled as {b}, owner to confirm)" for a, b in rows) or "none"
        return self._resp("answer", f"{len(rows)} unregistered agent(s) are active in the logs: {names}.", ["M16"], sql, intent="M16", rows=rows)

    def why_drop(self, q, persona):
        sql = "SELECT u.region, ROUND(100.0*SUM(u.active)/SUM(u.assigned),1) AS m01_pct,\n  (SELECT ROUND(100.0*SUM(status='failed')/COUNT(*),1) FROM events_clean e\n   WHERE e.event_type='connector_call' AND e.region=u.region) AS m11_pct\nFROM user_funnel u WHERE u.assigned = 1 GROUP BY u.region;"
        rows = _sql(self.db, sql)
        txt = "; ".join(f"{r[0]}: M01 {r[1]}%, M11 {r[2]}%" for r in rows)
        return self._resp("caveat", f"This data set holds one closed period, so I can't show a drop versus a prior period. What I can show side by side: {txt}. Where connector failures are higher, utilisation tends to be lower, but that is a correlation, not a proven cause. Confirm with the regional lead and the connector incident log.",
                          ["M01", "M11"], sql, intent="why_drop", rows=rows)

    def m19(self, q, persona):
        s = self.r["score"]; p = s["pillars"]
        pil = ", ".join(f"{k} {v if v is not None else 'no data'} (weight {s['weights'][k]})" for k, v in p.items())
        if s["state"] == "withheld":
            return self.refuse(f"I can't give an AI value score: the Outcome pillar has no verified data, and I don't fill gaps silently. Pillars: {pil}.",
                               f"The interim adoption and health index is {s['interim_index']}/100 (Reach 33, Depth 25, Reliability 25, Trust 17), labelled interim. Verified hours will unlock M19.", ["M19"], "M19")
        red = " It is shown RED because of a critical-risk override: " + self.r["critical_risk"] + "." if s["state"] == "red" else ""
        return self._resp("answer", f"AI value score M19 is {s['value']}/100. Pillars: {pil}.{red} Read it beside its pillars; it is not a team target.", ["M19"], intent="M19")

    def m17(self, q, persona):
        m = self.metrics["M17"]
        if m["value"] is None:
            return self.refuse("I can't state hours saved: there is no verified study result for this period (" + m["note"] + "). Usage time is not time saved.",
                               "I can show the M06 study design and current usage (M04) so you can see where a study is ready to run.", ["M17"], "M17")
        return self._resp("answer", f"Verified hours saved (M17) are {m['value']:g} hours per week, from the agreed study, synthetic input.", ["M17"], intent="M17")

    def m18(self, q, persona):
        m = self.metrics["M18"]
        if m["value"] is None:
            return self.refuse("I can't give cost per verified hour: it needs verified hours (M17), which are missing or not attributable.",
                               "I can show the M18 formula and which input is missing.", ["M18", "M17"], "M18")
        return self._resp("answer", f"Cost per verified hour (M18) is an index of {m['value']} versus the current process (1.0 = parity). Platform cost is a placeholder input, not a NimbusPay figure.", ["M18"], intent="M18")

    def m10(self, q, persona):
        sql = "SELECT substr(event_time,1,10) AS day, COUNT(*) AS runs, SUM(status='failed') AS failed,\n  ROUND(100.0*SUM(status='failed')/COUNT(*),1) AS m10_pct\nFROM events_clean WHERE event_type = 'agent_run'\nGROUP BY day ORDER BY day DESC LIMIT 1;"
        day, runs, failed, v = _sql(self.db, sql)[0]
        return self._resp("caveat", f"On the latest day with data ({day}) the agent error rate was {v}% ({failed}/{runs} runs). Caveat: data is as of {self.r['data_as_of']}, {self.r['quality']['late']} events arrived late this period and {self.r['quality']['after_close']} arrived after close, so the latest day can still change. Period M10 is {self.metrics['M10']['value']}%.",
                          ["M10", "M12"], sql, intent="M10")

    def mau(self, q, persona):
        u = self.r["users"]
        return self._resp("caveat", f"No. MAU counts anyone with a logged event, logins included ({u['vendor_mau_proxy']} users here), but only {len(u['active'])} were active and {len(u['habitual'])} habitual. More logins is not more value; value needs verified outcomes (M17) and the full M19 with its pillars.",
                          ["M01", "M02", "M19"], intent="mau")

    def why_low(self, q, persona):
        s = self.r["score"]
        state = "withheld (no verified Outcome data)" if s["state"] == "withheld" else f"{s['value']}/100"
        return self.refuse(f"I can't explain why the score is 'low': that assumes a judgement and a cause I can't verify. The current M19 is {state}.",
                           "I can show each pillar against its baseline and target, so you can see which inputs move it.", ["M19"], "why_low")

    def funnel(self, q, persona):
        f = self.r["funnel"]
        return self._resp("answer", f"Licence funnel: purchased {f['LF1']} -> assigned {f['LF2']} -> provisioned {f['LF3']} -> active {f['LF4']} -> engaged {f['LF5']} -> habitual {f['LF6']}. {self.r['paid_unused']} paid seats have no qualifying use ({self.r['never_assigned']} never assigned, {self.r['assigned_unused']} assigned but unused).",
                          ["LF1", "LF2", "LF3", "LF4", "LF5", "LF6"], "SELECT SUM(assigned), SUM(provisioned), SUM(active), SUM(engaged), SUM(habitual) FROM user_funnel;", intent="funnel")

    def counting(self, q, persona):
        g = self.r["grouping"]
        sql = "SELECT method, COUNT(*) AS interactions, SUM(qualifying) AS qualifying FROM interactions GROUP BY method;"
        return self._resp("answer", f"{self.r['quality']['clean_events']} clean events became {g['interactions']} logical interactions ({g['exact']} exact by interaction ID, {g['approximate']} approximate by sessionisation, {C.SESSION_GAP_S} s gap); {g['qualifying']} qualify. Counting raw non-login events would overstate use {g['inflation']}x.",
                          ["M04", "M20"], sql, intent="counting", rows=_sql(self.db, sql))

    def renewal(self, q, persona):
        rn = self.r["renewal"]
        return self._resp("answer", f"Recommended renewal outcome: {rn['outcome']}. {rn['why']} Evidence: utilisation {rn['evidence']['e1']}, verified impact {rn['evidence']['e2']}, unit economics {rn['evidence']['e3']}, reliability and governance {rn['evidence']['e4']}. Thresholds are placeholders agreed in advance.",
                          ["M01", "M17", "M18", "M10", "M11"], intent="renewal")

    def m20(self, q, persona):
        return self._resp("answer", f"Events without an interaction ID (M20): {self.metrics['M20']['value']}% overall. {self.metrics['M20']['note']}. Those interactions are grouped by sessionisation and labelled approximate.", ["M20"], intent="M20")

    def m04(self, q, persona):
        m = self.metrics["M04"]
        return self._resp("caveat" if m["approximate"] else "answer", f"Interactions per active user (M04) is {m['value']} ({m['note']}).{' Partly approximate: some interactions are sessionised.' if m['approximate'] else ''}", ["M04"], intent="M04")

    INTENTS = [
        (r"how is .*utili[sz]ation defined|define .*utili[sz]ation|definition of .*utili[sz]ation", "define_m01"),
        (r"why .*(value score|m19|score).*(low|bad|poor)", "why_low"),
        (r"why .*(drop|fall|fell|declin)", "why_drop"),
        (r"mau.*(doubl|up|grew|increas)|doubl.*mau", "mau"),
        (r"habitual", "m02_regions"),
        (r"newest country|new country|launch|cohort", "cohort"),
        (r"connector", "m11"),
        (r"unregistered|registry", "m16"),
        (r"value score|m19|ai score", "m19"),
        (r"hours.*sav|time saved|m17", "m17"),
        (r"cost per|m18|unit cost", "m18"),
        (r"error rate|m10|errors|failed runs", "m10"),
        (r"renew|renewal|recommend", "renewal"),
        (r"funnel|seats|shelfware|unused", "funnel"),
        (r"interaction id|m20|sessionis|sessioniz", "m20"),
        (r"how (do|are) .*count|interactions? (count|total)|how many interactions|overstat|events", "counting"),
        (r"per active user|m04|depth", "m04"),
        (r"utili[sz]ation|m01|adoption", "m01"),
    ]

    def route(self, q):
        ql = q.lower()
        for pat, fn in self.INTENTS:
            if re.search(pat, ql): return fn
        return None

    def ask(self, q, persona="executive"):
        g = self.guards(q, persona)                      # safety guards are ALWAYS deterministic
        if g:
            g["mode"] = "rules (guard)"; return g
        b = brain()
        fn, mode = None, "rules"
        if b["kind"] != "rules":
            fn = b["route"](q, list(INTENT_HELP))        # the model only picks a governed tool
            if fn: mode = b["label"]
        if not fn:
            fn = self.route(q)                           # automatic fallback: deterministic router
            if b["kind"] != "rules": mode = "rules (fallback)"
        if not fn:
            r = self.refuse("I can only answer from the governed metrics, and I couldn't match your question to one.",
                            "Try: 'What is licence utilisation?', 'Show the licence funnel', 'What is our AI value score?', 'Which connector fails most?', 'What renewal outcome do you recommend?'", [], "unmatched")
        else:
            r = getattr(self, fn)(q, persona)            # numbers come from SQL / pipeline here, never from the model
        r["mode"] = mode
        return r


# One line per governed tool, shown to the model. The model returns a tool name only.
INTENT_HELP = {
    "m01": "licence utilisation value (M01), optionally for a region",
    "define_m01": "how licence utilisation is defined",
    "m02_regions": "habitual users by market/region (M02)",
    "cohort": "newest country / launch cohort funnel",
    "m11": "connector failure rate, which connector fails most (M11)",
    "m16": "unregistered agents (M16)",
    "why_drop": "why utilisation dropped somewhere (correlation with caveat)",
    "m19": "AI value score (M19) and its pillars",
    "m17": "hours saved by AI (M17)",
    "m18": "cost per verified hour (M18)",
    "m10": "agent error rate (M10), recent days",
    "mau": "MAU went up so did value go up (wrong assumption)",
    "why_low": "why the AI value score is low (presupposition)",
    "funnel": "licence funnel, seats, shelfware, unused seats",
    "counting": "how interactions are counted, events vs interactions",
    "renewal": "renewal recommendation / outcome",
    "m20": "events without interaction ID (M20)",
    "m04": "interactions per active user (M04)",
}

_BRAIN = {"t": 0, "v": None}


def _http_json(url, body=None, headers=None, timeout=20):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def ollama_host():
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/").replace("0.0.0.0", "127.0.0.1")


def ollama_model():
    return os.environ.get("OLLAMA_MODEL", "qwen2.5:3b-instruct")


def _ollama_ready():
    """True if the Ollama server answers and the configured model is pulled."""
    try:
        h = ollama_host(); h = h if h.startswith("http") else "http://" + h
        tags = _http_json(h + "/api/tags", timeout=1.0)
        names = {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}
        want = ollama_model()
        return want in names or (want + ":latest") in names
    except Exception:
        return False


def ollama_route(q, intents):
    """Ask the local open model to choose ONE governed tool. Structured output constrains it to the tool list."""
    h = ollama_host(); h = h if h.startswith("http") else "http://" + h
    tools = "\n".join(f"- {k}: {INTENT_HELP[k]}" for k in intents)
    body = {"model": ollama_model(), "stream": False, "options": {"temperature": 0},
            "format": {"type": "object", "properties": {"tool": {"type": "string", "enum": intents + ["none"]}}, "required": ["tool"]},
            "messages": [{"role": "system", "content": "You route questions about AI adoption metrics to exactly one governed tool. "
                          "Reply with JSON {\"tool\": <name>} using a name from this list, or \"none\" if nothing fits. Never answer the question yourself.\n" + tools},
                         {"role": "user", "content": q}]}
    try:
        out = _http_json(h + "/api/chat", body, timeout=float(os.environ.get("OLLAMA_TIMEOUT", "20")))
        t = json.loads(out["message"]["content"]).get("tool")
        return t if t in intents else None
    except Exception:
        return None


def llm_enabled():
    return bool(os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def brain(refresh=False):
    """Pick the active brain: NP_BRAIN=rules|ollama|openai|auto (default auto).
    auto: local open model via Ollama if reachable, else an OpenAI-compatible key if set, else rules. Cached 30 s."""
    import time
    pref = os.environ.get("NP_BRAIN", "auto").lower()
    if not refresh and _BRAIN["v"] and time.time() - _BRAIN["t"] < 30 and _BRAIN["v"]["pref"] == pref:
        return _BRAIN["v"]
    v = dict(kind="rules", label="Rules engine", route=None, pref=pref)
    if pref in ("auto", "ollama") and _ollama_ready():
        v = dict(kind="ollama", label=f"Open model ({ollama_model()} via Ollama)", route=ollama_route, pref=pref)
    elif pref in ("auto", "openai") and llm_enabled():
        v = dict(kind="openai", label=f"LLM router ({os.environ.get('LLM_MODEL', 'gpt-4o-mini')})", route=llm_route, pref=pref)
    _BRAIN.update(t=time.time(), v=v)
    return v


def brain_info():
    b = brain()
    return dict(kind=b["kind"], label=b["label"], ollama_host=ollama_host(), ollama_model=ollama_model())


def llm_route(q, intents):
    """Optional: any OpenAI-compatible endpoint picks ONE governed tool via a tool call. Returns None on any failure."""
    key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    tool = {"type": "function", "function": {"name": "governed_metric", "description": "Answer using exactly one governed metric tool.",
            "parameters": {"type": "object", "properties": {"intent": {"type": "string", "enum": intents + ["none"]}}, "required": ["intent"]}}}
    body = {"model": model, "temperature": 0, "tools": [tool], "tool_choice": {"type": "function", "function": {"name": "governed_metric"}},
            "messages": [{"role": "system", "content": "Map the user's question to one governed metric tool, or 'none'. Never answer yourself.\n" +
                          "\n".join(f"- {k}: {INTENT_HELP[k]}" for k in intents)},
                         {"role": "user", "content": q}]}
    try:
        out = _http_json(base + "/chat/completions", body, {"Authorization": "Bearer " + key}, timeout=12)
        args = json.loads(out["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])
        return args["intent"] if args.get("intent") in intents else None
    except Exception:
        return None
