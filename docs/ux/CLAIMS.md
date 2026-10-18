# UX claims I can defend

Only statements backed by a measurement in this repository. Each row gives the exact sentence, the value, the method and the file it came
from. Anything not listed here (usability, satisfaction, "faster", "easier") has **not** been measured and must not be claimed.

All measurements: Chromium via Playwright (Lighthouse via Google Chrome), one Windows machine, local Streamlit server, original UI at commit
`548d2cd` vs rebuilt UI, scripts in `tools/ux/`. Real APIs for logging/latency; a local mock API for the water-tap test (no network involved).

| # | Claim (exact sentence) | Value | n | Method | Source |
|---|---|---|---|---|---|
| 1 | "On a 375x812 phone viewport the search box moved from 1,179 px down the page, below the first screen, to 184 px, visible without scrolling." | y = 1179 px -> 184 px | 3 runs, identical | Playwright reads the search box position after load. | `docs/ux/metrics-before.json`, `metrics-after.json` |
| 2 | "On a 1280x800 desktop the search box moved from 786 px (below the fold) to 154 px." | 786 -> 154 px | 3 runs, identical | same | same |
| 3 | "On desktop the search box is focused automatically, so logging a first food takes 1 click instead of 3 once the page has loaded." | 3 -> 1 click. Focus arrived 11-944 ms after the box appeared on 10 of 10 loads (5 within 100 ms, 5 between 0.7 and 0.95 s); someone typing before it lands must click | 3 runs, identical; 10 separate loads for the focus lag | Trusted click events counted in-page during a scripted flow that waits up to 3 s for focus; the focus lag measured separately over fresh page loads. On a phone focus is deliberately off (it would pop up the keyboard). | `metrics-*.json` (`interaction.1280`), `docs/ux/metrics-focus.json` (`tools/ux/measure_focus.py`) |
| 4 | "On a phone it takes 2 clicks instead of 3 (tap the box, tap Add), and 2 scroll gestures instead of 3 to reach the Add button." | 3 -> 2 clicks; 3 -> 2 scrolls | 3 runs, identical | same; a scroll gesture is one wheel step of 70% of the viewport. | `metrics-*.json` (`interaction.375`) |
| 5 | "Lighthouse mobile accessibility score rose from 88 to 100." | 88 -> 100 | 3 runs each (88,88,88 / 100,100,100) | Lighthouse 12.3 accessibility category, default mobile emulation, Today tab initial state only. | `metrics-*.json` (`lighthouse`) |
| 6 | "Elements failing axe-core checks fell from 61 to 49 across the four tabs at 375 px; the same four rule types remain." | 61 -> 49 nodes; 4 -> 4 distinct rules | 1 run each | axe-core 4.10.2, tags wcag2a, wcag2aa, best-practice. The remaining violations are inside Streamlit's own widgets (see `CHANGELOG.md`). | `metrics-*.json` (`axe`) |
| 7 | "A water tap updates the screen about twice as fast with the fragment-based UI as with the original full-page rerun." | Median 189 -> 90 ms, 271 -> 131 ms, 271 -> 106 ms, 199 -> 85 ms in four runs (ratios 2.1x, 2.1x, 2.6x, 2.3x) | 7 timed taps per version per run, four runs | Click to visible change in the water readout; empty-log state, local mock API, same machine. Absolute times differ between runs (machine load); the ratio stayed above 2x. Only the latest run is stored. | `docs/ux/metrics-water.json` (`tools/ux/measure_water.py`) |
| 8 | "The log, goals and history survive a page refresh, and one person's data is not shown to another link." | pass | 1 each | Real-browser smoke test (reload keeps entries) and headless tests (two ids). | `tools/ux/e2e_smoke.py`, `tests/test_ui.py` |
| 9 | "A food typed without a weight ("1 banana") is no longer logged as 1 g: the app asks for the weight and keeps Add disabled until it is confirmed." | pass | 1 each | Real-browser smoke test (Add disabled, warning shown, Keep 100 g enables it) and headless tests. | `tools/ux/e2e_smoke.py`, `tests/test_ui.py` |
| 10 | "A phrase with several foods is split into separate ingredient rows, each with source and match badges and an editable amount, instead of one merged row." | 3 table rows (2 items + total) for "2 cups white rice and carrots" | 1 | Real-browser smoke test counts table rows. | `tools/ux/e2e_smoke.py` |
| 11 | "Cup and spoon amounts use the matched food's own USDA serving size when it has one, instead of assuming the food weighs the same as water." | 1 cup of cooked white rice = 174 g (water assumption: 240 g); 3 tbsp peanut butter = 48 g (water assumption: 45 g) | 7 phrases, illustrative | Real USDA data with CalorieNinjas disabled. Not an accuracy measurement: the matched food is the scorer's choice and can be wrong. | `docs/ux/amounts-check.md` (`tools/ux/check_amounts.py`) |

| 12 | "In a scripted walkthrough of three tasks, the current UI can complete all three and the original cannot complete 'find yesterday's total' from a fresh visit, because nothing survives a refresh." | current UI 3/3 runs on all tasks (T3 answer 1,203 kcal matched the expected value); original T1 3/3, T2 3/3, T3 0/3 | 3 runs per version, fresh servers, 1 phrase, scripted (not people) | Playwright on the real CalorieNinjas API; the answer on screen is compared with the stored value. Best-case steps only. | `docs/ux/task-walkthrough.json`, `docs/ux/task-walkthrough.md` |

## Measured but NOT claimable as an improvement

| Measurement | Before | After | Why not |
|---|---|---|---|
| Keystrokes to log a first food | 29 | 30 | Unchanged (one more for Enter); the saving is in clicks and scrolling. |
| Cold first page load | 2,177 ms | 2,181, 2,316 and 2,286 ms in three runs | No difference; run-to-run spread is larger than any gap. |
| First search on a fresh server | 1,393 ms (375 px) / 1,391 ms (1280 px) | 1,363 / 875 ms, 1,481 / 1,403 ms, 1,386 / 1,364 ms in three runs | Single measurements. The 875 ms from run 1 did not repeat, which is why none of these is claimed. |
| Setting a daily goal (scripted) | 1 click, 7 keystrokes (field on Today) | 3 clicks, 4 keystrokes (Profile tab); this is slower, not an improvement. See `task-walkthrough.md` |
| Repeat (cached) search | 175 ms | 169, 254 and 214 ms in three runs | No meaningful difference. |

## Not measured yet

- Usability: task success, task time and System Usability Scale scores need real participants. The kit is [`usability-test.md`](usability-test.md); its tables are empty on purpose.
- Behaviour with a populated log or on slow networks and low-end phones.
- Any claim about real users' match accuracy (see the benchmark and the feedback log, which has no real-use data yet).
