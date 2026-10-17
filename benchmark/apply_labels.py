"""Writes a filled labeling sheet into queries.csv (acceptable_fdc_ids, pipe-separated).

Every row must be y or n; blank rows abort so partial labeling is never silently treated as 'no'.
Queries where every candidate is 'n' keep an empty list and are reported (no acceptable match exists).

    python -m benchmark.apply_labels benchmark/labeling_sheet_filled.csv
"""
import sys
from collections import defaultdict

from benchmark.common import QUERIES_CSV, read_csv, write_csv


def main(path):
    sheet = read_csv(path)
    blanks = [r for r in sheet if r["acceptable"].strip().lower() not in ("y", "n")]
    if blanks:
        sys.exit(f"{len(blanks)} rows have no y/n label (first: {blanks[0]['query_id']} / {blanks[0]['fdc_id']}). Aborting.")
    acc = defaultdict(list)
    seen = set()
    for r in sheet:
        seen.add(r["query_id"])
        if r["acceptable"].strip().lower() == "y":
            acc[r["query_id"]].append(r["fdc_id"])
    queries = read_csv(QUERIES_CSV)
    for q in queries:
        if q["id"] in seen:
            q["acceptable_fdc_ids"] = "|".join(acc.get(q["id"], []))
            tags = [t for t in q["notes"].split(";") if t and t not in ("labeled=1", "no_acceptable")]
            tags.append("labeled=1")
            if not q["acceptable_fdc_ids"]:
                tags.append("no_acceptable")
            q["notes"] = ";".join(tags)
    write_csv(QUERIES_CSV, queries, ["id", "query", "split", "acceptable_fdc_ids", "notes"])
    none = [q["id"] for q in queries if q["id"] in seen and not q["acceptable_fdc_ids"]]
    print(f"labelled {len(seen)} queries; {len(none)} have no acceptable candidate: {none}")


if __name__ == "__main__":
    main(sys.argv[1])
