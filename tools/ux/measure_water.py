"""Click-to-update latency of the water control, original UI (full-page rerun) vs new UI (fragment rerun).

The original UI file is recovered from git history into _legacy_ui.py (untracked, deleted afterwards):
    git show 548d2cd:nutrition_tracker.py > _legacy_ui.py
    python -m tools.ux.measure_water
Each version: 8 taps on a fresh server; the first tap is discarded as warm-up; reports the median and max of the rest.
No external API is called by this interaction.
"""
import json
import re
import statistics
import time

from playwright.sync_api import sync_playwright

from tools.ux.harness import ROOT, VIEWPORTS, running_app, wait_app_ready
from tools.ux.measure import scroll_into_view

N = 8


def run(script, version):
    with running_app(use_mock=True, script=script) as url, sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_context(viewport=VIEWPORTS["1280"]).new_page()
        page.goto(url)
        wait_app_ready(page)
        if version == "before":
            btn = page.get_by_role("button", name=re.compile("1 glass"))
            times = []
            scroll_into_view(page, btn)
            for _ in range(N):
                before = page.locator(".mini-bar-label", has_text="glasses").first.inner_text()
                t0 = time.perf_counter()
                btn.click()
                page.wait_for_function(
                    "(old) => { const e=[...document.querySelectorAll('.mini-bar-label')].find(x=>x.innerText.includes('glasses')); return e && e.innerText!==old }",
                    arg=before, timeout=15000)
                times.append((time.perf_counter() - t0) * 1000)
            times = times[1:]
        else:
            page.get_by_text("Water", exact=True).first.click()            # open the expander
            summary = page.locator(".np-strip").first                       # shows "Water x / y ml", updates inside the fragment
            opt = page.get_by_role("button", name="+250 ml", exact=True)
            scroll_into_view(page, opt)
            times = []
            for _ in range(N):
                before = summary.inner_text()
                t0 = time.perf_counter()
                opt.click()
                page.wait_for_function(
                    "(old) => { const e=document.querySelector('.np-strip'); return e && e.innerText!==old }",
                    arg=before, timeout=15000)
                times.append((time.perf_counter() - t0) * 1000)
                page.wait_for_timeout(200)
            times = times[1:]
        b.close()
    return {"median_ms": round(statistics.median(times)), "max_ms": round(max(times)), "min_ms": round(min(times)), "n": len(times)}


if __name__ == "__main__":
    out = {"before_full_rerun": run("_legacy_ui.py", "before"), "after_fragment": run("nutrition_tracker.py", "after")}
    (ROOT / "docs/ux/metrics-water.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
