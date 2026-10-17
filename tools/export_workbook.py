"""Export the synthetic tabs of NimbusPay_Supporting_Workbook_v10.xlsx to CSVs in app/data/base/.
All rows are SYNTHETIC. Run once; the CSVs are committed so the app needs no workbook.
Usage: python tools/export_workbook.py [path/to/workbook.xlsx]"""
import csv, json, os, sys
import openpyxl
WB = sys.argv[1] if len(sys.argv) > 1 else "/workspace/hobby-project/fix/NimbusPay_Supporting_Workbook_v10.xlsx"
OUT = os.path.join(os.path.dirname(__file__), "..", "app", "data", "base")
os.makedirs(OUT, exist_ok=True)
wb = openpyxl.load_workbook(WB, data_only=True)
NA = {"Not logged", "Not applicable", None}
def rows(name):
    it = wb[name].iter_rows(values_only=True); h = next(it)
    return [dict(zip(h, r)) for r in it if r[0] is not None]
def w(fn, header, data):
    with open(os.path.join(OUT, fn), "w", newline="") as f:
        c = csv.writer(f); c.writerow(header); c.writerows(data)
ev = rows("Golden_Events_Extended")
w("events.csv", ["event_id","interaction_id","run_id","event_time","ingested_at","region","team_id","user_id","event_type","agent_id","log_source","status","truth_id"],
  [[r["Event ID"], "" if r["Interaction ID"] in NA else r["Interaction ID"], "" if r["Run ID"] in NA else r["Run ID"], r["Event time (UTC)"], r["Ingested at (UTC)"],
    r["Region"], r["Team ID"], r["User ID"], r["Event type"], "" if r["Agent ID"] in NA else r["Agent ID"], r["Log source"], r["Status"],
    "" if r["Ground-truth question (test oracle)"] in NA else r["Ground-truth question (test oracle)"]] for r in ev])
se = rows("Seat_Roster_Extended")
w("seats.csv", ["team_id","region","purchased_seats","user_id","assigned","provisioned"],
  [[r["Team ID"], r["Region"], r["Purchased seats (LF1)"], r["User ID"], r["Assigned (LF2)"], r["Provisioned (LF3)"]] for r in se])
ag = rows("Agent_Registry_Extended")
w("registry.csv", ["agent_id","name","registered","build_type","log_source"],
  [[r["Agent ID"], r["Name"], r["Registered"], "" if r["Build type (registry)"] == "Missing" else r["Build type (registry)"], r["Log source signature"]] for r in ag])
exp = {str(r["Test ID"]): r["Computed value"] for r in rows("Expected_Results_Extended") if str(r["Test ID"]).startswith("XR")}
json.dump(exp, open(os.path.join(OUT, "expected_results_extended.json"), "w"), indent=1, default=str)
g = rows("Golden_Events")
w("golden_events_9.csv", ["event_id","interaction_id","run_id","event_time","ingested_at","region","team_id","user_id","event_type","agent_id","log_source","status","truth_id"],
  [[r["Event ID"], "" if (r["Grouping method"] or "").startswith("Session") or r["Interaction ID"] in NA else r["Interaction ID"],
    "" if r["Run ID"] in NA else r["Run ID"], f"2026-09-07 09:00:{int(r['Relative time'][2:-1]):02d}", f"2026-09-07 09:05:{int(r['Relative time'][2:-1]):02d}",
    "Region A", r["Team ID"], r["User ID"], r["Event type"], "" if r["Agent ID"] in NA else r["Agent ID"],
    "platform" if r["Event type"] == "login" else ("sdk" if r["Agent build type"] == "Engineer-built" else "builder_ui"), "ok", ""] for r in g])
print("exported", len(ev), "events,", len(se), "seats,", len(ag), "agents,", len(exp), "expected results")
