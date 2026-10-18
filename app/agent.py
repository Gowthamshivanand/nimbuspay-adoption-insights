"""Adoption Insights Agent. READ-ONLY. Deny by default: an unknown or missing role gets the least-privileged persona.
 Zero-cost default: a deterministic intent router + templates over the
governed metrics, executing real SQL on the local warehouse. Every answer cites metric ID + version + data-as-of
and shows the SQL. Unsafe asks are refused with a safe alternative. Optional LLM mode (env key) only picks an
intent from the governed tool list; guards always run first and numbers always come from SQL, never the LLM."""
import json, os, re, threading, urllib.request
from . import config as C
from . import finetuned as FT

PERSONAS = {
    "executive": dict(label="Executive", regions=None),
    "regional_lead": dict(label="Regional lead (Region A)", regions=["Region A"]),
    "platform_engineer": dict(label="Platform engineer", regions=None),
    "fraud_ops_lead": dict(label="Fraud operations lead (Region A)", regions=["Region A"]),
    "finance": dict(label="Finance and Procurement", regions=None),
    # Demo roles for the on-screen role switch. Scope is enforced here, server-side, never in the UI.
    "manager": dict(label="Manager (all regions)", regions=None),
    "analyst": dict(label="Analyst (Region A)", regions=["Region A"]),
    # Deny by default: a missing or unrecognised role gets NO data scope. In production the role is an SSO claim.
    "guest": dict(label="Unrecognised role (least privilege)", regions=[]),
}
LEAST_PRIVILEGE = "guest"
PUBLIC_INTENTS = {"define_m01"}          # the only tools a role-less caller may use: definitions, no data


def resolve_persona(persona):
    """Unknown, empty or missing role -> least-privileged persona. Never fall back to a privileged role."""
    return persona if isinstance(persona, str) and persona in PERSONAS else LEAST_PRIVILEGE


_WV = r"(retire|delete|remove|disable|deactivate|enable|update|change|modify|reassign|unassign|revoke|grant|turn off|switch off|shut down|send|email|notify|cancel|terminate|suspend|pause|block|reset|rename)"
WRITE = (rf"(^\W*(please |kindly |can you |could you |would you |will you |go ahead and |just |now )*{_WV}\b"
         rf"|^\W*i (want|need|would like) (you )?to {_WV}\b|\b{_WV}\b.*\bfor me\b|\b(drop table|insert into|delete from|truncate)\b|\bemail (them|him|her)\b)")
PII = (r"(card number|\bpan\b|cvv|aadhaar|account number|phone number|email address|home address|\buser-\d+|password"
       r"|\b(show|list|give|see|send|display|print|open|read|access|view|get)\b.*\braw (events?|logs?|data)|raw (events?|logs?) (for|of|from|by)\b"
       r"|\b(export|download|dump|extract)\b.*\b(events?|logs?|records?|rows?|data)\b|event[- ]level|user[- ]level (data|records?)|\bprompts?\b|chat (history|logs?)|transcripts?)")
INDIVIDUAL = (r"(which (analysts?|users?|people|persons?|employees?|staff|members?|individuals?|colleagues?|agents? users?)\b"
              r"|who (uses|is using|used|isn'?t using|doesn'?t use|never uses|asks?|asked)\b"
              r"|who (is|are) (the |our )?(least|most|top|bottom|best|worst|laziest|slowest|heaviest|lightest|power)"
              r"|use the assistant least|(least|most) active (person|people|users?|analysts?|employees?|staff)"
              r"|name the|by name|\bnamed\b|rank (the )?(analysts|people|users|employees|staff)|individual"
              r"|(top|bottom) \d* ?(users|analysts|people|employees|performers)|power users?|\blazy\b|slacker|underperform"
              r"|(per|by|each) (employee|analyst|person)\b|by user\b|each user\b"
              r"|which ([\w-]+ )?(analysts?|employees?|staff|people|persons?)\b|(?<!agent )\bnames?\b|seat holders?|\b(inactive|idle) (users|people|employees|analysts|staff)\b"
              r"|\b(list|show|name|identify|find|flag)\b.*\b(users|people|employees|analysts|staff|individuals)\b|(employee|analyst|person|user)[- ]level|\banalysts? (are|is)\b)")
FORECAST = (r"(next (week|quarter|month|year)|\bwill\b.*\b(be|rise|grow|fall|drop|increase|decrease|reach|keep|hit|improve|look|need)\b"
            r"|forecast|predict|projection|going to (be|rise|grow|fall|drop|need)|expect(ed)? (to|next)|in (3|6|12|three|six|twelve) months)")
CAUSAL = (r"(\bcause[ds]?\b|caused|because of the (agent|ai)|did the .* (make|lead to|drive)|impact of the agent on"
          r"|did (the |our )?[\w\- ]*(agent|assistant|bot|ai|copilot|checker|tool)s? (reduce|cut|lower|improve|increase|speed|boost|drive|make|lead|prevent|stop|decrease)"
          r"|thanks to (the )?(agent|ai|assistant)|attribut(e|able)\b.*\bto (the )?(agent|ai|assistant)|because of (the )?(agent|ai|assistant))")
# Prompt injection / jailbreak: instructions hidden in the question never change the rules (the rules are code, not a prompt).
INJECTION = (r"(ignore (all |any |the |your |my )?(previous |prior |above |earlier |system )*(instructions|rules|guardrails|prompts?)"
             r"|system prompt|developer mode|admin mode|god mode|jailbreak|\bdan\b|do anything now|no (restrictions|rules|limits|guardrails)"
             r"|pretend (you are|to be|you're)|you are now|from now on you|act as (an? )?(admin|root|unrestricted|different)|bypass (the |your )?(guards?|rules|filters?|security)"
             r"|override (the |your )?(rules|guards?|role|scope|security)|disregard (the |your |all )?(rules|instructions)|^\W*system\s*:)")
# Claim check: a number supplied in the question is never confirmed unless the governed answer computed the same number.
CLAIM = (r"(\bconfirm|\bverify|\bvalidate|\bagree\b|say yes|is it true|\bright\s*\?|correct\s*\?|tell (the )?(board|cfo|ceo|leadership|panel)"
         r"|put (that|this|it) in|sign off on|\bprove\b)")
CLAIM_NUM = r"(\d+(?:\.\d+)?)\s*(%|percent\b|x\b|crores?\b|lakhs?\b|cr\b|hours?\b|hrs?\b|seats?\b|users?\b|people\b)"
UNGOVERNED = r"(sentiment|happiness|productivity|\broi\b|morale|\bnps\b|engagement score|lines of code)"

# reason -> (why, safe alternative, metrics). Shared by the code guards and the fine-tuned router's "refuse" route
# (the model only picks a reason; the text is always this canned, reviewed text). "gaming" and "harmful" are reachable only via the model.
REFUSALS = {
    "injection": ("I can't switch off my rules: instructions inside a question are treated as text, not commands. My guards are code that runs before any model, and your access comes from your role, not from what the question says.",
                  "Ask a governed question instead, for example 'What is licence utilisation this month?' or 'How reliable are our agents?'", []),
    "write": ("I can't do that: I am read-only and never change agents, seats, data or settings.",
              "I can show this agent's usage, reliability and owner from the registry so the owner can decide and act through change control.", ["M16", "M10"]),
    "pii": ("I can't show raw events, user-level records or personal or card data. Raw PII never leaves the masked zone.",
            "I can give aggregate, governed figures instead, for example licence utilisation (M01) or interactions per active user (M04) by region.", ["M01", "M04"]),
    "individual": ("I can't rank or single out individual people. Adoption metrics are for improving the product and enablement, not monitoring staff.",
                   "I can show team or region-level utilisation (M01) and habitual users (M02) for groups of at least %d people." % C.MIN_GROUP, ["M01"]),
    "forecast": ("I don't forecast. Governed metrics describe the closed period only; a forecast would be a guess presented as a fact.",
                 "I can show the current figure and its change versus the previous closed period when one exists.", ["M01"]),
    "causal": ("I can't say the agent caused that. Usage data shows correlation only; cause needs the agreed study (staggered rollout or holdout).",
               "I can show the M09 study design and the before/after figures with their caveat, or the adoption trend for that workflow.", ["M09"]),
    "ungoverned": ("That isn't a governed metric, so I won't compute it on the fly.",
                   "Governed alternatives: M01 utilisation, M02 habitual users, M04 interactions per active user, M17 verified hours, M19 value score. Propose new metrics to the metric owner (cap of 25).", []),
    "harmful": ("I can't help with that. I only answer governed questions about NimbusPay AI adoption, and harmful or unsafe requests are out of bounds.",
                "Ask about adoption, value or reliability instead, for example 'What is licence utilisation this month?'", []),
    "gaming": ("I can't help inflate or game a metric. Governed metrics count qualifying use only, so extra logins or empty runs do not move them.",
               "I can show which pillars of the value score (M19) are low and what genuine use would move them, or the licence funnel (LF1-LF6).", ["M19"]),
}

AGENT_ALIAS = [(r"fraud", "AG-FRAUD-01"), (r"\bkyc\b", "AG-KYC-04"), (r"onboarding", "AG-ONB-02"), (r"summar", "AG-SUMM-03"), (r"\bx9\b", "AG-DND-X9")]
AGENT_WORD = r"\b(agent|assistant|bot|copilot|checker|summari[sz]er|tool)\b"
VALUE_WORDS = r"(\bsav(e|es|ed|ing)\b|\btime\b|\bhours?\b|worth|value|\bhelp(s|ing|ful)?\b|benefit|pay(ing)? off|useful|impact)"
OUTCOME = [(r"task success|success rate|\bm07\b", "M07", "Task success rate", "task outcome labels"),
           (r"handle[- ]?time|\bm08\b|fraud (review|case) time", "M08", "Fraud handle-time change", "the fraud handle-time comparison study"),
           (r"cycle[- ]?time|\bm09\b|onboarding (time|speed)|faster onboarding|merchant onboarding", "M09", "Onboarding cycle-time change", "the onboarding cycle-time comparison study"),
           (r"time saved per task|per task|\bm06\b", "M06", "Verified time saved per task", "the agreed time-and-motion or holdout study")]

# Shown when nothing matches: the closest governed questions, never a guess.
SUGGEST = [
    ("What is licence utilisation this month?", "utilisation adoption usage active users people use licence seats rate"),
    ("Show the licence funnel and unused seats", "funnel seats paid unused shelfware purchased assigned waste"),
    ("Which seats can we take back at renewal?", "reclaim seats cut renewal take back save money right-size"),
    ("What renewal outcome do you recommend?", "renew renewal contract recommend worth buy money decision vendor"),
    ("How are interactions counted?", "count interaction events questions overstate inflate meaning definition"),
    ("Why is vendor MAU higher than our active users?", "vendor mau monthly logins dashboard numbers match"),
    ("Compare engineer-built and drag-and-drop agents", "engineer drag drop build type no-code compare agents"),
    ("Which agents are used the most?", "agents used most popular top list ranking which"),
    ("How reliable are our agents?", "reliable reliability errors failures broken breaking crash agents"),
    ("Is the fraud agent saving analysts time?", "fraud kyc onboarding agent saving time hours value analysts"),
    ("Which connector has the highest failure rate this week?", "connector failure integration api email"),
    ("Which team uses it least?", "team teams least most lowest usage group"),
    ("Which region has the best adoption?", "region market country compare best worst"),
    ("Is usage going up or down?", "trend week weekly up down growing declining over time"),
    ("Is our data up to date?", "fresh freshness late stale data current restatement"),
    ("What should leadership worry about?", "alerts risks worry issues problems flags attention"),
    ("What is our AI value score?", "value score m19 pillars overall score"),
    ("How many agents are unregistered?", "unregistered shadow registry unknown agents rogue"),
]


SQL_TRACE = __import__("threading").local()   # per-request row counts of SQL actually executed ("Why this number?")


def _sql(db, sql, args=()):
    rows = db.execute(sql, args).fetchall()
    tr = getattr(SQL_TRACE, "rows", None)
    if tr is not None: tr.append(len(rows))
    return rows


def _scope(persona):
    return PERSONAS[resolve_persona(persona)]["regions"]


def _scope_sql(regions, col="region"):
    if regions is None: return "", ()
    if not regions: return " AND 1=0", ()                    # least privilege: no rows at all
    return f" AND {col} IN ({','.join('?' * len(regions))})", tuple(regions)


def _show(sql, args):
    """SQL as displayed to the user, with bound parameters inlined (display only; execution stays parameterised)."""
    for a in args: sql = sql.replace("?", repr(a), 1)
    return sql


def _regions_in(ql):
    return sorted({"Region " + x.upper() for x in re.findall(r"\bregion ([a-z])\b", ql)})


STOP = {"what", "which", "how", "the", "our", "are", "is", "you", "can", "about", "does", "did", "for", "and", "with", "this", "that", "show", "tell", "give", "me", "much", "many", "doing"}


def _stem(w):
    return w[:5]


class Agent:
    def __init__(self, result, db):
        self.r, self.db = result, db
        self.metrics = {m: v for m, v in result["metrics"].items()}
        self.agents = {a["agent"]: a for a in result["agents"]}

    # ---------- helpers ----------
    def _resp(self, kind, text, metrics=(), sql="", alt=None, intent="", rows=None, suggestions=None):
        return dict(type=kind, text=text, intent=intent, safe_alternative=alt, sql=sql.strip() or None, rows=rows, suggestions=suggestions,
                    citations=[dict(metric=m, version=C.METRIC_VERSION, data_as_of=self.r["data_as_of"]) for m in metrics],
                    data_as_of=self.r["data_as_of"], label="Synthetic data", read_only=True)

    def refuse(self, why, alt, metrics=(), intent="refuse"):
        return self._resp("refuse", why, metrics, alt=alt, intent=intent)

    def refusal(self, reason, persona):
        """Canned refusal for a reason (used by the code guards and by the fine-tuned router's 'refuse' route)."""
        if reason == "small_group":
            return self.refuse(f"I can't report a group smaller than {C.MIN_GROUP} people: it could identify individuals.",
                               "I can show the figure at region level, or for the team once it has at least %d assigned seats." % C.MIN_GROUP, ["LF4"], "small_group")
        if reason == "scope":
            regions = _scope(persona) or []
            return self.refuse("That market is outside your access scope. Row-level security follows your SSO role (%s)." % (", ".join(regions) or "no data scope"),
                               "I can show the same metric for your own region, or the company-wide total that renewal uses. Ask your sponsor for wider access if needed.", ["M01"], "scope")
        why, alt, metrics = REFUSALS[reason]
        return self.refuse(why, alt, metrics, reason)

    # Validated args from the fine-tuned router (empty for other brains). Thread-local: requests can run in parallel.
    _ctx = threading.local()

    def _arg(self, key):
        return (getattr(self._ctx, "args", None) or {}).get(key)

    def _agent_in(self, ql):
        for aid in self.agents:
            if aid.lower() in ql: return aid
        if not re.search(AGENT_WORD, ql): return None
        for pat, aid in AGENT_ALIAS:
            if re.search(pat, ql) and aid in self.agents: return aid
        return None

    # ---------- guards (always deterministic, run before any intent or LLM) ----------
    def guards(self, q, persona):
        ql = q.lower().strip()
        for reason, pat in (("injection", INJECTION), ("write", WRITE), ("pii", PII), ("individual", INDIVIDUAL)):
            if re.search(pat, ql): return self.refusal(reason, persona)
        m = re.search(r"team of (\d+)|(\d+)[- ]person team|team with (\d+)", ql)
        if m and int(next(g for g in m.groups() if g)) < C.MIN_GROUP:
            return self.refusal("small_group", persona)
        regions = _scope(persona)
        if regions:
            asked = _regions_in(ql)
            outside = "outside my region" in ql or "other region" in ql or "another market" in ql or "outside my market" in ql
            if outside or any(a not in [x.split(" (")[0] for x in regions] for a in asked):
                return self.refusal("scope", persona)
        for reason, pat in (("forecast", FORECAST), ("causal", CAUSAL), ("ungoverned", UNGOVERNED)):
            if re.search(pat, ql): return self.refusal(reason, persona)
        return None

    def out_of_scope(self, region, persona):
        """True if a region (e.g. from the fine-tuned router's args) is outside the caller's row-level scope."""
        regions = _scope(persona)
        return regions is not None and region not in [x.split(" (")[0] for x in regions]

    def no_role(self):
        return self.refuse("I can't show data: your role isn't recognised, so you get least-privilege access (deny by default). In production the role comes from your SSO token, never from the request.",
                           "Sign in with a recognised role (executive, regional lead, platform engineer, fraud operations lead, finance). Without one I can still explain definitions, e.g. 'How is licence utilisation defined?'", [], "no_role")

    # ---------- intents ----------
    def m01(self, q, persona):
        reg = _scope(persona); w, a = _scope_sql(reg)
        asked = [self._arg("region")] if self._arg("region") else _regions_in(q.lower())
        if asked:
            w += " AND (" + " OR ".join("region LIKE ?" for _ in asked) + ")"; a += tuple(x + "%" for x in asked)
        sql = f"SELECT SUM(active) AS active, SUM(assigned) AS assigned,\n  ROUND(100.0*SUM(active)/SUM(assigned),1) AS m01_pct\nFROM user_funnel WHERE assigned = 1{w};"
        act, asg, v = _sql(self.db, sql, a)[0]
        if not asg:
            return self._resp("caveat", "No assigned seats match that scope in this data set.", ["M01"], _show(sql, a), intent="M01")
        sc = f" for {', '.join(asked)}" if asked else (f" for {', '.join(reg)}" if reg else "")
        return self._resp("answer", f"Licence utilisation{sc} is {v}% ({act} active users / {asg} assigned seats). Active = at least one qualifying interaction in the 28-day period.",
                          ["M01"], _show(sql, a), intent="M01")

    def define_m01(self, q, persona):
        return self._resp("answer", "M01 Licence utilisation = Active users (LF4) / Assigned seats (LF2). Active means at least one qualifying interaction (an agent run that returned a response) in the 28-day period. Logins never count. Version " + C.METRIC_VERSION + ", working definition to agree.", ["M01"], intent="define_M01")

    def m02_regions(self, q, persona):
        reg = _scope(persona); w, a = _scope_sql(reg)
        sql = f"SELECT region, SUM(habitual) AS habitual, SUM(assigned) AS assigned,\n  ROUND(100.0*SUM(habitual)/SUM(assigned),1) AS m02_pct\nFROM user_funnel WHERE assigned = 1{w}\nGROUP BY region HAVING SUM(assigned) >= {C.MIN_GROUP} ORDER BY m02_pct DESC;"
        rows = _sql(self.db, sql, a)
        txt = "; ".join(f"{r[0]}: {r[3]}% ({r[1]}/{r[2]})" for r in rows)
        return self._resp("answer", f"Habitual users (active in 3+ of 4 weeks) by market: {txt}.", ["M02"], _show(sql, a), intent="M02", rows=rows)

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
        lead = "No. " if re.search(r"doubl|so did|so is|means? more value|value (go|went) up", q.lower()) else "Vendor MAU is higher because it counts activity, not use. "
        return self._resp("caveat", lead + f"MAU counts anyone with a logged event, logins included ({u['vendor_mau_proxy']} users here), but only {len(u['active'])} were active and {len(u['habitual'])} habitual, so MAU overstates active users by {u['mau_overstatement']}. More logins is not more value; value needs verified outcomes (M17) and the full M19 with its pillars.",
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
        return self._resp("answer", f"One interaction = one question a person asked an agent, however many events it writes (the run, searches, connector calls). {self.r['quality']['clean_events']} clean events became {g['interactions']} logical interactions ({g['exact']} exact by interaction ID, {g['approximate']} approximate by sessionisation, {C.SESSION_GAP_S} s gap); {g['qualifying']} qualify (the agent returned a response). Counting raw non-login events would overstate use {g['inflation']}x.",
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

    # ---------- broader governed tools (same rules: SQL or pipeline numbers only, cited) ----------
    def _agent_sql(self, aid):
        sql = ("SELECT COUNT(*) AS interactions, SUM(qualifying) AS qualifying, COUNT(DISTINCT user_id) AS users,\n"
               "  SUM(method='exact') AS exact\nFROM interactions WHERE agent_id = ?;")
        return sql, _sql(self.db, sql, (aid,))[0]

    def agent_health(self, q, persona):
        aid = self._arg("agent") or self._agent_in(q.lower())
        if not aid: return self.reliability(q, persona)
        a = self.agents[aid]; sql, (n, qual, users, exact) = self._agent_sql(aid)
        flags = []
        if a["M10"] is not None and a["M10"] > C.M10_MAX: flags.append(f"error rate above the {C.M10_MAX:g}% gate")
        if a["M11"] is not None and a["M11"] > C.M11_MAX: flags.append(f"connector failures above the {C.M11_MAX:g}% gate")
        if not a["registered"]: flags.append("not in the registry (owner to confirm)")
        verdict = ("Watch: " + "; ".join(flags) + ".") if flags else f"Within the placeholder reliability gates (M10 <= {C.M10_MAX:g}%, M11 <= {C.M11_MAX:g}%)."
        return self._resp("answer", f"{a['name']} ({aid}, {a['build_type']}, {'registered' if a['registered'] else 'UNREGISTERED'}): {qual} qualifying interactions this period; "
                          f"agent error rate (M10) {a['M10']}% ({a['failed_runs']}/{a['runs']} runs); connector failure rate (M11) {a['M11']}% ({a['failed_calls']}/{a['calls']} calls); "
                          f"events without interaction ID (M20) {a['M20']}%{' so its counts are approximate' if a['M20'] else ''}. {verdict} Working is not the same as saving time: that needs M17.",
                          ["M10", "M11", "M20", "M04"] + ([] if a["registered"] else ["M16"]), _show(sql, (aid,)), intent="agent_health")

    def agent_value(self, q, persona):
        aid = self._arg("agent") or self._agent_in(q.lower())
        if not aid: return self.m17(q, persona)
        a = self.agents[aid]; sql, (n, qual, users, exact) = self._agent_sql(aid)
        m = self.metrics["M17"]
        ucount = f"{users} people" if users >= C.MIN_GROUP else f"fewer than {C.MIN_GROUP} people"
        if m["value"] is None:
            head = (f"Not provable from logs yet. Time saved is M17 (verified hours), and it needs the agreed comparison study (staggered rollout or holdout) for {a['name']}; "
                    f"there is no verified result this period, and usage time is not time saved.")
        else:
            head = (f"Company-wide verified hours saved (M17) are {m['value']:g} h/week from the agreed study; attributing a share to {a['name']} needs that study's per-workflow cut, "
                    f"so I don't split it by agent.")
        return self._resp("caveat", head + f" What the governed logs do show for {aid}: {qual} qualifying interactions from {ucount}, "
                          f"agent error rate (M10) {a['M10']}%, connector failure rate (M11) {a['M11']}%. Study design: compare handle time for matched cases with and without the agent, agreed baseline, owner sign-off.",
                          ["M17", "M04", "M10", "M11"], _show(sql, (aid,)), intent="agent_value")

    def reliability(self, q, persona):
        rows = sorted(self.r["agents"], key=lambda a: (-(a["M10"] or 0) - (a["M11"] or 0)))
        txt = "; ".join(f"{a['agent']} M10 {a['M10']}%, M11 {a['M11']}%" for a in rows)
        e = self.r["renewal"]["evidence"]["e4"]
        sql = ("SELECT agent_id,\n  ROUND(100.0*SUM(event_type='agent_run' AND status='failed')/NULLIF(SUM(event_type='agent_run'),0),1) AS m10_pct,\n"
               "  ROUND(100.0*SUM(event_type='connector_call' AND status='failed')/NULLIF(SUM(event_type='connector_call'),0),1) AS m11_pct\n"
               "FROM events_clean GROUP BY agent_id ORDER BY m10_pct + m11_pct DESC;")
        return self._resp("answer", f"Period agent error rate (M10) is {self.metrics['M10']['value']}% ({self.metrics['M10']['note']}) and connector failure rate (M11) is {self.metrics['M11']['value']}% ({self.metrics['M11']['note']}). "
                          f"By agent, worst first: {txt}. Placeholder gates: M10 <= {C.M10_MAX:g}%, M11 <= {C.M11_MAX:g}%; renewal reliability evidence is '{e}'.",
                          ["M10", "M11"], sql, intent="reliability", rows=[[a["agent"], a["M10"], a["M11"]] for a in rows])

    def agent_usage(self, q, persona):
        sql = ("SELECT i.agent_id, r.name, r.registered, r.build_type_used, SUM(i.qualifying) AS qualifying, COUNT(*) AS interactions\n"
               "FROM interactions i LEFT JOIN agent_registry r ON r.agent_id = i.agent_id\nGROUP BY i.agent_id ORDER BY qualifying DESC;")
        rows = _sql(self.db, sql)
        txt = "; ".join(f"{r[0]} {r[1] or 'unknown'} ({r[3]}{'' if r[2] else ', UNREGISTERED'}): {r[4]}" for r in rows)
        return self._resp("answer", f"{len(rows)} agents are in use. Ranked by qualifying interactions (logical questions answered, not raw events or logins): {txt}. "
                          "Drag-and-drop agents' counts are approximate (no interaction ID). Usage ranks activity, not time saved.",
                          ["M04", "M16", "M20"], sql, intent="agent_usage", rows=rows)

    def build_compare(self, q, persona):
        sql = ("SELECT build_type, COUNT(*) AS interactions, SUM(qualifying) AS qualifying, SUM(method='exact') AS exact\n"
               "FROM interactions GROUP BY build_type ORDER BY build_type DESC;")
        rows = _sql(self.db, sql)
        rel = {}
        for a in self.r["agents"]:
            d = rel.setdefault(a["build_type"], [0, 0]); d[0] += a["failed_runs"]; d[1] += a["runs"]
        parts = []
        for bt, n, qual, ex in rows:
            m20 = self.r["m20"].get(bt, {}).get("pct")
            fr, rn = rel.get(bt, [0, 0])
            parts.append(f"{bt}: {n} interactions ({ex} exact by interaction ID, {n - ex} approximate), {qual} qualifying, {m20}% of events without an interaction ID, agent error rate {round(100 * fr / rn, 1) if rn else 'n/a'}% ({fr}/{rn} runs)")
        return self._resp("answer", "; ".join(parts) + ". Drag-and-drop agents log no interaction ID, so their interactions are sessionised and labelled approximate; "
                          "compare their volumes as estimates, not exact counts. Engineer-built agents are counted exactly.",
                          ["M20", "M04", "M10"], sql, intent="build_compare", rows=rows)

    def team_usage(self, q, persona):
        reg = _scope(persona); w, a = _scope_sql(reg)
        sql = (f"SELECT team_id, region, SUM(active) AS active, SUM(assigned) AS assigned\nFROM user_funnel WHERE assigned = 1{w}\n"
               f"GROUP BY team_id ORDER BY team_id;  -- teams under {C.MIN_GROUP} assigned seats are suppressed")
        rows = _sql(self.db, sql, a)
        shown = sorted([r for r in rows if r[3] >= C.MIN_GROUP], key=lambda r: r[2] / r[3])
        hidden = [r[0] for r in rows if r[3] < C.MIN_GROUP]
        regs = {}
        for t, rg, act, asg in rows:
            d = regs.setdefault(rg, [0, 0]); d[0] += act; d[1] += asg
        regtxt = "; ".join(f"{rg} {round(100 * v[0] / v[1], 1)}% ({v[0]}/{v[1]})" for rg, v in sorted(regs.items(), key=lambda kv: kv[1][0] / kv[1][1]) if v[1] >= C.MIN_GROUP)
        tt = "; ".join(f"{t} ({rg}) {round(100 * act / asg, 1)}% ({act}/{asg})" for t, rg, act, asg in shown) or "none"
        low = f" Lowest reportable team: {shown[0][0]}." if shown else ""
        return self._resp("answer", f"Team-level licence utilisation (M01), teams with at least {C.MIN_GROUP} assigned seats: {tt}.{low} "
                          f"Suppressed to protect individuals (fewer than {C.MIN_GROUP} seats): {', '.join(hidden) or 'none'}. Region level instead, lowest first: {regtxt or 'none reportable'}.",
                          ["M01", "LF4"], _show(sql, a), intent="team_usage", rows=[list(r) for r in shown])

    def region_compare(self, q, persona):
        reg = _scope(persona); w, a = _scope_sql(reg)
        sql = (f"SELECT region, ROUND(100.0*SUM(active)/SUM(assigned),1) AS m01_pct, ROUND(100.0*SUM(habitual)/SUM(assigned),1) AS m02_pct, SUM(assigned) AS assigned\n"
               f"FROM user_funnel WHERE assigned = 1{w}\nGROUP BY region HAVING SUM(assigned) >= {C.MIN_GROUP} ORDER BY m01_pct DESC;")
        rows = _sql(self.db, sql, a)
        if not rows:
            return self._resp("caveat", "No market in your scope has enough assigned seats to report.", ["M01"], _show(sql, a), intent="region_compare")
        txt = "; ".join(f"{r[0]}: utilisation {r[1]}%, habitual {r[2]}% ({r[3]} seats)" for r in rows)
        best_h = max(rows, key=lambda r: r[2])
        note = " A launch cohort is still ramping, so read it against its launch date." if any("launch" in r[0].lower() for r in rows) else ""
        return self._resp("answer", f"By market, highest utilisation first: {txt}. Highest utilisation: {rows[0][0]}; most habitual use: {best_h[0]}.{note} Utilisation alone is not adoption quality; read it with habitual use.",
                          ["M01", "M02"], _show(sql, a), intent="region_compare", rows=rows)

    def trend(self, q, persona):
        reg = _scope(persona); w, a = _scope_sql(reg)
        sql = f"SELECT day/7 + 1 AS week, SUM(qualifying) AS qualifying, COUNT(DISTINCT user_id) AS users\nFROM interactions WHERE 1=1{w}\nGROUP BY week ORDER BY week;"
        rows = _sql(self.db, sql, a)
        wk = ", ".join(f"W{r[0]} {r[1]}" for r in rows)
        us = ", ".join(f"W{r[0]} {r[2] if r[2] >= C.MIN_GROUP else '<' + str(C.MIN_GROUP)}" for r in rows)
        return self._resp("caveat", f"This data set holds one closed 28-day period, so there is no prior period to compare, and I don't project forward. Within the period, qualifying interactions by week: {wk}; "
                          f"weekly active users: {us}. Read the last week with care: {self.r['quality']['late']} events arrived late and {self.r['quality']['after_close']} after close (restatement).",
                          ["M04", "M02", "M12"], _show(sql, a), intent="trend", rows=rows)

    def freshness(self, q, persona):
        g, ql = self.r["grouping"], self.r["quality"]
        return self._resp("answer", f"Data as of {self.r['data_as_of']}, period {self.r['period']}. {ql['late']} events arrived late (over {C.LATE_H} h) and are counted on event time, flagged; "
                          f"{ql['after_close']} rows arrived after the close (+{C.CLOSE_AFTER_H} h) and go to restatement, which would move qualifying interactions from {g['qualifying']} to {g['restated_qualifying']}. "
                          f"Closed-period numbers do not change silently.", ["M12"], "SELECT SUM(late) AS late_events, MAX(ingested_at) AS last_load FROM events_clean;", intent="freshness")

    def alerts(self, q, persona):
        al = self.r["alerts"]
        if not al:
            return self._resp("answer", "No alerts for this data set.", ["M01"], intent="alerts")
        order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        al = sorted(al, key=lambda x: order.get(x["severity"], 9))
        txt = " ".join(f"[{x['severity']}, {x['metric']}] {x['text']}" for x in al[:5])
        return self._resp("answer", f"Top alerts from the governed metrics: {txt} Renewal outcome right now: {self.r['renewal']['outcome']}.",
                          list(dict.fromkeys(x["metric"] for x in al)), intent="alerts")

    def reclaim(self, q, persona):
        from . import features as F
        sql = "SELECT team_id, region, purchased_seats, user_id, assigned, provisioned FROM seats;"
        seats = [dict(team_id=t, region=rg, purchased_seats=str(p), user_id=u, assigned="yes" if asg else "no", provisioned="yes" if pr else "no")
                 for t, rg, p, u, asg, pr in _sql(self.db, sql)]
        rc = F.seat_reclaim(dict(seats=seats), self.r)
        reg = _scope(persona)
        rows = [t for t in rc["rows"] if reg is None or any(t["region"].startswith(x) for x in reg)]
        total = sum(t["reclaimable"] for t in rows)
        tt = "; ".join(f"{t['team']} {t['reclaimable']} ({t['never_assigned']} never assigned, {t['buffer_kept']} kept as headroom)" for t in rows if t["reclaimable"])
        scope = "" if reg is None else f" in {', '.join(reg)}"
        return self._resp("answer", f"Seat reclaim finder{scope}: {total} of {sum(t['purchased'] for t in rows)} purchased seats could be reclaimed at renewal. {self.r['paid_unused']} paid seats have no qualifying use company-wide; "
                          f"the finder keeps {int(C.RECLAIM_KEEP_BUFFER * 100)}% headroom per team. By team: {tt or 'none'}. Team-level only, no individual named; launch-cohort teams are reviewed after ramp-up. Seat price is a placeholder.",
                          ["LF1", "LF2", "LF4", "M01"], sql, intent="reclaim", rows=[[t["team"], t["reclaimable"]] for t in rows])

    def outcome(self, q, persona):
        ql = q.lower()
        mid, label, need = next(((m, l, n) for p, m, l, n in OUTCOME if (m == self._arg("metric") if self._arg("metric") else re.search(p, ql))),
                                ("M07", "Task success rate", "task outcome labels"))
        m = self.metrics.get(mid)
        if m and m["value"] is not None:
            return self._resp("answer", f"{label} ({mid}) is {m['value']} {m['unit']} ({m['note']}).", [mid], intent="outcome")
        return self.refuse(f"I can't give {label} ({mid}): it needs outcome data from {need}, which this data set doesn't have, and I don't impute or estimate it.",
                           f"I can show the study design for {mid}, and the governed usage (M04) and reliability (M10) for that workflow in the meantime.", [mid], "outcome")

    INTENTS_FIRST = [
        (r"how is .*utili[sz]ation defined|define .*utili[sz]ation|definition of .*utili[sz]ation|what does .*utili[sz]ation mean", "define_m01"),
        (r"what (does|is) (one|an|a single|1) interaction|interaction mean|define .*interaction|what counts as (a |an |one )?(use|interaction|question)", "counting"),
        (r"why .*(value score|m19|score).*(low|bad|poor)", "why_low"),
        (r"why .*(drop|fall|fell|declin|lower|low\b|down)", "why_drop"),
        (r"interaction ids?|m20|sessionis|sessioniz|without (an )?(interaction )?ids?|missing ids?", "m20"),
        (r"unregistered|registry|shadow|unknown agents?|rogue|unapproved", "m16"),
        ("|".join(p for p, *_ in OUTCOME), "outcome"),
        (r"connector", "m11"),
    ]
    INTENTS = [
        (r"\bmau\b|monthly active|vendor'?s? (count|number|figure|dashboard|report|data|metric)s?|vendor says|numbers? (don'?t|do not) match", "mau"),
        (r"habitual|regular users|repeat users|sticky|stickiness|3\+ of 4", "m02_regions"),
        (r"newest country|new country|launch|cohort|new market", "cohort"),
        (r"engineer[- ]built|drag[- ](and|n|&)[- ]drop|no[- ]code|low[- ]code|build types?|built by engineers", "build_compare"),
        (r"reclaim|take back|claw ?back|right[- ]?siz|give back|(cut|drop|reduce|trim|remove|return|shed)\b.*\bseats?|seats?\b.*\b(cut|drop|reduce|trim|remove|return)\b|idle seats|which seats|seat savings|over[- ]?licen", "reclaim"),
        (r"value score|m19|ai score|overall score|health index|interim index|adoption score", "m19"),
        (r"hours.*sav|sav.*(time|hours)|time saved|verified hours|m17|time sav", "m17"),
        (r"cost per|m18|unit cost|cost of (an |each )?hour", "m18"),
        (r"(error rate|errors|failed runs|m10|fail).*(yesterday|today|latest|last day)|(yesterday|today|latest day).*(error|fail)", "m10"),
        (r"reliab|error rate|errors|failed runs|m10|fail|breaking|broken|\bbreaks?\b(?!\s*down)|crash|outage|uptime|stabl", "reliability"),
        (r"fresh|stale|up to date|up-to-date|late (events|data|rows|arriv)|m12|data as of|restat|last (updated|refresh|load)|how current", "freshness"),
        (r"alert|worr|red flag|\brisks?\b|issues|problems|watch out|attention|concern|what should (i|we|leadership) (know|look|focus)", "alerts"),
        (r"renew|renewal|recommend|contract|keep paying|worth (it|the money|paying)|should we (buy|keep|expand|continue|stop)|value for money", "renewal"),
        (r"which agents|what agents|list (of |the |all |our )?agents|how many agents|agents? (are|is) (used|the most|most)|most[- ]used agent|top agents|rank(ing)? (the |our )?agents|agent usage|busiest agent|popular agent|agents? by usage", "agent_usage"),
        (r"which teams?|what teams?|teams?\b.*\b(least|most|lowest|highest|best|worst|lag)|by team|per team|team[- ]level|each team|team-[a-c]\d|across teams", "team_usage"),
        (r"which (region|market)s?|by (region|market)|across (the )?(regions|markets)|compare (the )?(regions|markets)|each (region|market)|(best|worst|top|lowest|highest|leading|lagging) (region|market)", "region_compare"),
        (r"trend|going (up|down)|up or down|grow(ing|th)|increas|decreas|over time|week (on|over) week|by week|weekly|month (on|over) month|getting (better|worse)|improv|declin|momentum|rising|falling", "trend"),
        (r"funnel|seats?|shelfware|unused|idle|licen[cs]es? (bought|purchased|paid)|paying for|wasted|paid for|purchased", "funnel"),
        (r"how (do|are|is) .*count|interactions? (count|total)|how many interactions|overstat|events|double[- ]count|inflat|interactions?", "counting"),
        (r"per active user|per user|m04|depth|how often|questions per|frequency|intensity", "m04"),
        (r"utili[sz]ation|m01|adoption|how many (people|users|staff|employees|of us)|active users|actually us|using (it|the|ai)|use (it|the|ai)|uptake|usage|take[- ]?up|penetration", "m01"),
    ]

    def route(self, q):
        ql = q.lower()
        for pat, fn in self.INTENTS_FIRST:
            if re.search(pat, ql): return fn
        if self._agent_in(ql):
            return "agent_value" if re.search(VALUE_WORDS, ql) else "agent_health"
        for pat, fn in self.INTENTS:
            if re.search(pat, ql): return fn
        return None

    def suggest(self, q, n=3):
        words = {_stem(w) for w in re.findall(r"[a-z0-9]+", q.lower()) if len(w) > 2 and w not in STOP}
        scored = []
        for i, (s, kw) in enumerate(SUGGEST):
            vocab = {_stem(w) for w in re.findall(r"[a-z0-9]+", (s + " " + kw).lower()) if len(w) > 2 and w not in STOP}
            scored.append((-len(words & vocab), i, s))
        return [s for _, _, s in sorted(scored)[:n]]

    def unmatched(self, q):
        sug = self.suggest(q)
        r = self.refuse("I couldn't map that to a governed metric, so I won't guess. I can answer these governed questions: "
                        + " ".join(f"({i + 1}) {s}" for i, s in enumerate(sug)),
                        "Pick one of the suggestions, or ask about utilisation, seats, renewal, counting, reliability, agents, teams, regions or trends.", [], "unmatched")
        r["suggestions"] = sug
        return r

    def vague(self, q):
        """Vague question -> clarify flow: 3 governed options to pick from, no data and never a model-written answer."""
        r = self.unmatched(q)
        r["text"] = ("That's a broad question, so I won't guess. Which of these do you mean? "
                     + " ".join(f"({i + 1}) {s_}" for i, s_ in enumerate(r["suggestions"])))
        r["clarify"] = "vague"; r["confidence"] = 0.0
        return r

    def clarify(self, q, slot):
        """Clarifying question from the fine-tuned router's none + clarify. Same shape as conversation._clarify, no data.
        agent: one unnamed agent is meant -> pick an agent; topic: several asks with no main one -> 3 governed questions."""
        if slot == "agent":
            from . import conversation as CV          # lazy: conversation imports this module
            make_q = (lambda a: re.sub(CV.VAGUE_AGENT, a, q, count=1, flags=re.I)) if re.search(CV.VAGUE_AGENT, q, re.I) else (lambda a: f"How is {a} doing?")
            return CV._clarify(self, "Which agent do you mean? I won't guess, because the answer differs by agent.", CV._agent_options(self, make_q), 0.4, "clarify_agent")
        r = self.unmatched(q)                            # 3 closest governed questions, as a choice
        r["clarify"] = "topic"
        return r

    def regions(self):
        return sorted({r[0] for r in _sql(self.db, "SELECT DISTINCT region FROM user_funnel")})

    def ask(self, q, persona=None, prev=None):
        """prev: optional previous question (from the session), so the fine-tuned brain can resolve follow-ups."""
        persona = resolve_persona(persona)                  # deny by default: unknown or missing role -> least privilege
        g = self.guards(q, persona)                      # safety guards are ALWAYS deterministic and run first
        if g:
            g["mode"] = "rules (guard)"; return g
        q = re.sub(r"<[^<>]{0,300}>", " ", q).strip() or q   # markup is text, never routing input (e.g. '<img onerror=alert(1)>' is not an 'alerts' question)
        claims = claimed_numbers(q)
        b = brain()
        fn, mode, args, ft_note, ft_route = None, "rules", {}, None, None
        if is_vague(q) and not (prev and b["kind"] == "finetuned"):   # 'How are we doing?': ask, never guess (every brain)
            r = self.vague(q); r["mode"] = "rules (clarify)"; r["persona"] = persona
            return r
        use_model = b["kind"] == "finetuned"
        if use_model and ft_mode() == "hybrid":          # rules first, model second
            from . import conversation as CV             # lazy: conversation imports this module
            rfn, rconf = CV.route_scored(self, q)
            if (rfn and rconf >= rules_min_conf()) or (claims and not rfn):
                use_model = False; mode = "rules (hybrid)"   # confident rules match, or a claim with no governed match -> claim check
        if use_model:
            d = FT.route(q, persona, prev, self.agents, self.regions())   # schema-checked; None on any failure (incl. FT_TIMEOUT_S)
            ft_route = (d["tool"] if d else "invalid")
            if (d and d["tool"] not in ("refuse", "none") and ft_mode() == "hybrid" and not prev
                    and not self.route(q) and not in_domain(q)):
                d, ft_note = {"tool": "none", "args": {}}, "off-domain model route ignored"   # e.g. a joke routed to a data tool
            if d and d["tool"] == "refuse":              # the model may refuse MORE than the guards, never less
                r = self.refusal(d["args"]["reason"], persona); r["mode"] = b["label"] + " (refuse)"; r["persona"] = persona
                r["ft_route"] = ft_route; return r
            if d and d["tool"] == "none" and d["args"].get("clarify"):   # ask instead of guessing (no rules fallback)
                r = self.clarify(q, d["args"]["clarify"]); r["mode"] = b["label"] + " (clarify)"; r["persona"] = persona
                r["ft_route"] = ft_route; return r
            if d and d["tool"] != "none":
                fn, args, mode = d["tool"], d["args"], b["label"]
            ft_note = ft_note or ("model said none" if d else "invalid model output or timeout")
        elif b["kind"] not in ("rules", "finetuned"):
            fn = b["route"](q, list(INTENT_HELP))        # the model only picks a governed tool
            if fn: mode = b["label"]
        if not fn:
            fn = self.route(q)                           # automatic fallback: deterministic router
            if b["kind"] != "rules" and mode == "rules": mode = "rules (fallback)"
        if fn and persona == LEAST_PRIVILEGE and fn not in PUBLIC_INTENTS:
            r = self.no_role()
        elif not fn:
            r = self.unmatched(q)
        elif args.get("region") and self.out_of_scope(args["region"], persona):
            r = self.refusal("scope", persona)           # scope is re-checked on the model's args, not only on the question text
        else:
            self._ctx.args = args
            try:
                r = getattr(self, fn)(q, persona)        # numbers come from SQL / pipeline here, never from the model
            finally:
                self._ctx.args = None
            if (b["kind"] == "finetuned" and mode == b["label"] and r["type"] in ("answer", "caveat") and not claims
                    and os.environ.get("FT_ANSWER", "0") == "1"):   # default off: model routes, the template writes the text
                txt, why = FT.answer(q, persona, r)      # model writes the text; every number must be in the governed result
                if txt:
                    r["template_text"], r["text"], r["answer_by"] = r["text"], txt, "model (number-checked)"
                else:
                    r["answer_by"] = "template (" + why + ")"
        if claims:                                       # a user-typed number is never echoed as fact (template text only)
            r = self._claim_check(r, claims)
        if ft_note and mode == "rules (fallback)": r["fallback_reason"] = ft_note
        if ft_route: r["ft_route"] = ft_route
        r["mode"] = mode
        r["persona"] = persona
        return r

    def _claim_check(self, r, claims):
        """Never confirm a number the user supplied. Say whether the governed answer computed the same figure."""
        nums = set(re.findall(r"\d+(?:\.\d+)?", r["text"]))
        num = lambda c: re.match(r"\d+(?:\.\d+)?", c).group(0)
        same = [c for c in claims if num(c) in nums]
        other = [c for c in claims if num(c) not in nums]
        r["claim_check"] = dict(claimed=claims, matches_governed=same, unverified=other)
        if r["type"] == "refuse":
            if r["intent"] in ("unmatched", "no_role"):
                r = self.refuse(f"I can't confirm {', '.join(c for c in claims)}: that figure came from the question, not from a governed query, and I never repeat a number I didn't compute.",
                                "Ask for the metric itself (for example 'What is licence utilisation?' or 'Are we saving time?') and I'll give the computed figure with its metric ID, SQL and data-as-of."
                                + (" " + r["safe_alternative"] if r["intent"] == "no_role" else ""), [], "unverified_claim")
                r["claim_check"] = dict(claimed=claims, matches_governed=[], unverified=claims)
            return r
        if other:
            r["text"] = f"Claim check: I can't confirm {', '.join(other)} from your question; the governed figure is below. " + r["text"]
        else:
            r["text"] = f"Claim check: {', '.join(same)} matches the governed figure. " + r["text"]
        return r


# ---------- hybrid routing helpers (NP_BRAIN=finetuned) ----------
# Governed-domain vocabulary. Used for two code checks: (1) a short question with NO domain word that just asks for a
# status ("How are we doing?") is vague -> clarify with 3 governed options, never a model-written answer; (2) when the rules
# engine has no match, a model data-tool route for an off-domain question (no domain word, no previous question) is ignored.
# Tuned on the TRAIN split only (it keeps 98% of train questions the rules miss but the model should route).
DOMAIN = (r"seat|licen[cs]|utili[sz]|\butil\b|adopt|uptake|usage|\buse|using|user|active|activ|agent|\bbots?\b|assistant|copilot|\bai\b|tool|"
          r"renew|contract|vendor|supplier|procure|region|market|countr|team|group|squad|pod|data|dashboard|figure|number|metric|score|index|"
          r"formula|average|error|fail|flak|reliab|stable|dependab|connector|integration|plumbing|hook|time|hours?\b|sav|cost|money|spend|"
          r"budget|bill|value|worth|roi|trend|novelty|wearing off|interest|week|month|quarter|period|staff|people|ppl|employee|workforce|"
          r"rollout|launch|pilot|training|enablement|registry|governance|sign.?off|shadow|kyc|fraud|onboard|summar|x9|\bm\d\d\b|interaction|"
          r"event|log|report|exec|leadership|cfo|coo|fresh|stale|up to date|lag|behind|alert|worry|risk|flag|fire|cohort|engineer|no.?code|"
          r"citizen|drag|build|login|logged|idle|unused|dormant|shelf|reclaim|hand back|trim")
_DOMAIN_KW = sorted(set(re.findall(r"[a-z]{5,}", DOMAIN)))
VAGUE_ASK = (r"\b(how (are|is) (we|it|things|everything|stuff|that|this)\b|how'?s (it|everything|things) going|status|thoughts|verdict|story|"
             r"overview|summary|update|numbers|anything (new|interesting)|what'?s (up|new|happening)|where are we|how did we do|how we doing)")


def in_domain(q):
    """True if the question mentions anything from the governed domain (exact vocabulary, suggestion words, or a 1-typo match)."""
    import difflib
    ql = q.lower()
    if re.search(DOMAIN, ql): return True
    ws = re.findall(r"[a-z0-9]+", ql)
    if {_stem(w) for w in ws if len(w) > 3 and w not in STOP and w not in _GENERIC} & _suggest_vocab(): return True
    return any(difflib.get_close_matches(w, _DOMAIN_KW, n=1, cutoff=0.8) for w in ws if len(w) >= 5)


_SUGGEST_VOCAB = []
_GENERIC = {"going", "have", "there", "their", "would", "could", "should", "from", "into", "than", "then", "they", "them", "were",
            "been", "more", "most", "over", "down", "back", "right", "real", "really", "only", "best", "when", "where", "things", "anything"}


def _suggest_vocab():
    if not _SUGGEST_VOCAB:
        v = set()
        for s_, kw in SUGGEST: v |= {_stem(w) for w in re.findall(r"[a-z0-9]+", (s_ + " " + kw).lower()) if len(w) > 3 and w not in STOP}
        _SUGGEST_VOCAB.append(v)
    return _SUGGEST_VOCAB[0]


def is_vague(q):
    """Short status-style question with no topic, metric or agent: 'How are we doing?', 'status?', 'thoughts?'."""
    ql = q.lower().strip()
    return (len(re.findall(r"[a-z0-9']+", ql)) <= 6 and bool(re.search(VAGUE_ASK, ql)) and not in_domain(ql)
            and not claimed_numbers(q))


def ft_mode():
    """NP_BRAIN=finetuned routing mode: 'hybrid' (default: rules first, model second) or 'pure' (model first, for comparison)."""
    return "pure" if os.environ.get("FT_MODE", "hybrid").lower() == "pure" else "hybrid"


def rules_min_conf():
    """A rules match at or above this match quality (conversation.route_scored) is 'confident' and never goes to the model.
    0.65 is the lowest score any golden / probe / unscripted / break-it question gets (A11 'Which seats can we take back
    at renewal?'), so all of them stay with rules. Below it are general patterns that also hit 3+ other tools (0.6)."""
    try: return float(os.environ.get("FT_RULES_MIN_CONF", "0.65"))
    except ValueError: return 0.65


def claimed_numbers(q):
    """Numbers with a unit the user asks us to confirm, e.g. 'confirm 40% savings' -> ['40']. Empty unless a confirm-style verb is present."""
    ql = q.lower()
    if not re.search(CLAIM, ql): return []
    return list(dict.fromkeys(m.group(0).strip() for m in re.finditer(CLAIM_NUM, ql)))


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
    "agent_health": "how one named agent is doing: usage, error rate, connector failures (M10, M11, M20)",
    "agent_value": "is a named agent saving time / worth it (M17 study status + its governed usage)",
    "reliability": "how reliable the agents are overall, which agents fail most (M10, M11)",
    "agent_usage": "which agents are used most, list of agents in use",
    "build_compare": "compare engineer-built vs drag-and-drop agents",
    "team_usage": "usage by team, which team uses it least or most (small teams suppressed)",
    "region_compare": "compare markets/regions, best or worst region",
    "trend": "is usage going up or down, weekly trend within the closed period",
    "freshness": "data freshness, late data, restatement (M12)",
    "alerts": "current alerts, risks, what to worry about",
    "reclaim": "which seats to reclaim or cut at renewal (seat reclaim finder)",
    "outcome": "outcome metrics needing study data: task success M07, fraud handle time M08, onboarding cycle time M09, time per task M06",
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
    """Pick the active brain: NP_BRAIN=rules|ollama|openai|finetuned|auto (default auto). finetuned = FT_MODEL via Ollama.
    auto: local open model via Ollama if reachable, else an OpenAI-compatible key if set, else rules. Cached 30 s."""
    import time
    pref = os.environ.get("NP_BRAIN", "auto").lower()
    if not refresh and _BRAIN["v"] and time.time() - _BRAIN["t"] < 30 and _BRAIN["v"]["pref"] == pref:
        return _BRAIN["v"]
    v = dict(kind="rules", label="Rules engine", route=None, pref=pref)
    if pref == "finetuned":                       # opt-in only, never picked by auto
        if FT.ready():
            v = dict(kind="finetuned", label=f"Fine-tuned model ({FT.ft_model()})", route=None, pref=pref)
    elif pref in ("auto", "ollama") and _ollama_ready():
        v = dict(kind="ollama", label=f"Open model ({ollama_model()} via Ollama)", route=ollama_route, pref=pref)
    elif pref in ("auto", "openai") and llm_enabled():
        v = dict(kind="openai", label=f"LLM router ({os.environ.get('LLM_MODEL', 'gpt-4o-mini')})", route=llm_route, pref=pref)
    _BRAIN.update(t=time.time(), v=v)
    return v


def brain_info():
    b = brain()
    return dict(kind=b["kind"], label=b["label"], ollama_host=ollama_host(), ollama_model=FT.ft_model() if b["kind"] == "finetuned" else ollama_model())


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
