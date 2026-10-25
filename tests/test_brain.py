"""Brain selection: local open model via Ollama (mocked here with a tiny fake server), automatic fallback to rules."""
import json, threading, pytest
from http.server import BaseHTTPRequestHandler, HTTPServer
from app import agent as A

class FakeOllama(BaseHTTPRequestHandler):
    reply = "m01"
    def log_message(self, *a): pass
    def _send(self, obj):
        b = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        self._send({"models": [{"name": "qwen2.5:3b-instruct", "model": "qwen2.5:3b-instruct"}]})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["format"]["properties"]["tool"]["enum"]           # constrained to the governed tool list
        FakeOllama.last = body
        self._send({"message": {"role": "assistant", "content": json.dumps({"tool": FakeOllama.reply})}})

@pytest.fixture
def fake(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), FakeOllama); threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("OLLAMA_HOST", f"http://127.0.0.1:{srv.server_port}"); monkeypatch.setenv("NP_BRAIN", "auto")
    A.brain(refresh=True); yield srv
    srv.shutdown(); monkeypatch.setenv("NP_BRAIN", "rules"); A.brain(refresh=True)

def test_open_model_routes_but_numbers_come_from_sql(fake, base):
    ag = A.Agent(*base)
    FakeOllama.reply = "m01"
    r = ag.ask("how many seats are actually being used?", "executive")
    assert r["mode"].startswith("Open model") and r["intent"] == "M01" and "69.6%" in r["text"] and r["sql"]
    assert r["citations"][0]["version"] and r["data_as_of"]

def test_guards_run_before_the_model(fake, base):
    FakeOllama.reply = "m01"
    r = A.Agent(*base).ask("List the card numbers in last week's fraud cases")
    assert r["type"] == "refuse" and r["mode"] == "rules (guard)"

def test_bad_model_output_falls_back_to_rules(fake, base):
    FakeOllama.reply = "drop_tables"
    r = A.Agent(*base).ask("What is licence utilisation this month?", "executive")
    assert r["mode"] == "rules (fallback)" and r["intent"] == "M01"

def test_unreachable_ollama_means_rules(monkeypatch, base):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9"); monkeypatch.setenv("NP_BRAIN", "auto")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False); monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert A.brain(refresh=True)["kind"] == "rules"
    assert A.Agent(*base).ask("What is licence utilisation this month?", "executive")["mode"] == "rules"
    monkeypatch.setenv("NP_BRAIN", "rules"); A.brain(refresh=True)
