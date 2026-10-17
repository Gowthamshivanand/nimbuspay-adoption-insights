"""Pipeline must reproduce the v10 workbook's Expected_Results_Extended (XR01-XR31) and the 9-event golden set exactly."""
import json, os
from conftest import BASE, SCEN, read, run_dir
from app import pipeline as P

def f1(x): return f"{x:.1f}%"

def test_expected_results_extended(base, expected):
    r, _ = base; g, q, u, M = r["grouping"], r["quality"], r["users"], r["metrics"]
    got = {
        "XR01": q["raw_rows"], "XR02": q["duplicates"], "XR03": q["after_close"], "XR04": q["clean_events"], "XR05": q["late"], "XR06": q["logins"],
        "XR07": g["interactions"], "XR08": g["exact"], "XR09": g["approximate"], "XR10": g["qualifying"], "XR11": g["truth_questions"],
        "XR12": g["sessionisation_error"], "XR13": f"{g['inflation']:.2f}x", "XR14": u["vendor_mau_proxy"], "XR15": len(u["active"]),
        "XR16": len(u["engaged"]), "XR17": len(u["habitual"]),
        "XR18": f"{u['mau_overstatement']} users ({100 * u['mau_overstatement'] / len(u['active']):.1f}%)",
        "XR19": r["funnel"]["LF1"], "XR20": r["funnel"]["LF2"], "XR21": r["funnel"]["LF3"], "XR22": f1(M["M01"]["value"]), "XR23": f1(M["M02"]["value"]),
        "XR24": r["paid_unused"], "XR25": f1(M["M10"]["value"]), "XR26": f1(M["M11"]["value"]),
        "XR27a": f1(r["m20"]["Engineer-built"]["pct"]), "XR27b": f1(r["m20"]["Drag-and-drop"]["pct"]), "XR28": M["M16"]["value"],
        "XR29a": g["by_build_type"]["Engineer-built"], "XR29b": g["by_build_type"]["Drag-and-drop"], "XR30": g["restated_qualifying"],
    }
    for reg in r["regions"]:
        got["XR31-" + reg["region"].split()[1]] = f"{reg['assigned']} / {reg['active']} / {reg['habitual']}"
    assert set(got) == set(expected)
    for k in expected:
        assert str(got[k]) == str(expected[k]), (k, got[k], expected[k])

def test_user_lists_match_workbook(base):
    r, _ = base
    assert r["users"]["habitual"] == ["USER-101", "USER-102", "USER-106", "USER-111", "USER-121", "USER-131"]
    assert r["never_assigned"] == 8 and r["assigned_unused"] == 7

def test_golden_nine_events_become_two_interactions():
    data = P.load(read(os.path.join(BASE, "golden_events_9.csv")), read(os.path.join(BASE, "seats.csv")), read(os.path.join(BASE, "registry.csv")))
    r, _ = P.run(data)
    g = r["grouping"]
    assert r["quality"]["clean_events"] == 9 and g["interactions"] == 2 and g["exact"] == 1 and g["approximate"] == 1
    assert g["raw_events_per_interaction"] == 4.5                     # ER4: 4.5x overstatement
    assert r["users"]["active"] == ["USER-001", "USER-002"]           # ER3/ER5: login-only USER-003 is not active

def test_sql_warehouse_agrees_with_python(base):
    r, db = base
    act, asg = db.execute("SELECT SUM(active), SUM(assigned) FROM user_funnel WHERE assigned=1").fetchone()
    assert round(100 * act / asg, 1) == r["metrics"]["M01"]["value"]
    assert db.execute("SELECT COUNT(*) FROM interactions WHERE qualifying=1").fetchone()[0] == 43
    assert db.execute("SELECT COUNT(*) FROM events_clean").fetchone()[0] == 200

def test_value_score_rules(base, workbook_state):
    r, _ = base; s = r["score"]
    assert s["state"] == "ok" and s["value"] == round(sum(s["pillars"][k] * w for k, w in s["weights"].items()) / 100)
    w, _ = workbook_state
    assert w["score"]["state"] == "withheld" and w["score"]["value"] is None and w["score"]["interim_index"] is not None  # no silent imputation
    assert w["metrics"]["M17"]["value"] is None and w["metrics"]["M18"]["value"] is None

def test_eight_scenarios_cover_all_five_outcomes():
    idx = json.load(open(os.path.join(SCEN, "index.json")))
    assert len(idx) == 8
    outs = set()
    for s in idx:
        r, _ = run_dir(os.path.join(SCEN, s["key"]))
        assert r["renewal"]["outcome"] == s["expected_outcome"], s["key"]
        outs.add(r["renewal"]["outcome"])
        assert r["label"].startswith("SYNTHETIC")
    assert outs == {"Expand", "Renew and right-size", "Renegotiate", "Continue limited pilot", "Renew with remediation conditions"}

def test_critical_risk_override_turns_score_red():
    r, _ = run_dir(os.path.join(SCEN, "breach"))
    assert r["score"]["state"] == "red" and r["score"]["value"] is not None
    assert any(a["severity"] == "critical" for a in r["alerts"])

def test_missing_ids_make_counts_approximate_and_block_attribution():
    r, _ = run_dir(os.path.join(SCEN, "noids"))
    assert r["grouping"]["exact"] == 0 and r["metrics"]["M17"]["value"] is None and r["renewal"]["evidence"]["e2"] == "missing"

def test_validation_rejects_bad_files():
    import pytest
    with pytest.raises(P.ValidationError):
        P.load("event_id,foo\n1,2\n", read(os.path.join(BASE, "seats.csv")), read(os.path.join(BASE, "registry.csv")))
    bad = read(os.path.join(BASE, "events.csv")).replace(",login,", ",teleport,", 1)
    with pytest.raises(P.ValidationError):
        P.load(bad, read(os.path.join(BASE, "seats.csv")), read(os.path.join(BASE, "registry.csv")))
