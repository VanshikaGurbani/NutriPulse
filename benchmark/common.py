"""Shared helpers: paths, cache set-up, labelled-query loading, candidate pools."""
import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nutripulse import apis, matching  # noqa: E402
from nutripulse.cache import DiskCache, stats  # noqa: E402

BENCH = ROOT / "benchmark"
CACHE_DIR = BENCH / "cache"
QUERIES_CSV = BENCH / "queries.csv"
SEED = 20240601


def setup_cache(max_calls: int = 500, cache_dir: Path = CACHE_DIR):
    """Route every request through the JSON cache and cap live calls for this run."""
    apis.configure_cache(DiskCache(cache_dir))
    apis.set_call_budget(max_calls)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def parse_ids(cell: str) -> set:
    return {int(x) for x in (cell or "").replace(" ", "").split("|") if x}


def load_queries(split=None):
    rows = read_csv(QUERIES_CSV)
    if split:
        rows = [r for r in rows if r["split"] == split]
    return rows


def file_sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def kcal_per_100g(food: dict):
    nut = {n["nutrientId"]: n.get("value", 0) for n in food.get("foodNutrients", [])}
    for cid in matching.CALORIE_IDS:
        if nut.get(cid, 0) > 0:
            return nut[cid]
    return 0.0


__all__ = ["apis", "matching", "stats", "setup_cache", "read_csv", "write_csv", "parse_ids",
           "load_queries", "file_sha", "kcal_per_100g", "ROOT", "BENCH", "CACHE_DIR", "SEED"]
