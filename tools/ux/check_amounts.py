"""Runs a handful of phrases through the app's USDA fallback path on REAL USDA data and writes docs/ux/amounts-check.md.

CalorieNinjas is disabled so the fallback path (portion sizes, splitting, unstated weights) is exercised. Responses are cached in
benchmark/cache, so re-running is free. This is an illustration of behaviour on 7 phrases, not an accuracy measurement.

    python -m tools.ux.check_amounts
"""
import datetime

from benchmark.common import BENCH, ROOT, apis, setup_cache, stats
from nutripulse import lookup

PHRASES = ["1 cup cooked white rice", "2 cups white rice and carrots", "3 tbsp peanut butter", "1 banana", "2 large eggs",
           "macaroni and cheese", "100 g chicken breast"]


def main():
    setup_cache(80, BENCH / "cache")
    apis.nlp_items = lambda q: None          # force the USDA fallback path
    rows = []
    for q in PHRASES:
        try:
            r = lookup.lookup_meal(q)
        except apis.ServiceError as e:
            rows.append(f"| {q} | service error: {e.kind} | | | |")
            continue
        for it in (r or {"items": []})["items"]:
            ports = ", ".join(p["label"] for p in it.get("portions", [])[:3]) or "-"
            how = ("stated weight" if it["amount_known"] and not it.get("amount_note") else
                   it["amount_note"] if it.get("amount_note") else "NOT stated: 100 g placeholder, must be confirmed")
            rows.append(f"| {q} | {it['name']} | {it['grams']:g} g | {how} | {ports} |")
    text = ["# Amount handling on real USDA data (fallback path)", "",
            f"Generated {datetime.datetime.now():%Y-%m-%d %H:%M} by `tools/ux/check_amounts.py`. Seven phrases, USDA data as of that date, "
            "CalorieNinjas disabled. Illustrates behaviour; it is not an accuracy measurement. The matched food is the scorer's choice and "
            "can be wrong (see the benchmark).", "", "| Phrase | Matched food | Amount used | How the amount was decided | USDA serving sizes found |", "|---|---|---|---|---|"]
    text += rows + ["", f"Live API calls: {stats.api_calls}; served from cache: {stats.cache_hits}; retried 400s: {stats.retries}; failed after retries: {stats.errors}.", ""]
    (ROOT / "docs/ux/amounts-check.md").write_text("\n".join(text), encoding="utf-8")
    print("\n".join(text))


if __name__ == "__main__":
    main()
