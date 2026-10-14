"""Measures the UI: interaction cost to log a first food, load/search latency, axe violations, Lighthouse.

    python -m tools.ux.measure before     # writes docs/ux/metrics-before.json
    python -m tools.ux.measure after      # writes docs/ux/metrics-after.json

Interaction cost and latency use the REAL APIs (keys from .env); the mock server is not used here.
Interaction counting: trusted clicks and keydowns are counted inside the page; scroll gestures are the mouse-wheel
steps the script needs to bring a target into view (one wheel step = 70% of the viewport height).

Phone profile: 375x812 Chromium with a mobile user agent and touch. Desktop numbers use 1280x800.
"""
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from tools.ux.harness import ROOT, VIEWPORTS, running_app, wait_app_ready

QUERY = "2 cups white rice and carrots"
COUNTER_JS = """
window.__m = {clicks: 0, keys: 0};
document.addEventListener('click', e => { if (e.isTrusted) window.__m.clicks++; }, true);
document.addEventListener('keydown', e => { if (e.isTrusted) window.__m.keys++; }, true);
"""
AXE_JS = ROOT / "tools/ux/node_modules/axe-core/axe.min.js"
LIGHTHOUSE = ROOT / "tools/ux/node_modules/lighthouse/cli/index.js"


def in_view(page, locator, margin=24):
    box = locator.bounding_box()
    vh = page.viewport_size["height"]
    return bool(box) and box["y"] >= 0 and box["y"] + min(box["height"], 40) <= vh - margin


def scroll_into_view(page, locator, max_steps=25):
    """Scroll like a person (wheel gestures) until `locator` is visible; returns the gesture count."""
    vw, vh = page.viewport_size["width"], page.viewport_size["height"]
    gestures = 0
    while not in_view(page, locator) and gestures < max_steps:
        page.mouse.move(vw / 2, vh / 2)
        page.mouse.wheel(0, vh * 0.7)
        gestures += 1
        page.wait_for_timeout(150)
    return gestures


def counters(page):
    return page.evaluate("window.__m")


# ── version-specific logging flows ───────────────────────────────────────────

FLOWS = {}


def flow(name):
    def deco(fn):
        FLOWS[name] = fn
        return fn
    return deco


@flow("before")
def before_flow(page):
    """Log a first food in the ORIGINAL UI: find search, type, click Analyze, scroll to Add, click Add."""
    box = page.get_by_placeholder("e.g. 2 cups oatmeal")
    search_in_first_screen = in_view(page, box)
    search_y = box.bounding_box()["y"]
    gestures = scroll_into_view(page, box)
    box.click()
    page.keyboard.type(QUERY)
    t0 = time.perf_counter()
    page.get_by_role("button", name="Analyze Food").click()
    page.get_by_text("Nutrition Info").first.wait_for(timeout=30000)
    search_ms = (time.perf_counter() - t0) * 1000
    add = page.get_by_role("button", name="Add to Today's Log")
    gestures += scroll_into_view(page, add)
    add.click()
    page.get_by_text("Added").first.wait_for(timeout=10000)
    return {"search_in_first_screen": search_in_first_screen, "search_box_y_px": round(search_y),
            "scroll_gestures": gestures, "search_ms_cold": round(search_ms)}


@flow("after")
def after_flow(page):
    """Log a first food in the NEW UI: (focus the box if autofocus did not), type, press Enter, scroll to Add, click Add."""
    box = page.get_by_label("Food search")
    search_in_first_screen = in_view(page, box)
    search_y = box.bounding_box()["y"]
    gestures = scroll_into_view(page, box)
    focus_js = "document.activeElement && document.activeElement.getAttribute('aria-label') === 'Food search'"
    t_focus = time.perf_counter()
    try:                                                # a person glances at the page for up to ~3 s before reaching for the box
        page.wait_for_function(focus_js, timeout=3000)
    except Exception:
        pass
    focused = page.evaluate(focus_js)
    focus_wait_ms = round((time.perf_counter() - t_focus) * 1000)
    if not focused:
        box.click()
    page.keyboard.type(QUERY)
    t0 = time.perf_counter()
    page.keyboard.press("Enter")
    page.get_by_text("Ingredients found").first.wait_for(timeout=30000)
    search_ms = (time.perf_counter() - t0) * 1000
    add = page.get_by_role("button", name="Add to ").first
    gestures += scroll_into_view(page, add)
    add.click()
    page.get_by_text("Nothing logged yet").first.wait_for(state="detached", timeout=10000)
    return {"search_in_first_screen": search_in_first_screen, "search_box_y_px": round(search_y), "autofocused": bool(focused), "focus_wait_ms": focus_wait_ms,
            "scroll_gestures": gestures, "search_ms_cold": round(search_ms)}


def repeat_search_after(page):
    box = page.get_by_label("Food search")
    scroll_into_view(page, box)
    box.fill(QUERY)
    t0 = time.perf_counter()
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    page.get_by_text("Ingredients found").first.wait_for(timeout=30000)
    return round((time.perf_counter() - t0) * 1000)


def repeat_search_before(page):
    box = page.get_by_placeholder("e.g. 2 cups oatmeal")
    scroll_into_view(page, box)
    box.fill(QUERY)
    page.keyboard.press("Tab")
    t0 = time.perf_counter()
    page.get_by_role("button", name="Analyze Food").click()
    page.wait_for_timeout(100)
    page.get_by_text("Nutrition Info").first.wait_for(timeout=30000)
    return round((time.perf_counter() - t0) * 1000)


REPEAT = {"before": repeat_search_before, "after": repeat_search_after}


def measure_interaction(browser, url, version, vp_name):
    vp = VIEWPORTS[vp_name]
    mobile = vp_name == "375"
    ctx = browser.new_context(viewport=vp, is_mobile=mobile, has_touch=mobile,
                              user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36" if mobile else None)
    ctx.add_init_script(COUNTER_JS)
    page = ctx.new_page()
    t0 = time.perf_counter()
    page.goto(url)
    wait_app_ready(page)
    load_ms = (time.perf_counter() - t0) * 1000
    out = FLOWS[version](page)
    c = counters(page)
    out.update(clicks=c["clicks"], keystrokes=c["keys"], viewport=vp_name)
    out["first_load_ms"] = round(load_ms)
    ctx.close()
    return out


def measure_latency(browser, url, version):
    """Cold = first load / first search of a fresh server; warm = second load / repeated identical search."""
    ctx = browser.new_context(viewport=VIEWPORTS["375"])
    ctx.add_init_script(COUNTER_JS)
    page = ctx.new_page()
    t0 = time.perf_counter()
    page.goto(url)
    wait_app_ready(page)
    cold_load = (time.perf_counter() - t0) * 1000
    page.reload()
    t0 = time.perf_counter()
    wait_app_ready(page)
    warm_load = (time.perf_counter() - t0) * 1000
    FLOWS[version](page)                       # first search of this query on this server (cold lookup cache)
    warm_search = REPEAT[version](page)        # identical search again (served by st.cache_data)
    ctx.close()
    return {"load_cold_ms": round(cold_load), "load_warm_ms": round(warm_load), "repeat_search_ms": warm_search}


def run_axe(browser, url, tab_labels):
    ctx = browser.new_context(viewport=VIEWPORTS["375"])
    page = ctx.new_page()
    page.goto(url)
    wait_app_ready(page)
    results = {}
    for label in tab_labels:
        page.get_by_role("tab", name=label).first.click()
        page.wait_for_timeout(900)
        page.add_script_tag(path=str(AXE_JS))
        r = page.evaluate("""async () => { const r = await axe.run(document, {runOnly: ['wcag2a','wcag2aa','best-practice']});
            return r.violations.map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help})); }""")
        results[label] = r
    ctx.close()
    all_v = [v for vs in results.values() for v in vs]
    by_impact = {}
    for v in all_v:
        by_impact[v["impact"]] = by_impact.get(v["impact"], 0) + 1
    return {"per_tab": results, "violation_rules_total": len(all_v), "violating_nodes_total": sum(v["nodes"] for v in all_v),
            "rules_by_impact": by_impact}


def run_lighthouse(url, runs=3, port=9333):
    """Lighthouse (mobile preset, accessibility only) against a Chromium we launch ourselves on a debug port,
    with the system Google Chrome (Playwright's bundled Chromium cannot start standalone on this machine)."""
    chrome = Path(os.environ.get("CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe"))
    scores = []
    for i in range(runs):
        profile = ROOT / f"tools/ux/_chrome_profile_{i}"
        proc = subprocess.Popen([str(chrome), "--headless=new", "--no-sandbox", f"--remote-debugging-port={port}",
                                 f"--user-data-dir={profile}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(3)
            out = ROOT / f"tools/ux/_lh_{i}.json"
            subprocess.run(["node", str(LIGHTHOUSE), url, f"--port={port}", "--only-categories=accessibility", "--output=json",
                            f"--output-path={out}", "--quiet"], check=True, capture_output=True, timeout=240)
            data = json.loads(out.read_text(encoding="utf-8"))
            out.unlink()
            scores.append(round(data["categories"]["accessibility"]["score"] * 100))
        finally:
            proc.terminate()
            time.sleep(1)
            shutil.rmtree(profile, ignore_errors=True)
    return {"scores": scores, "median": statistics.median(scores), "preset": "lighthouse default (mobile emulation)"}


def main(version):
    tabs = {"before": ["Today", "Insights", "Profile", "History"], "after": ["Today", "Insights", "Profile", "History"]}[version]
    result = {"version": version, "date": time.strftime("%Y-%m-%d %H:%M"), "interaction": {}, "latency": {}, "axe": {}, "lighthouse": {}}
    for vp in ("375", "1280"):
        with running_app(use_mock=False) as url, sync_playwright() as pw:
            browser = pw.chromium.launch()
            result["interaction"][vp] = [measure_interaction(browser, url, version, vp) for _ in range(3)]
            browser.close()
    with running_app(use_mock=False) as url, sync_playwright() as pw:
        browser = pw.chromium.launch()
        result["latency"] = measure_latency(browser, url, version)
        result["axe"] = run_axe(browser, url, tabs)
        browser.close()
        result["lighthouse"] = run_lighthouse(url)
    path = ROOT / f"docs/ux/metrics-{version}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "axe"}, indent=1)[:3000])
    print("axe:", result["axe"]["violation_rules_total"], "rules,", result["axe"]["violating_nodes_total"], "nodes", result["axe"]["rules_by_impact"])


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main(sys.argv[1])
