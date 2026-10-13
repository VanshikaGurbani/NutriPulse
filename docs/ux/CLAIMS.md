# UX claims I can defend

Only statements backed by a measurement in this repository. Each row gives the exact sentence, the value, the method and the file it came
from. Anything not listed here (usability, satisfaction, "faster", "easier") has **not** been measured and must not be claimed.

All measurements: Chromium via Playwright (Lighthouse via Google Chrome), one Windows machine, local Streamlit server, original UI at commit
`548d2cd` vs rebuilt UI, scripts in `tools/ux/`. Real APIs for logging/latency; a local mock API for the water-tap test (no network involved).

| # | Claim (exact sentence) | Value | n | Method | Source |
|---|---|---|---|---|---|
| 1 | "On a 375x812 phone viewport the search box moved from 1,179 px down the page, below the first screen, to 167 px, visible without scrolling." | y = 1179 px -> 167 px | 3 runs, identical | Playwright reads the search box position after load. | `docs/ux/metrics-before.json`, `metrics-after.json` |
| 2 | "On a 1280x800 desktop the search box moved from 786 px (below the fold) to 137 px." | 786 -> 137 px | 3 runs, identical | same | same |
| 3 | "Logging a first food on desktop takes 1 click instead of 3." | 3 -> 1 click | 3 runs, identical | Trusted click events counted in-page during a scripted flow (focus, type, submit, add); the new UI autofocuses the box and submits on Enter. | `metrics-*.json` (`interaction.1280`) |
| 4 | "On a phone it takes 2 clicks instead of 3 (tap the box, tap Add), and 2 scroll gestures instead of 3 to reach the Add button." | 3 -> 2 clicks; 3 -> 2 scrolls | 3 runs, identical | same; a scroll gesture is one wheel step of 70% of the viewport. | `metrics-*.json` (`interaction.375`) |
| 5 | "Lighthouse mobile accessibility score rose from 88 to 100." | 88 -> 100 | 3 runs each (88,88,88 / 100,100,100) | Lighthouse 12.3 accessibility category, default mobile emulation, Today tab initial state only. | `metrics-*.json` (`lighthouse`) |
| 6 | "Elements failing axe-core checks fell from 61 to 49 across the four tabs at 375 px; the same four rule types remain." | 61 -> 49 nodes; 4 -> 4 distinct rules | 1 run each | axe-core 4.10.2, tags wcag2a, wcag2aa, best-practice. The remaining violations are inside Streamlit's own widgets (see `CHANGELOG.md`). | `metrics-*.json` (`axe`) |
| 7 | "A water tap updates the screen in a median 90 ms with the new fragment-based UI versus 189 ms with a full-page rerun." | 189 ms -> 90 ms median (new max 297 ms, old max 231 ms) | 7 timed taps each | Click to visible change in the water readout; empty-log state, local mock API, same machine. | `docs/ux/metrics-water.json` (`tools/ux/measure_water.py`) |
| 8 | "The log, goals and history survive a page refresh, and one person's data is not shown to another link." | pass | 1 each | Real-browser smoke test (reload keeps entries) and headless tests (two ids). | `tools/ux/e2e_smoke.py`, `tests/test_ui.py` |
| 9 | "A phrase with several foods is split into separate ingredient rows, each with source and match badges and an editable amount, instead of one merged row." | 3 table rows (2 items + total) for "2 cups white rice and carrots" | 1 | Real-browser smoke test counts table rows. | `tools/ux/e2e_smoke.py` |

## Measured but NOT claimable as an improvement

| Measurement | Before | After | Why not |
|---|---|---|---|
| Keystrokes to log a first food | 29 | 30 | Unchanged (one more for Enter); the saving is in clicks and scrolling. |
| Cold first page load | 2,177 ms | 2,181 ms | No difference. |
| First search on a fresh server | 1,393 ms (375 px) / 1,391 ms (1280 px) | 1,363 ms / 875 ms | Single measurements; differences of this size are within noise except possibly the 1280 px one, which I cannot separate from variance with n = 1. |
| Repeat (cached) search | 175 ms | 169 ms | No meaningful difference. |

## Not measured yet

- Usability: task success, task time and System Usability Scale scores need real participants. The kit is [`usability-test.md`](usability-test.md); its tables are empty on purpose.
- Behaviour with a populated log or on slow networks and low-end phones.
- Any claim about real users' match accuracy (see the benchmark and the feedback log, which has no real-use data yet).
