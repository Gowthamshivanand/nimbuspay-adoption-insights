"""Browser checks for the pitch-day UI fixes: a hostile persona string in the Audit tab is shown as text (no HTML runs),
and a failed request shows an error message instead of a frozen chat bubble. No screenshots are written.
Skips cleanly if Playwright or a browser is unavailable."""
import json, os, socket, subprocess, sys, time, urllib.request, pytest
from conftest import ROOT

pw = pytest.importorskip("playwright.sync_api")


def _port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    port = _port(); env = dict(os.environ, PORT=str(port), NP_BRAIN="rules", AUDIT_DB=str(tmp_path_factory.mktemp("a") / "audit.db"))
    p = subprocess.Popen([sys.executable, "-m", "app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try: urllib.request.urlopen(url + "/api/health"); break
        except Exception: time.sleep(0.25)
    yield url
    p.terminate(); p.wait(5)


@pytest.fixture
def page(server):
    with pw.sync_playwright() as p:
        exe = os.environ.get("CHROME_PATH") or next((x for x in ("/usr/bin/google-chrome", "/usr/bin/chromium") if os.path.exists(x)), None)
        try: b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        except Exception as e: pytest.skip(f"No browser: {e}")
        pg = b.new_page(viewport={"width": 1366, "height": 900})
        pg.dialogs = []; pg.on("dialog", lambda d: (pg.dialogs.append(d.message), d.dismiss()))
        pg.goto(server); pg.wait_for_selector("[data-testid=scen-baseline]")
        yield pg
        b.close()


def test_audit_tab_shows_a_hostile_persona_as_text(page, server):
    req = urllib.request.Request(server + "/api/ask", data=json.dumps({"question": "What is licence utilisation?",
                                 "persona": "<img src=x id=pwn onerror=alert(1)>"}).encode(), headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req).read()
    page.click("#tab-audit"); page.wait_for_selector("[data-testid=audit]")
    page.wait_for_timeout(300)
    assert page.query_selector("#pwn") is None and page.dialogs == []
    assert "<img src=x id=pwn" in page.inner_text("[data-testid=audit]")


def test_failed_request_shows_an_error_not_a_frozen_bubble(page):
    page.route("**/api/ask**", lambda route: route.fulfill(status=500, body='{"detail": "Internal Server Error"}', content_type="application/json"))
    page.click("#tab-agent"); page.fill("[data-testid=ask-input]", "What is licence utilisation this month?"); page.click("[data-testid=ask-btn]")
    page.wait_for_selector("[data-testid=answer]", timeout=5000)
    txt = page.inner_text("#chat")
    assert "didn't answer" in txt and page.query_selector("[data-testid=streaming]") is None
