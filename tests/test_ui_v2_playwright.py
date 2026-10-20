"""v2 (React) UI: every screen renders with its key element and no page errors; the legacy UI is still served at /legacy
and at / with NP_UI=legacy; the build is text-only (HF Space check). No screenshots are written. Skips if no browser."""
import os, socket, subprocess, sys, time, urllib.request, pytest
from conftest import ROOT

pw = pytest.importorskip("playwright.sync_api")
TABS = {"data": "[data-testid=scen-baseline]", "exec": "[data-testid=outcome]", "whatif": "[data-testid=w-run]", "seats": "[data-testid=reclaim]",
        "region": "text=Regional adoption", "eng": "text=Engineering reliability", "agent": "[data-testid=ask-input]", "alerts": "[data-testid=alerts]",
        "compare": "[data-testid=compare]", "pack": "[data-testid=pack-html]", "audit": "[data-testid=audit]", "cost": "[data-testid=c-monthly]",
        "models": "[data-testid=models]"}


def _port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _serve(tmp, **extra):
    port = _port(); env = dict(os.environ, PORT=str(port), NP_BRAIN="rules", OLLAMA_HOST="http://127.0.0.1:9", AUDIT_DB=str(tmp / "audit.db"),
                               NP_FEEDBACK=str(tmp / "fb.jsonl"), NP_EVAL_DIR=str(tmp / "evals"), **extra)
    p = subprocess.Popen([sys.executable, "-m", "app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try: urllib.request.urlopen(url + "/api/health"); break
        except Exception: time.sleep(0.25)
    return p, url


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    p, url = _serve(tmp_path_factory.mktemp("v2")); yield url; p.terminate(); p.wait(5)


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        exe = os.environ.get("CHROME_PATH") or next((x for x in ("/usr/bin/google-chrome", "/usr/bin/chromium") if os.path.exists(x)), None)
        try: b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        except Exception as e: pytest.skip(f"No browser: {e}")
        yield b
        b.close()


def test_v2_build_is_committed_and_text_only():
    web = os.path.join(ROOT, "app", "web")
    assert os.path.isfile(os.path.join(web, "index.html")), "run: cd web && npm ci && npm run build"
    for d, _, fs in os.walk(web):
        for f in fs: assert b"\x00" not in open(os.path.join(d, f), "rb").read(), f


@pytest.mark.parametrize("w,h", [(1440, 900), (390, 844)])
def test_every_screen_renders(server, browser, w, h):
    pg = browser.new_page(viewport={"width": w, "height": h}); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(server); pg.wait_for_selector("[data-testid=scen-baseline]")
    assert pg.query_selector("#root") is not None                  # the React app, not the legacy page
    pg.click("[data-testid=scen-baseline]"); pg.wait_for_selector("[data-testid=outcome]")
    assert "Renew and right-size" in pg.inner_text("[data-testid=outcome]")
    for t, sel in TABS.items():
        pg.click(f"#tab-{t}"); pg.wait_for_selector(sel)
    pg.click("#tab-cost"); assert pg.inner_text("[data-testid=c-monthly]").startswith("$")
    pg.close(); assert not errs, errs


def test_legacy_ui_is_still_served(server, browser):
    html = urllib.request.urlopen(server + "/legacy").read().decode()
    assert html == open(os.path.join(ROOT, "app", "static", "index.html"), encoding="utf-8").read()
    pg = browser.new_page(); pg.goto(server + "/legacy"); pg.wait_for_selector("[data-testid=scen-baseline]")
    assert pg.query_selector("#root") is None; pg.close()


def test_np_ui_legacy_flag_serves_the_old_ui_at_root(tmp_path):
    p, url = _serve(tmp_path, NP_UI="legacy")
    try: assert urllib.request.urlopen(url + "/").read().decode() == open(os.path.join(ROOT, "app", "static", "index.html"), encoding="utf-8").read()
    finally: p.terminate(); p.wait(5)
