"""Real-browser smoke test of the main flows against the mock API, and a frame-by-frame GIF of logging a food.

    python -m tools.ux.e2e_smoke
Prints PASS/FAIL per check; writes docs/ux/logging-flow.gif.
"""
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

from tools.ux.harness import ROOT, VIEWPORTS, running_app, wait_app_ready

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))


def main():
    frames = []
    with running_app() as url, sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport=VIEWPORTS["375"], is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.goto(url)
        wait_app_ready(page)
        uid_url = page.url
        check("uid is placed in the URL", "u=" in uid_url, uid_url)

        def snap(label):
            path = ROOT / f"tools/ux/_frame_{len(frames)}.png"
            page.screenshot(path=str(path))
            frames.append((path, label))

        snap("start")
        box = page.get_by_label("Food search")
        box.click()
        page.keyboard.type("2 cups white rice and carrots")
        snap("typed")
        page.keyboard.press("Enter")
        page.get_by_text("Ingredients found").first.wait_for(timeout=20000)
        page.wait_for_timeout(500)
        snap("result")
        check("multi-ingredient result split into 2 rows", page.locator(".np-table tbody tr").count() == 3)   # 2 items + total
        page.get_by_role("button", name="Add to ").first.click()
        page.get_by_text("Nothing logged yet").first.wait_for(state="detached", timeout=10000)
        page.wait_for_timeout(800)
        snap("added")
        check("entries appear in the log", page.locator(".np-entry").count() == 2)
        check("undo button offered", page.get_by_role("button", name="Undo").count() == 1)
        page.get_by_role("button", name="Undo").click()
        page.get_by_text("Nothing logged yet").first.wait_for(timeout=10000)
        try:
            page.wait_for_function("document.querySelectorAll('.np-entry').length === 0", timeout=8000)
            check("undo removes the added food", True)
        except Exception:
            check("undo removes the added food", False, "entries still present")

        # fix-the-match on the USDA path ("nothing" makes the mock CalorieNinjas return no items)
        box = page.get_by_label("Food search")
        box.fill("nothing special")
        page.keyboard.press("Enter")
        page.get_by_text("Ingredients found").first.wait_for(timeout=20000)
        exp = page.get_by_text("Pick another match").first
        exp.click()
        radios = page.get_by_role("radio")
        check("five alternative matches offered", radios.count() >= 5, str(radios.count()))
        radios.nth(2).locator("xpath=ancestor::label").click()
        page.get_by_role("button", name="Use this match").click()
        page.get_by_text("Match updated").first.wait_for(timeout=10000)
        check("choosing another match updates the item", page.get_by_text("You chose this").count() >= 1)

        # persistence: reload with the same URL keeps the data
        page.get_by_role("button", name="Add to ").first.click()
        page.wait_for_timeout(1500)
        page.reload()
        wait_app_ready(page)
        check("log survives a page refresh", page.locator(".np-entry").count() >= 1)

        # onboarding: 3 steps
        page.get_by_text("Lose weight").first.click()
        page.get_by_role("button", name="Next").click()
        page.get_by_text("About you").first.wait_for(timeout=10000)
        page.get_by_text("Female", exact=True).first.click()
        page.get_by_label("Age (years)").first.fill("30")
        page.get_by_label("Age (years)").first.press("Enter")
        page.get_by_label("Height (cm)").first.fill("170")
        page.get_by_label("Height (cm)").first.press("Enter")
        page.get_by_label("Weight (kg)").first.fill("65")
        page.get_by_label("Weight (kg)").first.press("Enter")
        page.get_by_role("combobox", name="Activity level").first.click()
        page.get_by_role("option").first.click()
        page.wait_for_timeout(600)
        page.get_by_role("button", name="Next").click()
        page.get_by_text("Your daily target").first.wait_for(timeout=10000)
        check("onboarding reaches the target step", True)
        page.get_by_role("button", name="Finish").click()
        page.wait_for_timeout(1500)
        check("goal appears in the summary after setup", "of " in page.locator(".np-strip").first.inner_text())
        b.close()

    # GIF
    imgs = []
    for path, _ in frames:
        im = Image.open(path).convert("RGB")
        im = im.resize((375, int(im.height * 375 / im.width)))
        imgs.append(im.convert("P", palette=Image.ADAPTIVE))
        path.unlink()
    out = ROOT / "docs/ux/logging-flow.gif"
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=1300, loop=0)
    print("wrote", out, f"({out.stat().st_size // 1024} KB)")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
