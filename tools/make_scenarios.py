"""Build the 8 SYNTHETIC scenario data sets in app/data/scenarios/ from the workbook-exported base CSVs.
Each scenario is a transformation of the base data, so the pipeline (not hand-typed numbers) produces
every figure. Deterministic. Not NimbusPay figures. Run: python tools/make_scenarios.py"""
import csv, json, os, shutil, datetime as dt
ROOT = os.path.join(os.path.dirname(__file__), "..", "app", "data")
BASE, OUT = os.path.join(ROOT, "base"), os.path.join(ROOT, "scenarios")
START = dt.datetime(2026, 9, 7)
F = "%Y-%m-%d %H:%M:%S"

def rd(fn):
    with open(os.path.join(BASE, fn)) as f: return list(csv.DictReader(f))

def wr(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

class Gen:
    def __init__(self, events, seats):
        self.ev, self.n = events, 0
        self.team = {s["user_id"]: (s["team_id"], s["region"]) for s in seats}
    def _id(self, p):
        self.n += 1; return f"{p}-{self.n:04d}"
    def add(self, user, etype, agent, t, iid="", rid="", status="ok", src="platform"):
        team, region = self.team[user]
        self.ev.append(dict(event_id=self._id("SE"), interaction_id=iid, run_id=rid, event_time=t.strftime(F),
                            ingested_at=(t + dt.timedelta(seconds=120)).strftime(F), region=region, team_id=team, user_id=user,
                            event_type=etype, agent_id=agent, log_source=src, status=status, truth_id=""))
    def login(self, user, day, hour=8):
        self.add(user, "login", "", START + dt.timedelta(days=day - 1, hours=hour))
    def question(self, user, agent, day, hour=11, sdk=True):
        t = START + dt.timedelta(days=day - 1, hours=hour, minutes=7)
        iid, rid, src = (self._id("SI"), self._id("SR"), "sdk") if sdk else ("", "", "builder_ui")
        self.login(user, day, hour)
        self.add(user, "agent_run", agent, t, iid, rid, src=src)
        if sdk: self.add(user, "search", agent, t + dt.timedelta(seconds=1), iid, rid, src=src)
        self.add(user, "connector_call", agent, t + dt.timedelta(seconds=2), iid, rid, src=src)
        self.add(user, "response", agent, t + dt.timedelta(seconds=5), iid, rid, src=src)

S = {}
def scenario(key, label, note, expect, outcomes):
    def deco(fn): S[key] = (label, note, expect, outcomes, fn); return fn
    return deco

@scenario("baseline", "Baseline (workbook data set)", "The v10 workbook's 210-row synthetic set exactly. Utilisation just under the agreed threshold.",
          "Renew and right-size", dict(verified_hours_week=180, cost_index=0.9))
def _b(ev, se, rg, g): pass

@scenario("healthy", "Healthy adoption", "Idle seats activated, most users return weekly, verified hours reported, unit cost inside the threshold.",
          "Expand", dict(verified_hours_week=260, cost_index=0.7))
def _h(ev, se, rg, g):
    for u, a, sdk in [("USER-104", "AG-FRAUD-01", 1), ("USER-105", "AG-FRAUD-01", 1), ("USER-103", "AG-FRAUD-01", 1), ("USER-122", "AG-KYC-04", 1),
                      ("USER-123", "AG-KYC-04", 1), ("USER-124", "AG-KYC-04", 1), ("USER-113", "AG-SUMM-03", 0), ("USER-134", "AG-ONB-02", 0)]:
        for d in (4, 11, 18, 25): g.question(u, a, d, sdk=bool(sdk))

@scenario("overstated", "Overstated usage (vendor MAU high)", "Everyone logs in, so the vendor MAU proxy looks great, but few people return. Unit cost per verified hour is high.",
          "Renegotiate", dict(verified_hours_week=70, cost_index=1.9))
def _o(ev, se, rg, g):
    for s in se:
        if s["provisioned"] == "Yes":
            for d in (3, 10, 17, 24): g.login(s["user_id"], d, 9)
    g.question("USER-104", "AG-FRAUD-01", 6); g.question("USER-113", "AG-SUMM-03", 6, sdk=False); g.question("USER-123", "AG-KYC-04", 6)

@scenario("shelfware", "Shelfware (paid seats unused)", "Six users stop using the assistant and purchased seats grow to 40; many paid and assigned seats have no qualifying use.",
          "Renew and right-size", dict(verified_hours_week=150, cost_index=0.95))
def _s(ev, se, rg, g):
    drop = {"USER-103", "USER-112", "USER-122", "USER-124", "USER-132", "USER-142"}
    ev[:] = [e for e in ev if e["user_id"] not in drop or e["event_type"] == "login"]
    for s in se:
        if s["team_id"] in ("TEAM-A1", "TEAM-B2"): s["purchased_seats"] = str(int(s["purchased_seats"]) + 4)
        if s["team_id"] == "TEAM-C2": s["purchased_seats"] = str(int(s["purchased_seats"]) + 1)

@scenario("newcountry", "New-country launch cohort", "A new country (Region D) launches with 8 seats and is still ramping; no verified study yet.",
          "Continue limited pilot", dict(verified_hours_week="", cost_index=""))
def _n(ev, se, rg, g):
    for i in range(1, 9):
        u = f"USER-2{i:02d}"
        se.append(dict(team_id="TEAM-D1", region="Region D (new country launch)", purchased_seats="10", user_id=u,
                       assigned="Yes", provisioned="Yes" if i <= 7 else "No"))
        g.team[u] = ("TEAM-D1", "Region D (new country launch)")
    g.question("USER-201", "AG-ONB-02", 22, sdk=False); g.question("USER-201", "AG-ONB-02", 27, sdk=False)
    g.question("USER-202", "AG-ONB-02", 26, sdk=False)
    for u in ("USER-203", "USER-204", "USER-205"): g.login(u, 24)

@scenario("incident", "Reliability incident (connector outage)", "Connector outage on the onboarding agent: most connector calls fail for two weeks.",
          "Renew with remediation conditions", dict(verified_hours_week=190, cost_index=0.85))
def _i(ev, se, rg, g):
    for e in ev:
        if e["event_type"] == "connector_call" and e["agent_id"] in ("AG-ONB-02", "AG-SUMM-03"): e["status"] = "failed"

@scenario("noids", "Missing interaction IDs", "The SDK release dropped interaction IDs, so every interaction is sessionised (approximate) and no study can attribute impact.",
          "Continue limited pilot", dict(verified_hours_week=200, cost_index=0.8))
def _x(ev, se, rg, g):
    for e in ev:
        if e["event_type"] != "login": e["interaction_id"] = ""; e["run_id"] = ""

@scenario("breach", "Critical-risk breach (privacy)", "Card data found outside the masked zone in an agent log: the score turns red and renewal needs remediation.",
          "Renew with remediation conditions", dict(verified_hours_week=230, cost_index=0.8,
          critical_risk="Card numbers found outside the masked zone in AG-FRAUD-01 logs (synthetic incident)"))
def _r(ev, se, rg, g): pass

def main():
    if os.path.exists(OUT): shutil.rmtree(OUT)
    index = []
    for key, (label, note, expect, outcomes, fn) in S.items():
        ev, se, rg = rd("events.csv"), rd("seats.csv"), rd("registry.csv")
        g = Gen(ev, se); fn(ev, se, rg, g)
        d = os.path.join(OUT, key); os.makedirs(d)
        wr(os.path.join(d, "events.csv"), ev); wr(os.path.join(d, "seats.csv"), se); wr(os.path.join(d, "registry.csv"), rg)
        json.dump(dict(outcomes, label="Synthetic; illustrative inputs (cost index uses a placeholder platform cost)"),
                  open(os.path.join(d, "outcomes.json"), "w"), indent=1)
        index.append(dict(key=key, label=label, note=note, expected_outcome=expect))
    json.dump(index, open(os.path.join(OUT, "index.json"), "w"), indent=1)
    print("built", len(index), "scenarios")

if __name__ == "__main__":
    main()
