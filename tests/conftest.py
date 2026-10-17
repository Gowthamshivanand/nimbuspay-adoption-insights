import json, os, sys, pytest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["NP_BRAIN"] = "rules"   # tests run against the deterministic engine
os.environ.setdefault("AUDIT_DB", os.path.join(ROOT, "app", "var", "test_audit.db"))
from app import pipeline as P

BASE = os.path.join(ROOT, "app", "data", "base")
SCEN = os.path.join(ROOT, "app", "data", "scenarios")

def read(p): return open(p, encoding="utf-8").read()

def run_dir(d, outcomes=None):
    o = outcomes if outcomes is not None else json.load(open(os.path.join(d, "outcomes.json")))
    return P.run(P.load(read(os.path.join(d, "events.csv")), read(os.path.join(d, "seats.csv")), read(os.path.join(d, "registry.csv")), o))

@pytest.fixture(scope="session")
def base():
    return run_dir(BASE, {"verified_hours_week": 180, "cost_index": 0.9})

@pytest.fixture(scope="session")
def workbook_state():
    """The workbook's own state: no verified outcome data yet (baselines/targets not set)."""
    return run_dir(BASE, {})

@pytest.fixture(scope="session")
def expected():
    return json.load(open(os.path.join(BASE, "expected_results_extended.json")))
