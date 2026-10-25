"""Ingest -> validate -> clean -> group into logical interactions -> licence funnel -> governed metrics ->
M19 value score -> renewal outcome. Loads a local SQLite warehouse so every metric has real SQL behind it.
All data is SYNTHETIC."""
import csv, io, sqlite3, datetime as dt
from collections import defaultdict
from . import config as C

EVENT_COLS = ["event_id", "interaction_id", "run_id", "event_time", "ingested_at", "region", "team_id", "user_id",
              "event_type", "agent_id", "log_source", "status"]
SEAT_COLS = ["team_id", "region", "purchased_seats", "user_id", "assigned", "provisioned"]
REG_COLS = ["agent_id", "name", "registered", "build_type", "log_source"]
EVENT_TYPES = {"login", "agent_run", "search", "connector_call", "response"}


class ValidationError(ValueError):
    pass


def _read(text, required, name):
    rd = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    missing = [c for c in required if c not in (rd.fieldnames or [])]
    if missing:
        raise ValidationError(f"{name}: missing columns {missing}")
    return [{k: (v or "").strip() for k, v in r.items() if k} for r in rd]


def _ts(s, name, rid):
    try:
        return dt.datetime.fromisoformat(s.replace("T", " ").replace("Z", ""))
    except Exception:
        raise ValidationError(f"{name}: bad timestamp '{s}' on row {rid}")


def load(events_csv, seats_csv, registry_csv, outcomes=None):
    """Parse + validate the three CSVs. outcomes: dict (verified_hours_week, cost_index, critical_risk) or None."""
    ev = _read(events_csv, EVENT_COLS, "events.csv")
    seats = _read(seats_csv, SEAT_COLS, "seats.csv")
    reg = {r["agent_id"]: r for r in _read(registry_csv, REG_COLS, "registry.csv")}
    issues = []
    for i, r in enumerate(ev, 2):
        if r["event_type"] not in EVENT_TYPES:
            raise ValidationError(f"events.csv: unknown event_type '{r['event_type']}' on row {i}")
        r["event_time"] = _ts(r["event_time"], "events.csv", i)
        r["ingested_at"] = _ts(r["ingested_at"], "events.csv", i)
        if r["event_type"] != "login" and not r["agent_id"]:
            raise ValidationError(f"events.csv: non-login event without agent_id on row {i}")
        if r["agent_id"] and r["agent_id"] not in reg:
            issues.append(f"Agent {r['agent_id']} not in registry file; treated as unregistered")
            reg[r["agent_id"]] = {"agent_id": r["agent_id"], "name": "Unknown (found in logs)", "registered": "No",
                                  "build_type": "", "log_source": r["log_source"]}
    return dict(events=ev, seats=seats, registry=reg, outcomes=outcomes or {}, issues=sorted(set(issues)))


def build_type(reg, agent):
    a = reg[agent]
    if a.get("build_type"):
        return a["build_type"], "Registry"
    return ("Drag-and-drop" if a.get("log_source") == "builder_ui" else "Engineer-built"), "Backfill classifier (to confirm)"


def compute_core(data, include_after_close=False, start=C.PERIOD_START):
    close = start + dt.timedelta(days=C.PERIOD_DAYS, hours=C.CLOSE_AFTER_H)
    rows, reg = data["events"], data["registry"]
    seen, clean, dup, late, after = set(), [], 0, 0, 0
    for r in sorted(rows, key=lambda r: r["ingested_at"]):          # keep first-ingested copy
        if r["event_id"] in seen:
            dup += 1; continue
        seen.add(r["event_id"])
        if r["ingested_at"] > close:
            after += 1
            if not include_after_close:
                continue
        r["late"] = (r["ingested_at"] - r["event_time"]).total_seconds() > C.LATE_H * 3600
        late += r["late"]
        clean.append(r)
    inter = {}
    for r in clean:                                                  # IR5: exact grouping by interaction ID
        if r["event_type"] != "login" and r["interaction_id"]:
            inter.setdefault(r["interaction_id"], dict(method="exact", ev=[]))["ev"].append(r)
    sess = defaultdict(list)                                         # IR6: sessionisation fallback (approximate)
    for r in clean:
        if r["event_type"] != "login" and not r["interaction_id"]:
            sess[(r["user_id"], r["agent_id"])].append(r)
    n = 0
    for key in sess:
        evs = sorted(sess[key], key=lambda r: r["event_time"]); last = None
        for r in evs:
            if last is None or (r["event_time"] - last).total_seconds() > C.SESSION_GAP_S:
                n += 1; cur = f"SESS-{n:04d}"; inter[cur] = dict(method="approximate", ev=[])
            inter[cur]["ev"].append(r); last = r["event_time"]
    for k, v in inter.items():
        types = {e["event_type"] for e in v["ev"]}
        first = min(v["ev"], key=lambda e: e["event_time"])
        v.update(id=k, qual="agent_run" in types and "response" in types, user=first["user_id"], agent=first["agent_id"],
                 team=first["team_id"], region=first["region"], day=(first["event_time"] - start).days + 1,
                 start=first["event_time"], n_events=len(v["ev"]))
        v["bt"], v["bt_src"] = build_type(reg, v["agent"])
    q = {k: v for k, v in inter.items() if v["qual"]}
    days = defaultdict(set)
    for v in q.values():
        days[v["user"]].add(v["day"])
    active = set(days)
    engaged = {u for u, d in days.items() if len(d) >= 2}
    habitual = {u for u, d in days.items() if len({(x - 1) // 7 for x in d}) >= 3}
    truth = {r.get("truth_id") for r in clean if r.get("truth_id") and r["event_type"] == "response"}
    return dict(clean=clean, dup=dup, late=late, after=after, inter=inter, q=q, active=active, engaged=engaged,
                habitual=habitual, anyevent={r["user_id"] for r in clean}, truth=truth, close=close, days=days)


def pct(a, b):
    return round(100 * a / b, 1) if b else None


def norm(mid, x, invert=False):
    lo, hi = C.NORM[mid]
    s = max(0.0, min(100.0, 100 * (x - lo) / (hi - lo)))
    return 100 - s if invert else s


def warehouse(data, R):
    """Load the clean, grouped data into an in-memory SQLite warehouse (read-only use by the agent)."""
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.executescript("""
    CREATE TABLE events_clean(event_id TEXT PRIMARY KEY, interaction_key TEXT, run_id TEXT, event_time TEXT, ingested_at TEXT,
      late INT, region TEXT, team_id TEXT, user_id TEXT, event_type TEXT, agent_id TEXT, build_type TEXT, has_interaction_id INT, status TEXT);
    CREATE TABLE interactions(interaction_key TEXT PRIMARY KEY, method TEXT, qualifying INT, user_id TEXT, team_id TEXT, region TEXT,
      agent_id TEXT, build_type TEXT, build_type_source TEXT, day INT, n_events INT);
    CREATE TABLE seats(team_id TEXT, region TEXT, purchased_seats INT, user_id TEXT, assigned INT, provisioned INT);
    CREATE TABLE agent_registry(agent_id TEXT PRIMARY KEY, name TEXT, registered INT, build_type TEXT, build_type_used TEXT);
    CREATE TABLE user_funnel(user_id TEXT PRIMARY KEY, team_id TEXT, region TEXT, assigned INT, provisioned INT, active INT, engaged INT, habitual INT);
    """)
    key_of = {}
    for k, v in R["inter"].items():
        for e in v["ev"]:
            key_of[e["event_id"]] = k
        db.execute("INSERT INTO interactions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (k, v["method"], int(v["qual"]), v["user"], v["team"], v["region"], v["agent"], v["bt"], v["bt_src"], v["day"], v["n_events"]))
    for r in R["clean"]:
        bt = build_type(data["registry"], r["agent_id"])[0] if r["agent_id"] else None
        if bt and data["registry"][r["agent_id"]].get("build_type") == "":
            bt = "Drag-and-drop" if bt == "Drag-and-drop" else bt
        db.execute("INSERT INTO events_clean VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (r["event_id"], key_of.get(r["event_id"]), r["run_id"], str(r["event_time"]), str(r["ingested_at"]), int(r["late"]),
                    r["region"], r["team_id"], r["user_id"], r["event_type"], r["agent_id"], bt, int(bool(r["interaction_id"])), r["status"]))
    for s in data["seats"]:
        db.execute("INSERT INTO seats VALUES(?,?,?,?,?,?)", (s["team_id"], s["region"], int(s["purchased_seats"]), s["user_id"],
                                                             int(s["assigned"].lower() == "yes"), int(s["provisioned"].lower() == "yes")))
    for a in data["registry"].values():
        db.execute("INSERT INTO agent_registry VALUES(?,?,?,?,?)", (a["agent_id"], a["name"], int(a["registered"].lower() == "yes"),
                                                                    a["build_type"] or None, build_type(data["registry"], a["agent_id"])[0]))
    for s in data["seats"]:
        u = s["user_id"]
        db.execute("INSERT OR REPLACE INTO user_funnel VALUES(?,?,?,?,?,?,?,?)", (u, s["team_id"], s["region"], int(s["assigned"].lower() == "yes"),
                   int(s["provisioned"].lower() == "yes"), int(u in R["active"]), int(u in R["engaged"]), int(u in R["habitual"])))
    db.commit()
    return db


def run(data):
    """Full pipeline. Returns a JSON-able result dict plus the SQLite warehouse."""
    R = compute_core(data, False)
    RR = compute_core(data, True)
    reg = data["registry"]
    clean, q = R["clean"], R["q"]
    nonlogin = [r for r in clean if r["event_type"] != "login"]
    runs = [r for r in clean if r["event_type"] == "agent_run"]
    conn = [r for r in clean if r["event_type"] == "connector_call"]
    teams = {}
    for s in data["seats"]:
        teams.setdefault(s["team_id"], dict(team=s["team_id"], region=s["region"], purchased=int(s["purchased_seats"]), users=[]))["users"].append(s)
    assigned_users = [s["user_id"] for s in data["seats"] if s["assigned"].lower() == "yes"]
    purchased = sum(t["purchased"] for t in teams.values())
    assigned = len(assigned_users)
    provisioned = sum(1 for s in data["seats"] if s["provisioned"].lower() == "yes")
    act_a = [u for u in assigned_users if u in R["active"]]
    eng_a = [u for u in assigned_users if u in R["engaged"]]
    hab_a = [u for u in assigned_users if u in R["habitual"]]
    funnel = dict(LF1=purchased, LF2=assigned, LF3=provisioned, LF4=len(R["active"]), LF5=len(R["engaged"]), LF6=len(R["habitual"]))
    # per region
    regions = {}
    for t in teams.values():
        g = regions.setdefault(t["region"], dict(region=t["region"], purchased=0, assigned=0, provisioned=0, active=0, engaged=0, habitual=0, teams=[]))
        ua = [s["user_id"] for s in t["users"] if s["assigned"].lower() == "yes"]
        tr = dict(team=t["team"], purchased=t["purchased"], assigned=len(ua),
                  provisioned=sum(1 for s in t["users"] if s["provisioned"].lower() == "yes"),
                  active=sum(u in R["active"] for u in ua), engaged=sum(u in R["engaged"] for u in ua), habitual=sum(u in R["habitual"] for u in ua))
        tr["suppressed"] = tr["assigned"] < C.MIN_GROUP
        g["teams"].append(tr)
        for k in ("purchased", "assigned", "provisioned", "active", "engaged", "habitual"):
            g[k] += tr[k]
    for g in regions.values():
        g["M01"] = pct(g["active"], g["assigned"]); g["M02"] = pct(g["habitual"], g["assigned"])
        rconn = [r for r in conn if r["region"] == g["region"]]
        g["M11"] = pct(sum(r["status"] == "failed" for r in rconn), len(rconn))
        g["launch_cohort"] = "launch" in g["region"].lower()
    # reliability by agent and connector proxy
    agents = []
    for a in sorted(reg):
        ar = [r for r in runs if r["agent_id"] == a]; ac = [r for r in conn if r["agent_id"] == a]
        ae = [r for r in nonlogin if r["agent_id"] == a]
        if not ae and reg[a]["registered"].lower() == "yes" and not any(r["agent_id"] == a for r in data["events"]):
            pass
        bt, src = build_type(reg, a)
        agents.append(dict(agent=a, name=reg[a]["name"], registered=reg[a]["registered"].lower() == "yes", build_type=bt, build_type_source=src,
                           runs=len(ar), failed_runs=sum(r["status"] == "failed" for r in ar), M10=pct(sum(r["status"] == "failed" for r in ar), len(ar)),
                           calls=len(ac), failed_calls=sum(r["status"] == "failed" for r in ac), M11=pct(sum(r["status"] == "failed" for r in ac), len(ac)),
                           qualifying=sum(v["agent"] == a for v in q.values()),
                           M20=pct(sum(not r["interaction_id"] for r in ae), len(ae))))
    m20 = {}
    for bt in ("Engineer-built", "Drag-and-drop"):
        ev = [r for r in nonlogin if build_type(reg, r["agent_id"])[0] == bt]
        m20[bt] = dict(noid=sum(not r["interaction_id"] for r in ev), events=len(ev), pct=pct(sum(not r["interaction_id"] for r in ev), len(ev)))
    exact_q = sum(v["method"] == "exact" for v in q.values())
    out = data["outcomes"]
    vh = out.get("verified_hours_week"); vh = float(vh) if vh not in (None, "") else None
    ci = out.get("cost_index"); ci = float(ci) if ci not in (None, "") else None
    risk = (out.get("critical_risk") or "").strip()
    exact_share = pct(exact_q, len(q)) or 0.0
    attributable = exact_share >= C.EXACT_SHARE_MIN
    M = {}
    def m(mid, value, unit, label, approx=False, note=""):
        M[mid] = dict(id=mid, value=value, unit=unit, label=label, approximate=approx, note=note, version=C.METRIC_VERSION)
    m("M01", pct(len(act_a), assigned), "%", "Licence utilisation", note=f"{len(act_a)} active / {assigned} assigned")
    m("M02", pct(len(hab_a), assigned), "%", "Habitual users", note=f"{len(hab_a)} habitual / {assigned} assigned")
    m("M04", round(len(q) / len(R["active"]), 2) if R["active"] else None, "per user", "Interactions per active user",
      approx=exact_share < 100, note=f"{len(q)} qualifying interactions / {len(R['active'])} active users")
    m("M07", None, "%", "Task success rate", note="Needs task outcome labels; not in this data set (withheld, no imputation)")
    m("M10", pct(sum(r["status"] == "failed" for r in runs), len(runs)), "%", "Agent error rate",
      note=f"{sum(r['status'] == 'failed' for r in runs)}/{len(runs)} runs failed")
    m("M11", pct(sum(r["status"] == "failed" for r in conn), len(conn)), "%", "Connector failure rate",
      note=f"{sum(r['status'] == 'failed' for r in conn)}/{len(conn)} calls failed")
    m("M12", R["late"], "late events", "Data freshness", note=f"{R['late']} late events; {R['after']} rows after close go to restatement")
    m("M16", sum(1 for a in {r['agent_id'] for r in nonlogin} if reg[a]["registered"].lower() != "yes"), "agents", "Unregistered agents")
    vh_ok = vh is not None and attributable
    m("M17", vh if vh_ok else None, "hours / week", "Verified hours saved",
      note="From the agreed study" if vh_ok else ("Withheld: no verified study result" if vh is None else f"Withheld: only {exact_share}% of interactions are exact, so impact cannot be attributed"))
    m("M18", ci if (vh_ok and ci is not None) else None, "index vs current process", "Cost per verified hour",
      note="Index vs the current process (1.0 = parity). Platform cost is a PLACEHOLDER input, not a NimbusPay figure.")
    m("M20", pct(sum(not r["interaction_id"] for r in nonlogin), len(nonlogin)), "%", "Events without interaction ID",
      note="; ".join(f"{k}: {v['pct']}% ({v['noid']}/{v['events']})" for k, v in m20.items()))
    # M19 value score with pillars
    pillars = {
        "Reach": round((norm("M01", M["M01"]["value"] or 0) + norm("M02", M["M02"]["value"] or 0)) / 2, 1),
        "Depth": round(norm("M04", M["M04"]["value"] or 0), 1),
        "Outcome": round(norm("M17", M["M17"]["value"]), 1) if M["M17"]["value"] is not None else None,
        "Reliability": round((norm("M10", M["M10"]["value"] or 0, True) + norm("M11", M["M11"]["value"] or 0, True)) / 2, 1),
        "Trust": round(max(0.0, (100 - (M["M20"]["value"] or 0)) - 15 * M["M16"]["value"]), 1),
    }
    if pillars["Outcome"] is None:
        idx = sum(pillars[k] * w for k, w in C.INTERIM_WEIGHTS.items()) / sum(C.INTERIM_WEIGHTS.values())
        score = dict(state="withheld", value=None, interim_index=round(idx), reason="Outcome pillar has no verified data. M19 is withheld (no silent imputation); the interim adoption and health index (33/25/25/17) is shown instead, clearly labelled.")
    else:
        v = sum(pillars[k] * w for k, w in C.WEIGHTS.items()) / sum(C.WEIGHTS.values())
        score = dict(state="red" if risk else "ok", value=round(v), interim_index=None,
                     reason=("Critical-risk override: " + risk + ". Score shown red regardless of value.") if risk else "All pillars present.")
    score.update(pillars=pillars, weights=C.WEIGHTS)
    m("M19", score["value"], "/100", "AI value score", note=score["reason"])
    # renewal engine (Renewal_Criteria: 4 evidence areas -> 5 outcomes)
    util = M["M01"]["value"] or 0
    ev = dict(
        e1="met" if util >= C.UTIL_THRESHOLD else "below",
        e2="met" if vh_ok else "missing",
        e3="missing" if M["M18"]["value"] is None else ("met" if M["M18"]["value"] <= C.COST_INDEX_MAX else "above"),
        e4="gap" if (risk or (M["M11"]["value"] or 0) > C.M11_MAX or (M["M10"]["value"] or 0) > C.M10_MAX) else "met")
    if ev["e2"] == "missing":
        outcome, why = "Continue limited pilot", "Verified impact is missing or cannot be attributed, so value is not yet proven."
    elif ev["e4"] == "gap":
        outcome, why = "Renew with remediation conditions", ("Critical risk: " + risk) if risk else "Reliability is below the agreed gate; renew only with fix-by dates."
    elif ev["e1"] == "below":
        outcome, why = "Renew and right-size", f"Impact is shown but utilisation is {util}% (< {C.UTIL_THRESHOLD}%): reduce or reassign unused seats."
    elif ev["e3"] == "above":
        outcome, why = "Renegotiate", f"Use is real but cost per verified hour index is {M['M18']['value']} (> {C.COST_INDEX_MAX}): seek better price or usage-based terms."
    else:
        outcome, why = "Expand", "Use and impact are strong, unit cost is acceptable and controls are in place."
    data_as_of = max(r["ingested_at"] for r in clean).strftime("%Y-%m-%d %H:%M UTC") if clean else None
    result = dict(
        label="SYNTHETIC DATA. Not NimbusPay figures.", data_as_of=data_as_of,
        period=f"{C.PERIOD_START:%Y-%m-%d} + {C.PERIOD_DAYS} days (close +{C.CLOSE_AFTER_H} h)",
        quality=dict(raw_rows=len(data["events"]), duplicates=R["dup"], after_close=R["after"], clean_events=len(clean), late=R["late"],
                     logins=sum(r["event_type"] == "login" for r in clean), issues=data["issues"]),
        grouping=dict(interactions=len(R["inter"]), exact=sum(v["method"] == "exact" for v in R["inter"].values()),
                      approximate=sum(v["method"] == "approximate" for v in R["inter"].values()), qualifying=len(q),
                      truth_questions=len(R["truth"]) or None, sessionisation_error=(len(R["truth"]) - len(q)) if R["truth"] else None,
                      nonlogin_events=len(nonlogin), inflation=round(len(nonlogin) / len(q), 2) if q else None,
                      raw_events_per_interaction=round(len(clean) / len(R["inter"]), 2) if R["inter"] else None,
                      exact_share=exact_share,
                      by_build_type={bt: sum(v["bt"] == bt for v in q.values()) for bt in ("Engineer-built", "Drag-and-drop")},
                      restated_qualifying=len(RR["q"])),
        users=dict(vendor_mau_proxy=len(R["anyevent"]), active=sorted(R["active"]), engaged=sorted(R["engaged"]), habitual=sorted(R["habitual"]),
                   mau_overstatement=len(R["anyevent"]) - len(R["active"])),
        funnel=funnel, paid_unused=purchased - len(R["active"]), never_assigned=purchased - assigned, assigned_unused=assigned - len(act_a),
        regions=sorted(regions.values(), key=lambda g: g["region"]), agents=agents, m20=m20, metrics=M, score=score,
        renewal=dict(evidence=ev, outcome=outcome, why=why, thresholds=dict(util=C.UTIL_THRESHOLD, exact_share=C.EXACT_SHARE_MIN,
                     cost_index=C.COST_INDEX_MAX, m10=C.M10_MAX, m11=C.M11_MAX)),
        critical_risk=risk or None)
    result["alerts"] = alerts(result)
    return result, warehouse(data, R)


def alerts(res):
    A = []
    def a(sev, mid, text):
        A.append(dict(severity=sev, metric=mid, text=text))
    M = res["metrics"]
    if res["critical_risk"]:
        a("critical", "M19", "Critical risk: " + res["critical_risk"] + ". Value score shown red; renewal needs remediation.")
    if (M["M11"]["value"] or 0) > C.M11_MAX:
        a("high", "M11", f"Connector failure rate {M['M11']['value']}% is above the {C.M11_MAX}% gate.")
    elif (M["M11"]["value"] or 0) > 15:
        a("medium", "M11", f"Connector failure rate {M['M11']['value']}% is elevated (watch level 15%).")
    if (M["M10"]["value"] or 0) > C.M10_MAX:
        a("high", "M10", f"Agent error rate {M['M10']['value']}% is above the {C.M10_MAX}% gate.")
    if M["M16"]["value"]:
        a("medium", "M16", f"{M['M16']['value']} unregistered agent(s) found in logs; build type backfilled, owner to confirm.")
    if res["grouping"]["exact_share"] < C.EXACT_SHARE_MIN:
        a("high", "M20", f"Only {res['grouping']['exact_share']}% of interactions carry an interaction ID: counts approximate, impact not attributable.")
    if (M["M01"]["value"] or 0) < C.UTIL_THRESHOLD:
        a("medium", "M01", f"Licence utilisation {M['M01']['value']}% is below the {C.UTIL_THRESHOLD}% threshold; {res['paid_unused']} paid seats have no qualifying use.")
    if res["quality"]["late"]:
        a("low", "M12", f"{res['quality']['late']} late events (counted on event time, flagged).")
    if res["quality"]["after_close"]:
        a("low", "M12", f"{res['quality']['after_close']} rows arrived after close; restatement adds {res['grouping']['restated_qualifying'] - res['grouping']['qualifying']} qualifying interaction(s).")
    if res["score"]["state"] == "withheld":
        a("info", "M19", "AI value score withheld: Outcome pillar has no verified data (no silent imputation).")
    sup = [t["team"] for g in res["regions"] for t in g["teams"] if t["suppressed"]]
    if sup:
        a("info", "LF4", f"{len(sup)} team(s) have fewer than {C.MIN_GROUP} assigned seats ({', '.join(sup)}); team-level figures suppressed, region totals shown.")
    return A
