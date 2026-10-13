# Benchmark results

<!-- ops:start -->
## 6. Operational metrics (synthetic replayed session)

150 lookups drawn from 60 distinct queries (seeded, popularity-skewed; **not real user traffic**), run from a cold cache through the app lookup path (CalorieNinjas first, USDA fallback). Latencies depend on the machine and network used for the run.

| Metric | Value | n |
|---|---|---|
| Live latency, calorieninjas path: p50 / p95 | 234 ms / 282 ms | 60 |
| Cache-served lookup: p50 / p95 | 0.4 ms / 6.9 ms | 90 |
| USDA fallback rate (distinct queries where CalorieNinjas returned nothing) | 0.0% | 60 |
| Request-level cache hit rate | 60.0% | 150 requests |
| Live API calls made | 60 | |
| API calls avoided by caching | 90 of 150 (60.0%) | |

### USDA path latency (forced, cold cache)

The USDA fallback never triggered in the session above, so its latency was measured separately: 30 distinct queries run through `search_food` (3 typed USDA searches each, plus retries of USDA's intermittent 400s) from an empty cache.

| Metric | Value | n |
|---|---|---|
| Live latency, USDA path (3 searches): p50 / p95 | 1324 ms / 1814 ms | 30 |
| Live HTTP requests per lookup (mean, incl. retries) | 4.00 | 30 |
| Requests that hit a 400 and were retried | 30 | 120 requests |
| Searches that still failed after retries | 1 | 90 searches |
<!-- ops:end -->
