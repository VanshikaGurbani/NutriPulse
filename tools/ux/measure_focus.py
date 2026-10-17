"""How soon after the search box appears does it get keyboard focus on desktop? 10 fresh page loads, mock API (no quota).

    python -m tools.ux.measure_focus     # writes docs/ux/metrics-focus.json
"""
import json
import time

from playwright.sync_api import sync_playwright

from tools.ux.harness import ROOT, VIEWPORTS, running_app

FOCUS_JS = "document.activeElement && document.activeElement.getAttribute('aria-label') === 'Food search'"


def main(n=10):
    lags, ok = [], 0
    with running_app(use_mock=True) as url, sync_playwright() as pw:
        b = pw.chromium.launch()
        for _ in range(n):
            page = b.new_context(viewport=VIEWPORTS["1280"]).new_page()
            t0 = time.perf_counter()
            page.goto(url)
            page.wait_for_selector('input[aria-label="Food search"]', timeout=30000)
            ready = (time.perf_counter() - t0) * 1000
            try:
                page.wait_for_function(FOCUS_JS, timeout=8000)
                lags.append(round((time.perf_counter() - t0) * 1000 - ready))
                ok += 1
            except Exception:
                pass
            page.context.close()
        b.close()
    out = {"loads": n, "focused": ok, "lag_ms_after_box_visible_sorted": sorted(lags),
           "within_100ms": sum(x <= 100 for x in lags), "max_ms": max(lags) if lags else None}
    (ROOT / "docs/ux/metrics-focus.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
