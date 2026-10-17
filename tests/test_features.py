"""Seat reclaim, what-if simulator, lineage, vendor bill reconciler."""
import json, os, pytest
from conftest import BASE, SCEN, ROOT, read
from app import pipeline as P, features as F

def data(d=BASE):
    o = {"verified_hours_week": 180, "cost_index": 0.9} if d == BASE else json.load(open(os.path.join(d, "outcomes.json")))
    return P.load(read(os.path.join(d, "events.csv")), read(os.path.join(d, "seats.csv")), read(os.path.join(d, "registry.csv")), o)

@pytest.fixture(scope="module")
def bd():
    d = data(); r, db = P.run(d); return d, r, db

def test_seat_reclaim(bd):
    d, r, _ = bd; s = F.seat_reclaim(d, r)
    assert s["purchased"] == 31 and sum(t["never_assigned"] for t in s["rows"]) == 8          # matches XR24 split (8 never assigned)
    assert sum(t["not_provisioned"] + t["provisioned_idle"] for t in s["rows"]) == 7         # 7 assigned but unused
    assert s["reclaimable"] == 10 and s["reclaim_value"] == 10 * s["unit_price"]
    assert "placeholder" in s["label"].lower() and not any("user" in k for k in s["rows"][0])   # team-level, nobody named

def test_whatif_identity_is_no_change(bd):
    d, _, _ = bd; w = F.whatif(d)
    assert w["before"] == w["after"] and w["before"]["outcome"] == "Renew and right-size"

def test_whatif_rightsizing_seats_flips_outcome(bd):
    d, _, _ = bd; w = F.whatif(d, seats=20)
    assert w["after"]["funnel"]["LF1"] == 20 and w["after"]["funnel"]["LF2"] == 20 and w["after"]["funnel"]["LF4"] == 16   # active users kept
    assert w["after"]["M01"] == 80.0 and w["after"]["outcome"] == "Expand"
    assert d["seats"][0]["purchased_seats"] == "6"                                               # original data untouched

def test_whatif_connector_fix_clears_incident():
    w = F.whatif(data(os.path.join(SCEN, "incident")), connector_fix=True)
    assert w["before"]["outcome"] == "Renew with remediation conditions" and w["after"]["M11"] == 0.0
    assert w["after"]["outcome"] != w["before"]["outcome"] and w["after"]["pillars"]["Reliability"] > w["before"]["pillars"]["Reliability"]

def test_whatif_id_coverage_unblocks_attribution():
    w = F.whatif(data(os.path.join(SCEN, "noids")), id_coverage=100)
    assert w["before"]["exact_share"] == 0.0 and w["after"]["exact_share"] == 100.0
    assert w["before"]["outcome"] == "Continue limited pilot" and w["after"]["evidence"]["e2"] == "met" and w["after"]["score"] is not None

def test_lineage(bd):
    d, r, db = bd; L = F.lineage("M01", r, db)
    assert L["sql_result"] == 69.6 and L["version"] == "v1.0" and L["formula"] and L["owner"] and L["freshness"]["data_as_of"]
    assert F.lineage("M11", r, db)["sql_result"] == 17.5 and F.lineage("M10", r, db)["sql_result"] == 4.3
    assert F.lineage("M19", r, db)["sql"] is None and F.lineage("M99", r, db) is None

def test_reconcile_sample(bd):
    d, r, _ = bd
    x = F.reconcile(read(os.path.join(ROOT, "app", "data", "samples", "vendor_invoice_sample.csv")), d, r)
    st = {row["team"]: row for row in x["rows"]}
    assert st["TEAM-A1"]["status"] == "ok"
    assert st["TEAM-A2"]["status"] == "mismatch" and any("overbilling" in f for f in st["TEAM-A2"]["flags"])
    assert st["TEAM-X9"]["status"] == "mismatch" and "Team not in our seat roster" in st["TEAM-X9"]["flags"]
    assert st["TEAM-C2"]["flags"] == ["Team in roster but not on the invoice"]
    assert x["totals"]["billed"] == 32 and x["totals"]["mismatches"] == 2

def test_reconcile_rejects_bad_invoice(bd):
    d, r, _ = bd
    with pytest.raises(P.ValidationError): F.reconcile("team_id,seats\nA,1\n", d, r)
    with pytest.raises(P.ValidationError): F.reconcile("invoice_id,team_id,billed_seats\nI,TEAM-A1,lots\n", d, r)
