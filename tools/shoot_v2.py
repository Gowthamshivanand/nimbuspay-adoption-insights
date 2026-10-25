"""Screenshot every v2 screen and pop-up into screens/ (not committed). Needs a running server.
  python tools/shoot_v2.py --base http://127.0.0.1:7880 --out screens"""
import argparse, os
from playwright.sync_api import sync_playwright

TABS = [("data", "[data-testid=scen-baseline]"), ("exec", "[data-testid=outcome]"), ("whatif", "[data-testid=w-run]"), ("seats", "[data-testid=reclaim]"),
        ("region", "text=Regional adoption"), ("eng", "text=Engineering reliability"), ("agent", "[data-testid=ask-input]"), ("alerts", "[data-testid=alerts]"),
        ("compare", "[data-testid=compare]"), ("pack", "[data-testid=pack-html]"), ("audit", "[data-testid=audit]"), ("cost", "[data-testid=c-monthly]"), ("models", "[data-testid=models]")]


def main(base, out):
    os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1440, "height": 900}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        def shot(n, full=True, top=True):   # let the 180 ms tab fade finish (wait 300 ms) and capture from the top
            if top: pg.evaluate("window.scrollTo(0, 0)")
            pg.wait_for_timeout(300); pg.screenshot(path=os.path.join(out, n + ".png"), full_page=full)
        pg.goto(base); pg.wait_for_selector("[data-testid=scen-baseline]"); shot("00-data")
        pg.click("[data-testid=scen-baseline]"); pg.wait_for_selector("[data-testid=outcome]")
        for i, (t, sel) in enumerate(TABS, 1):
            pg.click(f"#tab-{t}"); pg.wait_for_selector(sel); pg.wait_for_timeout(700 if t == "pack" else 250)
            if t == "whatif": pg.fill("[data-testid=w-seats]", "20"); pg.click("[data-testid=w-run]"); pg.wait_for_selector("[data-testid=w-result]")
            if t == "seats": pg.click("[data-testid=inv-sample]"); pg.wait_for_selector("[data-testid=reconcile]")
            if t == "agent":
                pg.click("[data-testid=gq-1]"); pg.wait_for_selector("[data-testid=answer]")
                pg.fill("[data-testid=ask-input]", "and Region B?"); pg.click("[data-testid=ask-btn]"); pg.wait_for_function("document.querySelectorAll('[data-testid=answer]').length>=2")
                pg.click("[data-testid=gq-14]"); pg.wait_for_function("document.querySelectorAll('[data-testid=answer]').length>=3")
            shot(f"{i:02d}-{t}")
        pg.click("#tab-exec"); pg.click("[data-testid=kpi-M01]"); pg.wait_for_selector("[data-testid=lineage]"); shot("14-lineage-modal", False, top=False)
        pg.click("[data-testid=lin-close]")
        pg.click("#tab-agent"); pg.locator("[data-testid=why-btn]").first.click(); pg.wait_for_selector("[data-testid=why-panel]"); shot("15-why-modal", False, top=False)
        pg.click("[data-testid=why-close]")
        pg.click("#tab-data"); pg.click("[data-testid=scen-breach]"); pg.wait_for_selector("[data-testid=score] >> text=RED"); shot("16-breach-red")
        pg.click("#tab-data"); pg.click("[data-testid=scen-baseline]"); pg.wait_for_selector("[data-testid=outcome]")
        for n, (w, h) in {"17-mobile-exec": (390, 844), "18-tablet-agent": (834, 1112)}.items():
            m = b.new_page(viewport={"width": w, "height": h}); m.goto(base); m.wait_for_selector("[data-testid=scen-baseline]")
            m.click("#tab-exec" if "exec" in n else "#tab-agent"); m.wait_for_timeout(500); m.screenshot(path=os.path.join(out, n + ".png"), full_page=False); m.close()
        pg.goto(base + "/legacy"); pg.wait_for_selector("[data-testid=scen-baseline]"); shot("19-legacy-fallback", False)
        b.close()
    print("page errors:", errs or "none")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True); ap.add_argument("--out", default="screens"); a = ap.parse_args(); main(a.base.rstrip("/"), a.out)
