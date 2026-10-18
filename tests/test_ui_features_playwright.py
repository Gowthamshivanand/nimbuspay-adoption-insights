"""Browser walkthrough of the new agent features: role switch, streaming with brain + latency, follow-up, why-this-number,
clarifying question, thumbs feedback and the Models comparison screen. Saves docs/screenshots/app-14..20. Skips if no browser."""
import json, os, socket, subprocess, sys, tempfile, time, urllib.request, pytest
from conftest import ROOT

pw = pytest.importorskip("playwright.sync_api")
SHOTS = os.path.join(ROOT, "docs", "screenshots")
TMP = tempfile.mkdtemp(prefix="np-ui-")


def _port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def server():
    port = _port()
    env = dict(os.environ, PORT=str(port), AUDIT_DB=os.path.join(TMP, "audit.db"), NP_FEEDBACK=os.path.join(TMP, "fb", "feedback.jsonl"),
               NP_EVAL_DIR=os.path.join(TMP, "evals"), NP_STREAM_DELAY_MS="70", OLLAMA_HOST="http://127.0.0.1:9", NP_BRAIN="rules")
    p = subprocess.Popen([sys.executable, "-m", "app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try: urllib.request.urlopen(url + "/api/health"); break
        except Exception: time.sleep(0.25)
    yield url
    p.terminate(); p.wait(5)


@pytest.fixture(scope="module")
def page(server):
    with pw.sync_playwright() as p:
        exe = os.environ.get("CHROME_PATH") or next((x for x in ("/usr/bin/google-chrome", "/usr/bin/chromium") if os.path.exists(x)), None)
        try:
            b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        except Exception as e:
            pytest.skip(f"No browser: {e}")
        pg = b.new_page(viewport={"width": 1366, "height": 900})
        errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(server); pg.wait_for_selector("[data-testid=scen-baseline]"); pg.errors = errors
        yield pg
        b.close()


def shot(pg, name, full=False):
    os.makedirs(SHOTS, exist_ok=True); pg.screenshot(path=os.path.join(SHOTS, f"app-{name}.png"), full_page=full)


def n_answers(pg, n):
    pg.wait_for_function(f"document.querySelectorAll('[data-testid=answer]').length>={n}")


def last(pg, sel):
    return pg.locator(sel).last


def test_agent_features(page):
    pg = page
    pg.click("[data-testid=scen-baseline]"); pg.wait_for_selector("[data-testid=outcome]")
    pg.click("[data-testid=role-manager]"); pg.click("#tab-agent")
    assert "Manager" in pg.inner_text("[data-testid=role-now]")
    # streaming with brain + latency
    pg.fill("[data-testid=ask-input]", "What is licence utilisation this month?"); pg.click("[data-testid=ask-btn]")
    pg.wait_for_function("(document.querySelector('#stream-text')||{textContent:''}).textContent.length>25")
    pg.locator("#chat").scroll_into_view_if_needed(); shot(pg, "14-streaming")
    n_answers(pg, 1)
    a = last(pg, "[data-testid=answer]").inner_text()
    assert "69.6%" in a and "Rules engine" in a and " ms" in a and "confidence" in a
    # follow-up
    pg.fill("[data-testid=ask-input]", "and Region B?"); pg.click("[data-testid=ask-btn]"); n_answers(pg, 2)
    t = last(pg, "[data-testid=answer]").inner_text()
    assert "Follow-up, read as" in t and "Region B is 75.0%" in t; shot(pg, "15-followup")
    # why this number
    last(pg, "[data-testid=why-btn]").click(); pg.wait_for_selector("[data-testid=why-panel]")
    w = pg.inner_text("[data-testid=why-panel]")
    assert "SELECT" in w and "M01" in w and pg.inner_text("[data-testid=why-rows]") == "1" and "Region B" in w; shot(pg, "16-why-this-number")
    pg.click("[data-testid=why-close]"); pg.wait_for_selector("#why", state="detached")
    # clarifying question
    pg.fill("[data-testid=ask-input]", "Is the agent saving time?"); pg.click("[data-testid=ask-btn]"); n_answers(pg, 3)
    assert "Which agent do you mean" in last(pg, "[data-testid=answer]").inner_text(); shot(pg, "17-clarify")
    last(pg, "[data-testid=opt-1]").click(); n_answers(pg, 4)
    assert "AG-FRAUD-01" in last(pg, "[data-testid=answer]").inner_text()
    # thumbs feedback
    last(pg, "[data-testid=fb-down]").click(); pg.wait_for_selector("[data-testid=fb-done]")
    rows = [json.loads(x) for x in open(os.path.join(TMP, "fb", "feedback.jsonl"))]
    assert rows[-1]["rating"] == "down" and rows[-1]["brain"] == "rules"; shot(pg, "18-feedback")
    # role switch: same question, guest denied (server-side), analyst scoped
    pg.locator("[data-testid=as-guest]").first.click(); n_answers(pg, 5)
    g = last(pg, "[data-testid=answer]").inner_text(); assert "Refused" in g and "role isn't recognised" in g
    pg.click("[data-testid=role-analyst]"); pg.wait_for_function("document.querySelector('[data-testid=role-now]').textContent.includes('Analyst')")
    pg.fill("[data-testid=ask-input]", "What is licence utilisation this month?"); pg.click("[data-testid=ask-btn]"); n_answers(pg, 6)
    assert "Region A" in last(pg, "[data-testid=answer]").inner_text()
    pg.click("[data-testid=role-guest]"); pg.fill("[data-testid=ask-input]", "What is licence utilisation this month?"); pg.click("[data-testid=ask-btn]"); n_answers(pg, 7)
    assert "role isn't recognised" in last(pg, "[data-testid=answer]").inner_text(); shot(pg, "19-role-switch")
    pg.click("[data-testid=role-manager]")
    # model comparison
    pg.click("#tab-models"); pg.wait_for_selector("[data-testid=models]")
    m = pg.inner_text("[data-testid=models]")
    assert "21/21" in pg.inner_text("[data-testid=mrow-rules]") and "not available" in pg.inner_text("[data-testid=mrow-ollama]")
    assert "not available" in pg.inner_text("[data-testid=mrow-finetuned]")
    ev = os.path.join(TMP, "saved_eval.json")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "eval_agent.py"), "--brain", "rules", "--save", ev], cwd=ROOT, check=True, capture_output=True)
    pg.set_input_files("[data-testid=m-upload]", ev); pg.click("#mupf button"); pg.wait_for_selector("[data-testid=mrow-up-0]")
    assert "uploaded file saved_eval.json" in pg.inner_text("[data-testid=mrow-up-0]"); shot(pg, "20-models", full=True)
    assert not pg.errors, pg.errors
