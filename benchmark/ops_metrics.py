"""Operational metrics from a replayed session through the app's real lookup path.

The session is SYNTHETIC: N lookups drawn (seeded, popularity-skewed) from benchmark/queries.csv. It is not
real user traffic and results.md says so. It runs against its own cache dir (benchmark/cache_ops, git-ignored)
that starts empty, so the first occurrence of each query is a live call and repeats are cache hits.

Path logic mirrors nutrition_tracker.py: CalorieNinjas first; if it returns nothing, USDA (3 typed searches).

    python -m benchmark.ops_metrics [--max-calls 500] [--lookups 150]
"""
import argparse
import random
import shutil
import time

from benchmark.common import BENCH, SEED, apis, load_queries, matching, update_section
from nutripulse.cache import DiskCache, stats

OPS_CACHE = BENCH / "cache_ops"
OPS_CACHE_USDA = BENCH / "cache_ops_usda"
NL = chr(10)


def percentile(xs, p):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100
    f, c = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def lookup(query):
    """The app search path. Returns which path served the query."""
    if apis.search_food_nlp(query) is not None:
        return "calorieninjas"
    matching.search_food(matching.parse_serving(query)[2])
    return "usda_fallback"


def replay(queries, n_lookups, seed=SEED):
    rng = random.Random(seed)
    order = list(queries)
    rng.shuffle(order)
    session = rng.choices(order, weights=[1 / (i + 1) for i in range(len(order))], k=n_lookups)
    recs = []
    for q in session:
        before = stats.api_calls
        t0 = time.perf_counter()
        path = lookup(q)
        recs.append({"query": q, "path": path, "ms": (time.perf_counter() - t0) * 1000, "live": stats.api_calls - before})
    return recs


def summarize(recs):
    uniq_first = {}
    for r in recs:
        uniq_first.setdefault(r["query"], r["path"])
    live = [r for r in recs if r["live"] > 0]
    cached = [r for r in recs if r["live"] == 0]
    fallback_rate = sum(p == "usda_fallback" for p in uniq_first.values()) / len(uniq_first)
    L = ["## 6. Operational metrics (synthetic replayed session)", "",
         f"{len(recs)} lookups drawn from {len(uniq_first)} distinct queries (seeded, popularity-skewed; **not real user traffic**), "
         "run from a cold cache through the app lookup path (CalorieNinjas first, USDA fallback). "
         "Latencies depend on the machine and network used for the run.", "",
         "| Metric | Value | n |", "|---|---|---|"]
    for path in ("calorieninjas", "usda_fallback"):
        xs = [r["ms"] for r in live if r["path"] == path]
        if xs:
            L.append(f"| Live latency, {path} path: p50 / p95 | {percentile(xs, 50):.0f} ms / {percentile(xs, 95):.0f} ms | {len(xs)} |")
    if cached:
        xs = [r["ms"] for r in cached]
        L.append(f"| Cache-served lookup: p50 / p95 | {percentile(xs, 50):.1f} ms / {percentile(xs, 95):.1f} ms | {len(xs)} |")
    L += [f"| USDA fallback rate (distinct queries where CalorieNinjas returned nothing) | {fallback_rate:.1%} | {len(uniq_first)} |",
          f"| Request-level cache hit rate | {stats.hit_rate:.1%} | {stats.lookups} requests |",
          f"| Live API calls made | {stats.api_calls} | |",
          f"| API calls avoided by caching | {stats.cache_hits} of {stats.lookups} ({stats.cache_hits / max(stats.lookups, 1):.1%}) | |", ""]
    return "\n".join(L)


def _timed_usda_pass(sample, parallel, cache_dir):
    shutil.rmtree(cache_dir, ignore_errors=True)
    apis.configure_cache(DiskCache(cache_dir))
    stats.reset()
    ms = []
    for q in sample:
        t0 = time.perf_counter()
        matching.search_food(matching.parse_serving(q)[2], parallel=parallel)
        ms.append((time.perf_counter() - t0) * 1000)
    return ms, {"calls": stats.api_calls, "retries": stats.retries, "errors": stats.errors}


def usda_path_latency(queries, n, seed=SEED):
    """Force the USDA path (what runs on fallback) on the same n distinct queries twice from cold caches: the three typed
    searches one after another, then concurrently (what the app does)."""
    sample = random.Random(seed + 1).sample(sorted(set(queries)), n)
    seq, seq_s = _timed_usda_pass(sample, False, OPS_CACHE_USDA)
    par, par_s = _timed_usda_pass(sample, True, BENCH / "cache_ops_usda_parallel")
    return ["", "### USDA path latency (forced, cold cache)", "",
            f"The USDA fallback never triggered in the session above, so its latency was measured separately on {n} distinct queries "
            "(3 typed USDA searches each, plus retries of USDA's intermittent 400s), twice from an empty cache: searches one after another, "
            "then concurrently (what the app does). The two passes hit USDA at different moments, so treat small differences as noise.", "",
            "| Metric | Sequential | Concurrent | n |", "|---|---|---|---|",
            f"| Live latency, USDA path: p50 | {percentile(seq, 50):.0f} ms | {percentile(par, 50):.0f} ms | {n} |",
            f"| Live latency, USDA path: p95 | {percentile(seq, 95):.0f} ms | {percentile(par, 95):.0f} ms | {n} |",
            f"| Live HTTP requests per lookup (mean, incl. retries) | {seq_s['calls'] / n:.2f} | {par_s['calls'] / n:.2f} | {n} |",
            f"| Requests that hit a 400 and were retried | {seq_s['retries']} | {par_s['retries']} | |",
            f"| Searches that still failed after retries | {seq_s['errors']} | {par_s['errors']} | {n * 3} searches each |", ""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-calls", type=int, default=500)
    ap.add_argument("--lookups", type=int, default=150)
    ap.add_argument("--usda-sample", type=int, default=30)
    args = ap.parse_args()
    shutil.rmtree(OPS_CACHE, ignore_errors=True)
    apis.configure_cache(DiskCache(OPS_CACHE))
    apis.set_call_budget(args.max_calls)
    stats.reset()
    recs = replay([r["query"] for r in load_queries()], args.lookups)
    text = summarize(recs)
    if args.usda_sample:
        text += NL.join(usda_path_latency([r["query"] for r in load_queries()], args.usda_sample))
    update_section("ops", text)
    print(text)


if __name__ == "__main__":
    main()
