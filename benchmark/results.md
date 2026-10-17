# Benchmark results

<!-- ops:start -->
## 6. Operational metrics (synthetic replayed session)

150 lookups drawn from 60 distinct queries (seeded, popularity-skewed; **not real user traffic**), run from a cold cache through the app lookup path (CalorieNinjas first, USDA fallback). Latencies depend on the machine and network used for the run.

| Metric | Value | n |
|---|---|---|
| Live latency, calorieninjas path: p50 / p95 | 230 ms / 280 ms | 60 |
| Cache-served lookup: p50 / p95 | 0.4 ms / 7.8 ms | 90 |
| USDA fallback rate (distinct queries where CalorieNinjas returned nothing) | 0.0% | 60 |
| Request-level cache hit rate | 60.0% | 150 requests |
| Live API calls made | 60 | |
| API calls avoided by caching | 90 of 150 (60.0%) | |

### USDA path latency (forced, cold cache)

The USDA fallback never triggered in the session above, so its latency was measured separately on 30 distinct queries (3 typed USDA searches each, plus retries of USDA's intermittent 400s), twice from an empty cache: searches one after another, then concurrently (what the app does). The two passes hit USDA at different moments, so treat small differences as noise.

| Metric | Sequential | Concurrent | n |
|---|---|---|---|
| Live latency, USDA path: p50 | 1321 ms | 536 ms | 30 |
| Live latency, USDA path: p95 | 1850 ms | 836 ms | 30 |
| Live HTTP requests per lookup (mean, incl. retries) | 3.77 | 3.70 | 30 |
| Requests that hit a 400 and were retried | 23 | 21 | |
| Searches that still failed after retries | 0 | 0 | 90 searches each |
<!-- ops:end -->
