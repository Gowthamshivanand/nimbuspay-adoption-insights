"""Cost and scale calculator: arithmetic, sources, API."""
import pytest
from fastapi.testclient import TestClient
from app.server import app
from app import costcalc as CC

c = TestClient(app)

def test_defaults_local_cpu():
    r = CC.calculate()
    assert r["queries_per_day"] == 1000 and r["llm_queries_per_day"] == 700
    assert r["model_instances"] == 2 and r["monthly_cost_usd"] == round(0.08925 * 730 + 2 * 0.357 * 730, 2)
    assert r["p95_latency_s"] == 2.5 and r["p95_basis"] == "assumption"

def test_hosted_token_math():
    r = CC.calculate(model="gpt-4o-mini")
    assert r["token_cost_usd"] == round(700 * 30 * (550 * 0.15 + 10 * 0.60) / 1e6, 2) and r["model_instances"] == 0
    assert r["cost_per_1000_llm_calls_tokens_usd"] == 0.0885

def test_scale_adds_instances_and_rules_only_is_fast():
    big = CC.calculate(users=50000, queries_per_user_day=10)
    assert big["model_instances"] > 2
    rules = CC.calculate(rules_share=1.0)
    assert rules["p95_latency_s"] < 0.01 and rules["model_instances"] == 0

def test_validation():
    with pytest.raises(CC.CalcError): CC.calculate(model="nope")
    with pytest.raises(CC.CalcError): CC.calculate(rules_share=1.5)

def test_every_model_and_source_is_cited():
    for m in CC.MODELS.values():
        assert (m.get("price_src") or m.get("host_src")) in CC.SOURCES and m["p95_basis"] == "assumption"
    assert all(s["checked"] == "2026-10-18" and s["url"] for s in CC.SOURCES.values())

def test_cost_api():
    meta = c.get("/api/cost").json()
    assert meta["default_result"]["monthly_cost_usd"] == CC.calculate()["monthly_cost_usd"] and len(meta["assumptions"]) >= 10
    r = c.post("/api/cost", json={"model": "gpt-6-luna", "users": 400}).json()
    assert r["queries_per_day"] == 2000 and r["inputs"]["model"] == "gpt-6-luna"
    assert c.post("/api/cost", json={"model": "bogus"}).status_code == 422
    assert "Cost and scale" in c.get("/static/app.js").text
