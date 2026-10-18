"""Deny by default: a missing, empty or unknown role gets the least-privileged persona (no data), in the agent and the API."""
import pytest
from fastapi.testclient import TestClient
from app import agent as A
from app.server import app

c = TestClient(app)

@pytest.fixture(scope="module")
def agent(workbook_state):
    return A.Agent(*workbook_state)

@pytest.mark.parametrize("p", [None, "", "superadmin", "Executive", "EXECUTIVE", "admin", "executive ", 42])
def test_unknown_role_resolves_to_least_privilege(p):
    assert A.resolve_persona(p) == "guest" and A.PERSONAS["guest"]["regions"] == []

def test_known_roles_unchanged():
    for k in ("executive", "regional_lead", "platform_engineer", "fraud_ops_lead", "finance"):
        assert A.resolve_persona(k) == k

@pytest.mark.parametrize("q", ["What is licence utilisation this month?", "Show the licence funnel", "What renewal outcome do you recommend?",
                               "Which connector has the highest failure rate this week?", "Is the KYC agent working?", "Which team uses it least?"])
def test_unknown_role_gets_no_data(agent, q):
    for p in (None, "superadmin"):
        r = agent.ask(q, p)
        assert r["type"] == "refuse" and r["intent"] == "no_role" and r["safe_alternative"] and not r["sql"] and not r["rows"]
        assert "%" not in r["text"]

def test_default_argument_is_least_privilege(agent):
    assert agent.ask("What is licence utilisation this month?")["intent"] == "no_role"

def test_unknown_role_can_still_read_definitions_and_guards_still_explain(agent):
    assert agent.ask("How is licence utilisation defined?", "nobody")["type"] == "answer"
    assert agent.ask("List the card numbers in last week's fraud cases", "nobody")["intent"] == "pii"

def test_scope_sql_denies_empty_scope():
    assert A._scope_sql([]) == (" AND 1=0", ())
    assert A._scope_sql(None) == ("", ())

def test_api_missing_and_unknown_persona_deny_by_default():
    c.post("/api/load/baseline")
    for body in ({"question": "What is licence utilisation this month?"},
                 {"question": "What is licence utilisation this month?", "persona": "superadmin"},
                 {"question": "What is licence utilisation this month?", "persona": None}):
        r = c.post("/api/ask", json=body).json()
        assert r["type"] == "refuse" and r["intent"] == "no_role" and r["persona"] == "guest"
    a = c.get("/api/audit").json()[0]
    assert a["persona"].startswith("guest (requested:")
    ok = c.post("/api/ask", json={"question": "What is licence utilisation this month?", "persona": "executive"}).json()
    assert ok["type"] == "answer" and "69.6%" in ok["text"]

def test_personas_endpoint_lists_least_privilege_role():
    assert "guest" in c.get("/api/personas").json()
