"""Inter-labeler agreement. Compares two filled labeling sheets on the rows both labelled.

    python -m benchmark.kappa labeler1_sheet.csv labeler2_sheet.csv
"""
import sys

from benchmark.common import read_csv
from benchmark.metrics import cohen_kappa


def compare(path_a, path_b):
    a = {(r["query_id"], r["fdc_id"]): r["acceptable"].strip().lower() for r in read_csv(path_a)}
    b = {(r["query_id"], r["fdc_id"]): r["acceptable"].strip().lower() for r in read_csv(path_b)}
    keys = sorted(k for k in a.keys() & b.keys() if a[k] in ("y", "n") and b[k] in ("y", "n"))
    if not keys:
        raise SystemExit("no overlapping labelled rows")
    la, lb = [a[k] for k in keys], [b[k] for k in keys]
    kappa, po = cohen_kappa(la, lb)
    return {"n_rows": len(keys), "n_queries": len({k[0] for k in keys}), "kappa": kappa, "agreement": po,
            "pos_rate_a": la.count("y") / len(la), "pos_rate_b": lb.count("y") / len(lb)}


if __name__ == "__main__":
    r = compare(sys.argv[1], sys.argv[2])
    print(f"Cohen's kappa = {r['kappa']:.3f} over {r['n_rows']} candidate judgments "
          f"({r['n_queries']} queries); raw agreement {r['agreement']:.1%}")
