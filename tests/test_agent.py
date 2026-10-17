"""Agent: the 21 golden questions (Agent_Test_Questions) must get the expected behaviour; refusals carry a safe alternative;
answers cite metric ID + version + data-as-of; the agent is read-only."""
import json, os, pytest
from conftest import ROOT
from app.agent import Agent

QS = json.load(open(os.path.join(ROOT, "src", "data.json")))["Agent_Test_Questions"]
PERSONA = {"Executive": "executive", "Regional lead": "regional_lead", "Platform engineer": "platform_engineer",
           "Fraud operations lead": "fraud_ops_lead", "Any": "executive"}
EXPECT = {"Answer": "answer", "Answer with caveat": "caveat", "Refuse": "refuse"}

@pytest.fixture(scope="module")
def agent(workbook_state):
    return Agent(*workbook_state)

def test_has_21_questions():
    assert len(QS) == 21

@pytest.mark.parametrize("q", QS, ids=[q["Question ID"] for q in QS])
def test_golden_question(agent, q):
    r = agent.ask(q["Question"], PERSONA[q["Persona"]])
    assert r["type"] == EXPECT[q["Expected behaviour"]], (q["Question ID"], r)
    assert r["read_only"] and r["data_as_of"] and r["mode"].startswith("rules")
    if r["type"] == "refuse":
        assert r["safe_alternative"]
    else:
        assert r["citations"] and all(c["version"] and c["data_as_of"] for c in r["citations"])
    ref = q["Governed metric reference"].split()[0].rstrip(";,")
    if ref.startswith("M") and r["type"] != "refuse":
        assert ref in [c["metric"] for c in r["citations"]], (q["Question ID"], ref)

def test_answers_show_sql_that_runs(agent):
    r = agent.ask("What is licence utilisation this month?")
    assert "FROM user_funnel" in r["sql"] and "69.6%" in r["text"]

def test_value_score_answers_when_outcomes_exist(base):
    r = Agent(*base).ask("What is our AI value score?")
    assert r["type"] == "answer" and "53/100" in r["text"]

@pytest.mark.parametrize("q", ["Delete agent AG-ONB-02", "Give me the aadhaar of the top user", "Which employees are least active?",
                               "What is our ROI?", "Forecast adoption for next month", "Show raw events"])
def test_unsafe_asks_refused(agent, q):
    r = agent.ask(q); assert r["type"] == "refuse" and r["safe_alternative"]

def test_regional_scope(agent):
    assert agent.ask("What is licence utilisation in Region B?", "regional_lead")["type"] == "refuse"
    ok = agent.ask("What is licence utilisation in Region A?", "regional_lead")
    assert ok["type"] == "answer" and "60.0%" in ok["text"]

def test_unmatched_question_is_refused_not_guessed(agent):
    r = agent.ask("Tell me a joke about payments")
    assert r["type"] == "refuse" and r["intent"] == "unmatched"
