"""Scripted walkthrough of the three usability-test tasks (see docs/ux/usability-test.md), old UI vs new UI, real APIs.

THIS IS NOT A USABILITY TEST. A script knows exactly where to click, so these are best-case step counts and times (lower bounds),
and there are no participants, no SUS and no judgement of how easy anything feels. What it does show, objectively: whether each task
CAN be completed in each version, the minimum number of clicks/keystrokes it takes, and whether the answer on screen is correct.

    git show 548d2cd:nutrition_tracker.py > _legacy_ui.py     # the original UI, untracked and deleted afterwards
    python -m tools.ux.task_walkthrough                         # writes docs/ux/task-walkthrough.json
Tasks:  T1 log "2 slices of toast and a banana";  T2 set a 1,800 kcal daily goal;  T3 read yesterday's calorie total.
"""
import datetime
import json
import os
import tempfile
import time

from playwright.sync_api import sync_playwright

from tools.ux.harness import ROOT, VIEWPORTS, running_app, wait_app_ready

QUERY = "2 slices of toast and a banana"
COUNTER_JS = """
window.__m = {clicks: 0, keys: 0};
document.addEventListener('click', e => { if (e.isTrusted) window.__m.clicks++; }, true);
document.addEventListener('keydown', e => { if (e.isTrusted) window.__m.keys++; }, true);
"""


def snapshot(page):
    return page.evaluate("window.__m")


def timed(page, fn):
    """Run one task; return {ok, clicks, keystrokes, seconds, note}."""
    before, t0 = snapshot(page), time.perf_counter()
    try:
        ok, note = fn()
    except Exception as e:                                   # a task that cannot be done in the UI is a result, not a crash
        ok, note = False, f"could not complete: {type(e).__name__}: {str(e).splitlines()[0][:110]}"
    after = snapshot(page)
    reloaded = after["clicks"] < before["clicks"]            # a page reload resets the in-page counters: the step counts are unknown then
    return {"completed": bool(ok), "clicks": None if reloaded else after["clicks"] - before["clicks"],
            "keystrokes": None if reloaded else after["keys"] - before["keys"],
            "seconds": round(time.perf_counter() - t0, 1), "note": note}


def expected_yesterday():
    """What the sample week should show for yesterday, computed with the store code in a throwaway database."""
    from nutripulse.store import Store
    old = os.environ.get("NUTRIPULSE_STATE_DB")
    os.environ["NUTRIPULSE_STATE_DB"] = os.path.join(tempfile.mkdtemp(), "expected.sqlite")
    try:
        today = datetime.date.today()
        s = Store("expected")
        s.load_sample_days(today.isoformat(), 7)
        row = s.history_for_day((today - datetime.timedelta(days=1)).isoformat())
        label = (today - datetime.timedelta(days=1)).strftime("%a %d %b").replace(" 0", " ")
        return label, round(row["kcal"])
    finally:
        if old is None:
            os.environ.pop("NUTRIPULSE_STATE_DB", None)
        else:
            os.environ["NUTRIPULSE_STATE_DB"] = old


# ── new UI ───────────────────────────────────────────────────────────────────

def new_ui(browser, url):
    ctx = browser.new_context(viewport=VIEWPORTS["1280"])
    ctx.add_init_script(COUNTER_JS)
    page = ctx.new_page()
    page.goto(url)
    wait_app_ready(page)
    out = {}

    def t1():
        page.get_by_label("Food search").click()
        page.keyboard.type(QUERY)
        page.keyboard.press("Enter")
        page.get_by_text("Ingredients found").first.wait_for(timeout=30000)
        items = page.locator(".np-table tbody tr").count() - 1          # minus the total row
        page.get_by_role("button", name="Add to ").first.click()
        page.wait_for_function("document.querySelectorAll('.np-entry').length > 0", timeout=10000)
        logged = page.locator(".np-entry").count()
        return logged >= 2, f"{items} ingredient rows found, {logged} entries logged"

    def t2():
        page.get_by_role("tab", name="Profile").first.click()
        page.get_by_label("Calorie goal (kcal)").click()
        page.keyboard.type("1800")
        page.get_by_role("button", name="Save goals").click()
        page.wait_for_function("document.querySelector('.np-strip') && document.querySelector('.np-strip').textContent.includes('1,800')", timeout=10000)
        return True, "summary shows the 1,800 kcal goal"

    out["T1 log a meal"] = timed(page, t1)
    out["T2 set a goal"] = timed(page, t2)

    # setup (not timed): a week of sample data so that "yesterday" exists
    page.get_by_role("tab", name="Today").first.click()
    page.get_by_role("tab", name="Profile").first.click()
    page.get_by_role("button", name="Load a sample week").first.click()
    page.wait_for_timeout(2500)
    label, exp_kcal = expected_yesterday()

    def t3():
        page.get_by_role("tab", name="History").first.click()
        page.wait_for_selector(".np-table", timeout=10000)
        row = page.locator(".np-table tbody tr", has_text=label).first
        cells = [c.strip() for c in row.locator("th,td").all_text_contents()]
        shown = int(cells[1].replace(",", ""))
        return shown == exp_kcal, f"History row {label!r} shows {shown} kcal, expected {exp_kcal}"

    out["T3 find yesterday's total"] = timed(page, t3)
    ctx.close()
    return out


# ── old UI ───────────────────────────────────────────────────────────────────

def old_ui(browser, url):
    ctx = browser.new_context(viewport=VIEWPORTS["1280"])
    ctx.add_init_script(COUNTER_JS)
    page = ctx.new_page()
    page.goto(url)
    wait_app_ready(page)
    out = {}

    def t1():
        box = page.get_by_placeholder("e.g. 2 cups oatmeal")
        box.scroll_into_view_if_needed()
        box.click()
        page.keyboard.type(QUERY)
        page.get_by_role("button", name="Analyze Food").click()
        page.get_by_text("Nutrition Info").first.wait_for(timeout=30000)
        add = page.get_by_role("button", name="Add to Today's Log")
        add.scroll_into_view_if_needed()
        add.click()
        page.get_by_text("Added").first.wait_for(timeout=10000)
        return True, "logged as ONE merged row (the old UI cannot show ingredients separately)"

    def t2():
        goal = page.locator("input[type=number]").first                    # the calorie-goal field on the Today tab
        goal.click()
        page.keyboard.press("Control+a")
        page.keyboard.type("1800")
        page.keyboard.press("Enter")
        page.wait_for_function("document.body.innerText.includes('/ 1800 kcal')", timeout=10000)
        return True, "goal changed from the 2000 default"

    out["T1 log a meal"] = timed(page, t1)
    out["T2 set a goal"] = timed(page, t2)

    def t3():
        page.reload()
        wait_app_ready(page)
        page.get_by_role("tab", name="History").first.click()
        page.wait_for_timeout(800)
        text = page.inner_text("body")
        if "No history saved yet" in text:
            return False, "after a page refresh the History tab is empty: nothing from earlier days survives (state lived only in the browser session)"
        return False, "unexpected history content"

    out["T3 find yesterday's total"] = timed(page, t3)
    ctx.close()
    return out


RUNS = 3


def main():
    legacy = ROOT / "_legacy_ui.py"
    runs = {"new_ui": [], "old_ui": []}
    for _ in range(RUNS):                                      # a fresh server each time, so no run benefits from another's lookup cache
        with running_app(use_mock=False) as url, sync_playwright() as pw:
            b = pw.chromium.launch()
            runs["new_ui"].append(new_ui(b, url))
            b.close()
        if legacy.exists():
            with running_app(use_mock=False, script="_legacy_ui.py") as url, sync_playwright() as pw:
                b = pw.chromium.launch()
                runs["old_ui"].append(old_ui(b, url))
                b.close()
    results = {"note": ("Scripted walkthrough, NOT a usability test: best-case steps and times, " + str(RUNS) + " runs per version on fresh servers, one machine, "
                        "real CalorieNinjas data, 1280x800 desktop. No participants, no SUS."),
               "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "runs": runs, "summary": {}}
    for ver, rs in runs.items():
        for task in (rs[0] if rs else {}):
            col = [r[task] for r in rs]
            results["summary"].setdefault(ver, {})[task] = {
                "completed": f"{sum(c['completed'] for c in col)}/{len(col)}",
                "clicks": sorted({c["clicks"] for c in col}, key=str), "keystrokes": sorted({c["keystrokes"] for c in col}, key=str),
                "median_seconds": sorted(c["seconds"] for c in col)[len(col) // 2], "note": col[0]["note"]}
    (ROOT / "docs/ux/task-walkthrough.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    for ver in ("old_ui", "new_ui"):
        for task, r in results["summary"].get(ver, {}).items():
            print(f"{ver:7} {task:26} completed={r['completed']} clicks={r['clicks']} keys={r['keystrokes']} median={r['median_seconds']}s | {r['note']}")


if __name__ == "__main__":
    main()
