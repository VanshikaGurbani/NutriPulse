"""Builds the sheet a human fills in to label ground truth.

For each query it shows up to 10 USDA candidates in a NEUTRAL order (seeded shuffle, independent of
the scorer's ranking and of the API order) so the labeler is not primed by either system.
The 10 are chosen by interleaving the three USDA result lists rank-by-rank (round-robin), so every
data type is represented. Fill the `acceptable` column with y or n for every row.

Live API calls happen only for queries missing from benchmark/cache. Default cap: 500 calls.

    python -m benchmark.make_labeling_sheet --out benchmark/labeling_sheet.csv [--ids q001,q002] [--max-calls 500]
"""
import argparse
import random

from benchmark.common import SEED, kcal_per_100g, load_queries, matching, setup_cache, stats, write_csv

FIELDS = ["query_id", "query", "shown_pos", "fdc_id", "description", "data_type", "kcal_per_100g", "acceptable"]


def pick_pool(lists, k=10):
    """Round-robin across the per-data-type lists, deduplicated by fdcId, first k."""
    out, seen = [], set()
    for rank in range(max((len(x) for x in lists), default=0)):
        for lst in lists:
            if rank < len(lst) and lst[rank]["fdcId"] not in seen:
                seen.add(lst[rank]["fdcId"])
                out.append(lst[rank])
    return out[:k]


def build_rows(queries):
    rows = []
    for q in queries:
        pool = pick_pool(matching.candidate_lists(q["query"]))
        random.Random(f"{SEED}-{q['id']}").shuffle(pool)       # neutral order
        for pos, food in enumerate(pool, start=1):
            rows.append({"query_id": q["id"], "query": q["query"], "shown_pos": pos, "fdc_id": food["fdcId"],
                         "description": food.get("description", ""), "data_type": food.get("dataType", ""),
                         "kcal_per_100g": kcal_per_100g(food), "acceptable": ""})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="benchmark/labeling_sheet.csv")
    ap.add_argument("--ids", help="comma-separated query ids (default: all)")
    ap.add_argument("--max-calls", type=int, default=500)
    args = ap.parse_args()
    setup_cache(args.max_calls)
    queries = load_queries()
    if args.ids:
        keep = set(args.ids.split(","))
        queries = [q for q in queries if q["id"] in keep]
    rows = build_rows(queries)
    write_csv(args.out, rows, FIELDS)
    print(f"wrote {len(rows)} candidate rows for {len(queries)} queries to {args.out}")
    print(f"live API calls this run: {stats.api_calls}; served from cache: {stats.cache_hits}")


if __name__ == "__main__":
    main()
