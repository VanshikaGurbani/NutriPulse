# NutriPulse: execution plan and progress

Branch: `benchmark-and-ux`. Small commits, app must run after every commit. Nothing is pushed.

## Blockers that need the owner (I will not fake these)

| # | Needs | Blocks |
|---|-------|--------|
| B1 | `.env` with `USDA_API_KEY` and `CALORIENINJAS_KEY` (none in the clone) | Any live API call: candidate sheets, benchmark runs, latency numbers |
| B2 | Ground-truth labels (acceptable FDC ids) for every query, filled in on the labeling sheet | Accuracy, MRR, ablation, tuning |
| B3 | Optional 2nd labeler file (~30 queries) | Cohen's kappa |
| B4 | Meal reference values with sources (meals.csv) | Meal-level MAPE |
| B5 | Real usability-test sessions (5-8 people) | SUS scores, task times |
| B6 | Approval before any run that would exceed 500 live API calls | Cache-priming run |

## Task 1: benchmark and resume-grade metrics

| Phase | Work | Status |
|-------|------|--------|
| 1 | Refactor into `nutripulse/{apis,matching,nutrition,cache}.py`, thin UI, disk/TTL cache, call counters | **done** (commits a7c6ee3, 23fe15a; verified identical to old code on 700+ inputs) |
| 2 | pytest suite (44 tests, no live calls), ruff, GitHub Actions + README badge | **done locally**; the CI run itself has not executed because nothing is pushed |
| 3 | Benchmark harness (queries, labeling sheet, label import, kappa, dev-only tuning, test-only report, ablation, meals MAPE, ops metrics, charts) | **code done + tested on synthetic data**; numbers blocked on B1/B2/B4 |
| 4 | Thumbs up/down + SQLite feedback + admin view (`?admin=1`) | **done** (store tested, UI driven headlessly) |
| 5 | README Results / Methodology, benchmark/CLAIMS.md | CLAIMS only after real results |

## Task 2: UX overhaul with before/after measurement

| Phase | Work | Status |
|-------|------|--------|
| D | Install Playwright, "before" screenshots (375x812, 1280x800, every tab), `docs/ux/audit.md`, baseline metrics | pending (runs on the refactored app, before UI changes) |
| 1-8 | Layout, search form, results table, fix-the-match, SQLite persistence, onboarding, fragments, accessibility | pending |
| M | Click/keystroke counts, Lighthouse + axe, latency; `usability-test.md` template left empty | pending |
| Docs | `docs/ux/CHANGELOG.md`, `docs/ux/CLAIMS.md`, README UX section | pending |

## Order of work

1. Phase 1, 2 (unblocked) -> 2. Task 2 discovery + baseline (no keys needed for most screens) -> 3. Task 2 implementation
-> 4. Phase 3-5 harness and docs -> 5. Stop and hand over the labeling sheet / ask for keys -> 6. Run benchmark, fill results.

Note: Task 2's "multi-ingredient breakdown" and "pick another match" depend on the Phase 1 package, so the refactor goes first.
