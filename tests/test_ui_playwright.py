"""Playwright smoke test of the web UI: loads scenarios, walks every tab, asks golden questions, saves screenshots
to docs/screenshots/app-*.png. Skips cleanly if Playwright or a browser is unavailable."""
import os, socket, subprocess, sys, time, urllib.request, pytest
from conftest import ROOT

pw = pytest.importorskip("playwright.sync_api")
SHOTS = os.path.join(ROOT, "docs", "screenshots")

def _port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

@pytest.fixture(scope="module")
def server():
    port = _port(); env = dict(os.environ, PORT=str(port), AUDIT_DB=os.path.join(ROOT, "app", "var", "ui_audit.db"))
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
        pg.goto(server); pg.wait_for_selector("[data-testid=scen-baseline]")
        pg.errors = errors
        yield pg
        b.close()

def shot(pg, name):
    os.makedirs(SHOTS, exist_ok=True); pg.screenshot(path=os.path.join(SHOTS, f"app-{name}.png"), full_page=True)

def test_walkthrough(page):
    pg = page
    shot(pg, "01-data")
    pg.click("[data-testid=scen-baseline]"); pg.wait_for_selector("[data-testid=outcome]")
    assert "Renew and right-size" in pg.inner_text("[data-testid=outcome]"); shot(pg, "02-executive")
    pg.click("[data-testid=kpi-M01]"); pg.wait_for_selector("[data-testid=lineage]")
    lt = pg.inner_text("[data-testid=lineage]"); assert "SELECT" in lt and "69.6" in lt; shot(pg, "11-lineage")
    pg.click("[data-testid=lin-close]"); pg.wait_for_selector("#lin", state="detached")
    pg.click("#tab-whatif"); pg.fill("[data-testid=w-seats]", "20"); pg.click("[data-testid=w-run]"); pg.wait_for_selector("[data-testid=w-result]")
    assert "Expand" in pg.inner_text("[data-testid=w-result]"); shot(pg, "12-whatif")
    pg.click("#tab-seats"); pg.wait_for_selector("[data-testid=reclaim]"); assert pg.inner_text("[data-testid=reclaimable]") == "10"
    pg.click("[data-testid=inv-sample]"); pg.wait_for_selector("[data-testid=reconcile]")
    assert "mismatch" in pg.inner_text("[data-testid=reconcile]"); shot(pg, "13-seats-bill")
    pg.click("#tab-region"); pg.wait_for_selector("text=Regional adoption"); shot(pg, "03-regional")
    pg.click("#tab-eng"); pg.wait_for_selector("text=Engineering reliability"); assert "unregistered" in pg.content(); shot(pg, "04-engineering")
    pg.click("#tab-agent"); pg.click("[data-testid=gq-1]"); pg.wait_for_selector("[data-testid=answer]"); pg.wait_for_function("!document.querySelector('[data-testid=brain]').textContent.includes('checking')"); assert "Rules engine" in pg.inner_text("[data-testid=brain]")
    pg.click("[data-testid=gq-14]"); pg.wait_for_function("document.querySelectorAll('[data-testid=answer]').length>=2")
    pg.click("[data-testid=gq-8]"); pg.wait_for_function("document.querySelectorAll('[data-testid=answer]').length>=3")
    txt = pg.inner_text("[data-testid=chat]")
    assert "69.6%" in txt and "Refused" in txt and "Safe alternative" in txt and "M01 v1.0" in txt
    pg.fill("[data-testid=ask-input]", "What renewal outcome do you recommend?"); pg.click("[data-testid=ask-btn]")
    pg.wait_for_function("document.querySelectorAll('[data-testid=answer]').length>=4"); shot(pg, "05-agent")
    pg.click("#tab-alerts"); pg.wait_for_selector("[data-testid=alerts]"); shot(pg, "06-alerts")
    pg.click("#tab-compare"); pg.wait_for_selector("[data-testid=compare]"); assert "Expand" in pg.inner_text("[data-testid=compare]"); shot(pg, "07-compare")
    pg.click("#tab-pack"); pg.wait_for_timeout(800); shot(pg, "08-boardpack")
    pg.click("#tab-audit"); pg.wait_for_selector("[data-testid=audit]"); assert "card numbers" in pg.inner_text("[data-testid=audit]"); shot(pg, "09-audit")
    pg.click("#tab-data"); pg.click("[data-testid=scen-breach]"); pg.wait_for_selector("[data-testid=score]")
    assert "RED" in pg.inner_text("[data-testid=score]"); shot(pg, "10-breach-red")
    assert not pg.errors, pg.errors
