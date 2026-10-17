"""Product features on top of the pipeline: seat reclaim finder, renewal what-if simulator, metric lineage,
vendor bill reconciler. All figures SYNTHETIC; the seat price is a placeholder in abstract price units."""
import copy, json, math, os
from . import config as C, pipeline as P

HERE = os.path.dirname(__file__)


# ---------------- 1. Seat reclaim finder ----------------
def seat_reclaim(data, res):
    active = set(res["users"]["active"])
    teams = {}
    for s in data["seats"]:
        t = teams.setdefault(s["team_id"], dict(team=s["team_id"], region=s["region"], purchased=int(s["purchased_seats"]),
                                                 assigned=0, not_provisioned=0, provisioned_idle=0, active=0))
        if s["assigned"].lower() == "yes":
            t["assigned"] += 1
            if s["provisioned"].lower() != "yes": t["not_provisioned"] += 1
            elif s["user_id"] in active: t["active"] += 1
            else: t["provisioned_idle"] += 1
    rows = []
    for t in teams.values():
        t["never_assigned"] = t["purchased"] - t["assigned"]
        idle = t["not_provisioned"] + t["provisioned_idle"]
        buffer = math.ceil(t["assigned"] * C.RECLAIM_KEEP_BUFFER) if idle else 0
        t["reclaimable"] = t["never_assigned"] + max(0, idle - buffer)
        t["buffer_kept"] = min(buffer, idle)
        t["action"] = ("Do not renew unassigned seats; " if t["never_assigned"] else "") + \
                      ("enable or reassign idle seats" if idle else "no action") + (" (launch cohort: review after ramp-up)" if "launch" in t["region"].lower() else "")
        rows.append(t)
    total = sum(t["reclaimable"] for t in rows)
    return dict(label="Synthetic. Seat price is a placeholder in price units, not a real price.",
                rows=sorted(rows, key=lambda t: -t["reclaimable"]), purchased=sum(t["purchased"] for t in rows),
                reclaimable=total, unit_price=C.SEAT_PRICE_PLACEHOLDER, reclaim_value=total * C.SEAT_PRICE_PLACEHOLDER,
                note=f"Reclaimable = never-assigned seats + idle assigned seats (not provisioned, or provisioned with no qualifying use), "
                     f"keeping {int(C.RECLAIM_KEEP_BUFFER * 100)}% headroom per team. Team-level only: no individual is named.")


# ---------------- 2. Renewal what-if simulator ----------------
def whatif(data, seats=None, connector_fix=False, id_coverage=None):
    """Re-run the full pipeline on a modified copy of the data. Not a forecast.
    seats: total purchased seats at renewal (idle seats are unassigned first);
    connector_fix: failed connector calls succeed; id_coverage: % of sessionised interactions that carry an interaction ID."""
    d = copy.deepcopy(data)
    base, _ = P.run(copy.deepcopy(data))
    if connector_fix:
        for e in d["events"]:
            if e["event_type"] == "connector_call" and e["status"] == "failed": e["status"] = "ok"
    if id_coverage is not None:
        R = P.compute_core(copy.deepcopy(d))
        sess = sorted((v for v in R["inter"].values() if v["method"] == "approximate"), key=lambda v: v["start"])
        k = round(len(sess) * max(0, min(100, id_coverage)) / 100)
        keep = {e["event_id"]: v["id"] for v in sess[:k] for e in v["ev"]}
        for e in d["events"]:
            if e["event_id"] in keep: e["interaction_id"] = "WI-" + keep[e["event_id"]]
    if seats is not None:
        seats = max(0, int(seats))
        active = set(base["users"]["active"])
        assigned = [s for s in d["seats"] if s["assigned"].lower() == "yes"]
        excess = len(assigned) - seats
        if excess > 0:   # unassign idle seats first (not provisioned, then provisioned-idle); active users only if unavoidable
            order = sorted(assigned, key=lambda s: (s["user_id"] in active, s["provisioned"].lower() == "yes"))
            for s in order[:excess]: s["assigned"] = "No"; s["provisioned"] = "No"
        teams = {}
        for s in d["seats"]: teams.setdefault(s["team_id"], []).append(s)
        asg = {t: sum(x["assigned"].lower() == "yes" for x in v) for t, v in teams.items()}
        spare = max(0, seats - sum(asg.values())); tot = sum(asg.values()) or 1
        alloc = {t: a + math.floor(spare * a / tot) for t, a in asg.items()}
        rest = seats - sum(alloc.values())
        for t in sorted(alloc, key=lambda t: -asg[t])[:max(0, rest)]: alloc[t] += 1
        for t, v in teams.items():
            for s in v: s["purchased_seats"] = str(alloc[t])
    new, _ = P.run(d)
    def snap(r):
        return dict(funnel=r["funnel"], M01=r["metrics"]["M01"]["value"], M11=r["metrics"]["M11"]["value"], exact_share=r["grouping"]["exact_share"],
                    pillars=r["score"]["pillars"], score=r["score"]["value"], score_state=r["score"]["state"], interim=r["score"]["interim_index"],
                    outcome=r["renewal"]["outcome"], why=r["renewal"]["why"], evidence=r["renewal"]["evidence"], paid_unused=r["paid_unused"])
    return dict(label="Synthetic what-if. Not a forecast: it re-runs the same rules on modified data.",
                inputs=dict(seats=seats, connector_fix=connector_fix, id_coverage=id_coverage), before=snap(base), after=snap(new))


# ---------------- 3. Explain-this-number lineage ----------------
OWNER_ROLE = {"M01": "Licence / IT asset manager", "M02": "Product analytics lead", "M04": "Product analytics lead", "M07": "Business process owner",
              "M10": "Platform engineering lead", "M11": "Platform engineering lead", "M12": "Data engineering lead", "M16": "AI platform governance lead",
              "M17": "Finance + analytics (study owner)", "M18": "Finance and Procurement", "M19": "Product analytics lead (sponsor: CIO office)",
              "M20": "Platform engineering lead"}
LINEAGE = {
    "M01": (["seats.csv -> seats", "events.csv -> events_clean -> interactions -> user_funnel"],
            "SELECT ROUND(100.0*SUM(active)/SUM(assigned),1) FROM user_funnel WHERE assigned = 1;"),
    "M02": (["seats.csv -> seats", "events.csv -> interactions -> user_funnel (habitual = active in 3+ of 4 weeks)"],
            "SELECT ROUND(100.0*SUM(habitual)/SUM(assigned),1) FROM user_funnel WHERE assigned = 1;"),
    "M04": (["events.csv -> events_clean -> interactions", "user_funnel"],
            "SELECT ROUND(1.0*(SELECT COUNT(*) FROM interactions WHERE qualifying=1)/(SELECT SUM(active) FROM user_funnel),2);"),
    "M07": (["Task outcome labels (not in this data set)"], None),
    "M10": (["events.csv -> events_clean (event_type = agent_run)"],
            "SELECT ROUND(100.0*SUM(status='failed')/COUNT(*),1) FROM events_clean WHERE event_type='agent_run';"),
    "M11": (["events.csv -> events_clean (event_type = connector_call)"],
            "SELECT ROUND(100.0*SUM(status='failed')/COUNT(*),1) FROM events_clean WHERE event_type='connector_call';"),
    "M12": (["events.csv ingested_at vs event_time; period close"], "SELECT SUM(late) FROM events_clean;"),
    "M16": (["registry.csv -> agent_registry", "events_clean"],
            "SELECT COUNT(DISTINCT e.agent_id) FROM events_clean e JOIN agent_registry r ON r.agent_id=e.agent_id WHERE e.event_type<>'login' AND r.registered=0;"),
    "M17": (["outcomes input: verified hours from the agreed study (staggered rollout / holdout)", "interactions (exact-share gate)"], None),
    "M18": (["outcomes input: cost index vs current process (placeholder platform cost)", "M17"], None),
    "M19": (["M01, M02 (Reach)", "M04 (Depth)", "M17 (Outcome)", "M10, M11 (Reliability)", "M20, M16 (Trust)", "critical-risk register"], None),
    "M20": (["events.csv -> events_clean", "registry.csv (build type)"],
            "SELECT build_type, ROUND(100.0*SUM(has_interaction_id=0)/COUNT(*),1) FROM events_clean WHERE event_type<>'login' GROUP BY build_type;"),
}


def lineage(mid, res, db):
    if mid not in res["metrics"]:
        return None
    dic = {m["Metric ID"]: m for m in json.load(open(os.path.join(HERE, "..", "src", "data.json")))["Metric_Dictionary"]}.get(mid, {})
    src, sql = LINEAGE.get(mid, ([], None))
    check = None
    if sql:
        rows = db.execute(sql).fetchall()
        check = [list(r) for r in rows] if len(rows) > 1 else rows[0][0]
    m = res["metrics"][mid]
    return dict(metric=mid, name=m["label"], value=m["value"], unit=m["unit"], version=m["version"], approximate=m["approximate"], note=m["note"],
                formula=dic.get("Formula"), missing_data_rule=dic.get("Missing-data rule"), tests=dic.get("Tests"),
                owner=dic.get("Owner", "To be named"), proposed_owner_role=OWNER_ROLE.get(mid, "To be named"), sources=src, sql=sql, sql_result=check,
                pipeline=["validate", "dedupe on event_id", "period close + restatement", "group interactions (IR5 exact / IR6 approximate)", "funnel LF1-LF6", "metric"],
                freshness=dict(data_as_of=res["data_as_of"], late_events=res["quality"]["late"], after_close_rows=res["quality"]["after_close"], period=res["period"]),
                label="Synthetic data")


# ---------------- 4. Vendor bill reconciler ----------------
INVOICE_COLS = ["invoice_id", "team_id", "billed_seats"]


def reconcile(invoice_csv, data, res):
    rows = P._read(invoice_csv, INVOICE_COLS, "invoice.csv")
    active = set(res["users"]["active"])
    teams = {}
    for s in data["seats"]:
        t = teams.setdefault(s["team_id"], dict(purchased=int(s["purchased_seats"]), assigned=0, active=0))
        if s["assigned"].lower() == "yes":
            t["assigned"] += 1; t["active"] += s["user_id"] in active
    out, billed_teams = [], set()
    for i, r in enumerate(rows, 2):
        try: billed = int(float(r["billed_seats"]))
        except ValueError: raise P.ValidationError(f"invoice.csv: billed_seats '{r['billed_seats']}' is not a number on row {i}")
        tid = r["team_id"]; billed_teams.add(tid); t = teams.get(tid)
        try: price = float(r.get("unit_price") or C.SEAT_PRICE_PLACEHOLDER)
        except ValueError: price = C.SEAT_PRICE_PLACEHOLDER
        flags = []
        if not t:
            flags.append("Team not in our seat roster"); t = dict(purchased=0, assigned=0, active=0)
        if billed > t["purchased"]: flags.append(f"Billed {billed} > contracted/purchased {t['purchased']}: query overbilling")
        if billed > t["assigned"]: flags.append(f"{billed - t['assigned']} billed seats not assigned to anyone")
        if t["active"] < billed * 0.5: flags.append(f"Only {t['active']} of {billed} billed seats have qualifying use")
        if billed < t["assigned"]: flags.append(f"Billed {billed} < assigned {t['assigned']}: check true-up terms")
        out.append(dict(invoice_id=r["invoice_id"], team=tid, billed=billed, purchased=t["purchased"], assigned=t["assigned"], active=t["active"],
                        unit_price=price, billed_value=billed * price, unused_value=max(0, billed - t["active"]) * price,
                        status="mismatch" if any(f.startswith(("Billed", "Team not")) and "true-up" not in f for f in flags) else ("review" if flags else "ok"), flags=flags))
    for tid, t in teams.items():
        if tid not in billed_teams:
            out.append(dict(invoice_id="-", team=tid, billed=0, purchased=t["purchased"], assigned=t["assigned"], active=t["active"], unit_price=C.SEAT_PRICE_PLACEHOLDER,
                            billed_value=0, unused_value=0, status="review", flags=["Team in roster but not on the invoice"]))
    return dict(label="Synthetic invoice; prices are placeholders in price units.", rows=out,
                totals=dict(billed=sum(r["billed"] for r in out), purchased=sum(t["purchased"] for t in teams.values()),
                            assigned=sum(t["assigned"] for t in teams.values()), active=sum(t["active"] for t in teams.values()),
                            billed_value=sum(r["billed_value"] for r in out), unused_value=sum(r["unused_value"] for r in out),
                            mismatches=sum(r["status"] == "mismatch" for r in out), reviews=sum(r["status"] == "review" for r in out)))
