# Benchmark and engineering claims I can defend

Only statements backed by a file in this repository. Each row gives the exact sentence, the measured value, the sample size and the source.
Everything in `benchmark/results.md` comes from scripts that were actually run; nothing is estimated.

## Claimable now

| # | Claim (exact sentence) | Value | n | Source |
|---|---|---|---|---|
| 1 | "Running the three USDA searches concurrently cut the fallback path's median latency from 1.3 s to 0.5 s (p95 from 1.9 s to 0.8 s)." | p50 1,321 -> 536 ms; p95 1,850 -> 836 ms | 30 distinct queries, cold cache, same queries both passes (passes ran minutes apart, so small differences are noise) | `benchmark/results.md` section 6; `benchmark/ops_metrics.py` |
| 2 | "Found that USDA's API intermittently answers HTTP 400 to valid searches (about one in five requests in my measurement, concentrated on one data type) and added retries and error counting." | 21-23 retried 400s over about 111-113 requests per pass; 0 of 90 searches still failing after retries in the latest run (1 of 90 in an earlier run) | two passes of 30 queries | `benchmark/results.md` section 6; `nutripulse/apis.py` |
| 3 | "A disk response cache served 60% of requests (90 of 150) in a replayed session, avoiding 90 live API calls." | 60.0% hit rate | 150 lookups over 60 distinct queries; **synthetic** popularity-skewed session, not real traffic | `benchmark/results.md` section 6 |
| 4 | "The CalorieNinjas path answered in a median 234 ms (p95 282 ms)." | 234 / 282 ms | 60 live calls, one machine and network | `benchmark/results.md` section 6 |
| 5 | "143 automated tests (no live API calls) and a lint check pass in a fresh environment, and run in GitHub Actions on every push and pull request." | 143 passed, ruff clean | one clean-venv run with the exact CI steps; the workflow has not run on GitHub yet because nothing is pushed | `tests/`, `.github/workflows/ci.yml` |
| 6 | "Refactored a single 1,076-line Streamlit file into a tested package with no behavior change, verified against the original on generated inputs." | 330 scorer cases and 500 randomised TDEE/grade/tip cases, all identical | 330 + 500 | commit history (`4ac59af`, `a7c6ee3`); the comparison script was run interactively and is not stored |

## Not claimable yet (and why)

| What | Why not |
|---|---|
| Any match-accuracy figure (top-1, top-3, MRR), any statement that the scorer beats naive USDA ranking, or any "fewer match errors" percentage | The 139 benchmark queries have no ground-truth labels yet. `benchmark/labeling_sheet.csv` is ready; `python -m benchmark.run_benchmark report` refuses to run without labels. The earlier "75% fewer match errors" claim has no evidence and stays removed. |
| Per-term ablation results, tuned-weight results, Cohen's kappa | Need the same labels (and a second labeler for kappa). |
| Meal-level calorie/macro error | Needs reference values and sources in `benchmark/meals.csv`. |
| Real-user match-confirmed rate | The in-app thumbs log has no real-use data yet. |
| Usability results (task success, SUS) | No sessions have been run (`docs/ux/usability-test.md`). |
| That the "name closely matches / partial / weak" badge thresholds are well calibrated | They are display choices, unvalidated. |

Claim 6 is the weakest evidence in this file (the comparison script is not kept); say it as "verified on generated inputs" and no more than that.
