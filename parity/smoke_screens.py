"""Playwright smoke check of every screen (S00-S21) at desktop, tablet and mobile widths. Exit 0 = PASS.
  python parity/smoke_screens.py --base http://127.0.0.1:7861
Needs: pip install playwright && python -m playwright install chromium. Read-only, apart from loading scenarios and asking a few questions."""
import argparse, sys
from playwright.sync_api import sync_playwright

TABS = {"data": "[data-testid=scen-baseline]", "exec": "[data-testid=outcome]", "whatif": "[data-testid=w-run]", "seats": "[data-testid=reclaim]",
        "region": "text=Regional adoption", "eng": "text=Engineering reliability", "agent": "[data-testid=ask-input]", "alerts": "[data-testid=alerts]",
        "compare": "[data-testid=compare]", "pack": "[data-testid=pack-html]", "audit": "[data-testid=audit]", "cost": "[data-testid=c-monthly]",
        "models": "[data-testid=models]"}
VIEWPORTS = {"desktop": (1440, 900), "tablet": (834, 1112), "mobile": (390, 844)}


def main(base):
    fails = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for vp, (w, h) in VIEWPORTS.items():
            pg = b.new_page(viewport={"width": w, "height": h}); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: (errs.append("dialog: " + d.message), d.dismiss()))
            pg.goto(base); pg.wait_for_selector("[data-testid=scen-baseline]", timeout=15000)
            pg.click("[data-testid=scen-baseline]"); pg.wait_for_selector("[data-testid=outcome]")
            for t, sel in TABS.items():
                try:
                    pg.locator(f"#tab-{t}").scroll_into_view_if_needed(); pg.click(f"#tab-{t}"); pg.wait_for_selector(sel, timeout=15000)
                except Exception as e: fails.append(f"{vp}: tab {t}: {e.__class__.__name__}")
            try:   # states: lineage modal, agent answer + why modal, what-if result, reconcile, RED score
                pg.click("#tab-exec"); pg.click("[data-testid=kpi-M01]"); pg.wait_for_selector("[data-testid=lineage]"); pg.click("[data-testid=lin-close]")
                pg.click("#tab-agent"); pg.fill("[data-testid=ask-input]", "What is licence utilisation this month?"); pg.click("[data-testid=ask-btn]")
                pg.wait_for_selector("[data-testid=answer] >> text=69.6%"); pg.locator("[data-testid=why-btn]").last.click()
                pg.wait_for_selector("[data-testid=why-panel]"); pg.click("[data-testid=why-close]")
                pg.click("#tab-whatif"); pg.click("[data-testid=w-run]"); pg.wait_for_selector("[data-testid=w-result]")
                pg.click("#tab-seats"); pg.click("[data-testid=inv-sample]"); pg.wait_for_selector("[data-testid=reconcile]")
                pg.click("#tab-data"); pg.click("[data-testid=scen-breach]"); pg.wait_for_selector("[data-testid=score] >> text=RED")
                pg.click("#tab-data"); pg.click("[data-testid=scen-baseline]"); pg.wait_for_selector("[data-testid=outcome]")
            except Exception as e: fails.append(f"{vp}: states: {e.__class__.__name__}: {str(e)[:120]}")
            if errs: fails.append(f"{vp}: page errors: {errs[:3]}")
            pg.close()
        b.close()
    for f in fails: print("FAIL", f)
    print("smoke:", "PASS" if not fails else f"FAIL ({len(fails)})"); return 0 if not fails else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True); sys.exit(main(ap.parse_args().base.rstrip("/")))
