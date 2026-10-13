"""Screenshot every tab at 375x812 and 1280x800.

    python tools/ux/capture.py docs/ux/before

For each tab: `<tab>-fold` (what a person sees without scrolling) and `<tab>-full` (a tall viewport so the whole
tab is captured). The Today tab is also captured after one search, and Insights/History after logging a food, so
the populated states are on record. Data comes from the local mock API (layout only).
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from tools.ux.harness import ROOT, VIEWPORTS, running_app, wait_app_ready

TABS = {"today": "Today", "insights": "Insights", "profile": "Profile", "history": "History"}  # substring match on tab labels


def shot(page, out: Path, name: str, vp_name: str):
    vp = VIEWPORTS[vp_name]
    page.set_viewport_size(vp)
    page.wait_for_timeout(500)
    page.screenshot(path=str(out / f"{name}-fold-{vp_name}.png"))
    page.set_viewport_size({"width": vp["width"], "height": 3000})
    page.wait_for_timeout(700)
    page.screenshot(path=str(out / f"{name}-full-{vp_name}.png"))
    page.set_viewport_size(vp)


def open_tab(page, label):
    page.get_by_role("tab", name=label).first.click()
    page.wait_for_timeout(700)


def populated_flow(page, out, vp_name):
    """BEFORE-version flow: search a multi-ingredient food, add it, then capture the populated tabs."""
    open_tab(page, TABS["today"])
    page.get_by_placeholder("e.g. 2 cups oatmeal").fill("2 cups white rice and carrots")
    page.keyboard.press("Tab")
    page.get_by_role("button", name="Analyze Food").click()
    page.get_by_text("Nutrition Info").first.wait_for(timeout=20000)
    shot(page, out, "today-result", vp_name)
    page.get_by_role("button", name="Add to Today's Log").click()
    page.wait_for_timeout(1200)
    shot(page, out, "today-logged", vp_name)
    open_tab(page, TABS["insights"])
    shot(page, out, "insights-logged", vp_name)
    open_tab(page, TABS["history"])
    page.get_by_role("button", name="Save Today's Summary").click()
    page.wait_for_timeout(1000)
    shot(page, out, "history-saved", vp_name)


def run(out_dir):
    out = ROOT / out_dir
    out.mkdir(parents=True, exist_ok=True)
    with running_app() as url, sync_playwright() as pw:
        browser = pw.chromium.launch()
        for vp_name, vp in VIEWPORTS.items():
            ctx = browser.new_context(viewport=vp, device_scale_factor=1)
            page = ctx.new_page()
            page.goto(url)
            wait_app_ready(page)
            for key, label in TABS.items():
                open_tab(page, label)
                shot(page, out, f"{key}-empty", vp_name)
            populated_flow(page, out, vp_name)
            ctx.close()
        browser.close()
    print("saved to", out)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    run(sys.argv[1] if len(sys.argv) > 1 else "docs/ux/before")
