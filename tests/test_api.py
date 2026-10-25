"""API tests via FastAPI TestClient."""
import io, os, pytest
from fastapi.testclient import TestClient
from conftest import BASE
from app.server import app

c = TestClient(app)

def test_health_and_ui():
    assert c.get("/api/health").json()["ok"]
    assert "Adoption Insights" in c.get("/").text and c.get("/static/app.js").status_code == 200

def test_scenarios_load_and_outcomes():
    sc = c.get("/api/scenarios").json(); assert len(sc) == 8
    for s in sc:
        st = c.post(f"/api/load/{s['key']}").json()
        assert st["renewal"]["outcome"] == s["expected_outcome"]
    assert c.post("/api/load/nope").status_code == 404

def test_ask_and_audit():
    c.post("/api/load/baseline")
    r = c.post("/api/ask", json={"question": "What is licence utilisation this month?", "persona": "executive"}).json()
    assert r["type"] == "answer" and r["citations"][0]["metric"] == "M01"
    r2 = c.post("/api/ask", json={"question": "List the card numbers in last week's fraud cases"}).json()
    assert r2["type"] == "refuse"
    a = c.get("/api/audit").json()
    assert a[0]["question"].startswith("List the card") and a[0]["type"] == "refuse"

def test_upload_roundtrip_and_validation():
    files = {k: (k + ".csv", open(os.path.join(BASE, k + ".csv"), "rb"), "text/csv") for k in ("events", "seats", "registry")}
    st = c.post("/api/upload", files=files, data={"verified_hours_week": "180", "cost_index": "0.9"}).json()
    assert st["dataset"] == "upload" and st["grouping"]["qualifying"] == 43 and st["renewal"]["outcome"] == "Renew and right-size"
    bad = {"events": ("e.csv", io.BytesIO(b"x,y\n1,2\n"), "text/csv"),
           "seats": ("s.csv", open(os.path.join(BASE, "seats.csv"), "rb"), "text/csv"),
           "registry": ("r.csv", open(os.path.join(BASE, "registry.csv"), "rb"), "text/csv")}
    resp = c.post("/api/upload", files=bad); assert resp.status_code == 422 and "missing columns" in resp.json()["detail"]

def test_compare_and_boardpack():
    cmp = c.get("/api/compare").json(); assert len(cmp) == 8 and len({x["outcome"] for x in cmp}) == 5
    c.post("/api/load/breach")
    md = c.get("/api/boardpack?format=md").text
    assert "SYNTHETIC DATA" in md and "RED" in md and "Renew with remediation conditions" in md
    assert "<table>" in c.get("/api/boardpack?format=html").text

def test_sample_download():
    r = c.get("/api/sample/healthy/events.csv"); assert r.status_code == 200 and r.text.startswith("event_id")
    assert c.get("/api/sample/healthy/secret.txt").status_code == 404

def test_feature_endpoints():
    c.post("/api/load/baseline")
    assert c.get("/api/reclaim").json()["reclaimable"] == 10
    assert c.post("/api/whatif", json={"seats": 20}).json()["after"]["outcome"] == "Expand"
    assert c.get("/api/lineage/M01").json()["sql_result"] == 69.6 and c.get("/api/lineage/M99").status_code == 404
    assert c.get("/api/reconcile/sample").json()["totals"]["mismatches"] == 2
    f = {"invoice": ("inv.csv", open(os.path.join(BASE, "..", "samples", "vendor_invoice_sample.csv"), "rb"), "text/csv")}
    assert c.post("/api/reconcile", files=f).json()["totals"]["billed"] == 32
    assert c.post("/api/reconcile", files={"invoice": ("inv.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")}).status_code == 422
    assert c.get("/api/brain").json()["kind"] == "rules"
