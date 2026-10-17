"""Meal-level nutrient accuracy: end-to-end estimate vs a cited reference value.

Two app paths are evaluated on each meal that has reference values in benchmark/meals.csv:
  * CalorieNinjas path: the whole meal_text sent as one query (the app's primary path)
  * USDA fallback path: each ingredient parsed with parse_serving, matched with the scorer, scaled by grams

Metric: mean absolute percentage error (MAPE) per nutrient over meals with a positive reference.
Meals with empty reference columns or no ref_source are skipped and counted.

    python -m benchmark.run_meals [--max-calls 500]
"""
import argparse

from benchmark.common import BENCH, apis, matching, read_csv, setup_cache, stats, update_section, write_csv
from benchmark.metrics import bootstrap_ci, mape
from nutripulse import lookup

NUTS = [("kcal", "ref_kcal"), ("protein", "ref_protein_g"), ("carbs", "ref_carbs_g"), ("fat", "ref_fat_g")]


def cn_estimate(meal_text):
    items = apis.nlp_items(meal_text)
    if not items:
        return None
    return {"kcal": sum(i.get("calories", 0) for i in items), "protein": sum(i.get("protein_g", 0) for i in items),
            "carbs": sum(i.get("carbohydrates_total_g", 0) for i in items), "fat": sum(i.get("fat_total_g", 0) for i in items),
            "detail": [f"{i['name']} {i.get('serving_size_g', '?')} g = {i.get('calories', 0):.0f} kcal" for i in items],
            "grams": sum(i.get("serving_size_g", 0) for i in items)}


def usda_estimate(ingredients):
    tot = {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    detail, grams = [], 0.0
    for ing in ingredients:
        amt = matching.parse_amount(ing)
        if not amt["known"]:
            return None       # the app would ask the person for this weight; we do not invent one
        name = amt["name"]
        r = matching.search_food(name)
        if r is None:
            detail.append(f"{ing!r}: no match")
            continue
        g = lookup.resolve_amount(amt, r.get("fdc_id"))["grams"]       # same rule as the app: the food's own USDA serving size for cups/spoons
        f = g / 100
        tot["kcal"] += r["calories"] * f
        tot["protein"] += r["protein"] * f
        tot["carbs"] += r["carbs"] * f
        tot["fat"] += r["fat"] * f
        grams += g
        detail.append(f"{ing!r} -> {r['description']} ({g:.0f} g, {r['calories'] * f:.0f} kcal)")
    return dict(tot, detail=detail, grams=grams)


def listed_grams(ingredients):
    """Total grams of the ingredients whose weight is stated; None-weight ingredients (bare counts) are skipped."""
    return sum(a["grams"] for a in map(matching.parse_amount, ingredients) if a["known"])


def evaluate(meals):
    out = []
    for m in meals:
        ref = {k: float(m[col]) for k, col in NUTS}
        ing = [x for x in m["ingredients"].split("|") if x]
        out.append({"meal": m, "ref": ref, "ingredients": ing,
                    "cn": cn_estimate(m["meal_text"]), "usda": usda_estimate(ing)})
    return out


def summarize(results, path):
    rows = {}
    for k, _ in NUTS:
        used = [r for r in results if not (path == "usda" and r["usda"] is None)]   # skipped: amount unknown, the app would ask
        ests = [r[path][k] if r[path] else 0.0 for r in used]                        # failed lookups count as a 0 estimate
        refs = [r["ref"][k] for r in used]
        score, n = mape(ests, refs)
        errs = [abs(e - rf) / rf * 100 for e, rf in zip(ests, refs) if rf > 0]
        lo, hi = bootstrap_ci(errs, 1000, 20240601)
        rows[k] = (score, lo, hi, n)
    return rows


def worst(results, path, k=5):
    scored = []
    for r in results:
        if path == "usda" and r["usda"] is None:
            continue
        ref = r["ref"]["kcal"]
        est = r[path]["kcal"] if r[path] else 0.0
        scored.append((abs(est - ref) / ref * 100 if ref > 0 else 0, est, r))
    return sorted(scored, key=lambda x: -x[0])[:k]


def explain(r, path):
    e = r[path]
    if e is None:
        return "lookup returned nothing"
    notes = []
    listed = listed_grams(r["ingredients"])
    if e["grams"] and listed and abs(e["grams"] - listed) / listed > 0.25:
        notes.append(f"parsed {e['grams']:.0f} g in total vs {listed:.0f} g from the ingredient list (quantity/unit parsing)")
    if path == "cn" and len(e["detail"]) != len(r["ingredients"]):
        notes.append(f"{len(e['detail'])} items parsed vs {len(r['ingredients'])} ingredients listed")
    return "; ".join(notes) or "no parsing discrepancy detected automatically; inspect item matches"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-calls", type=int, default=500)
    args = ap.parse_args()
    setup_cache(args.max_calls)
    meals = read_csv(BENCH / "meals.csv")
    ready = [m for m in meals if all(m[c].strip() for _, c in NUTS) and m["ref_source"].strip()]
    skipped = len(meals) - len(ready)
    if not ready:
        raise SystemExit("meals.csv has no rows with reference values + ref_source; fill them in first")
    results = evaluate(ready)
    L = ["## 5. Meal-level nutrient accuracy", "",
         f"n = {len(ready)} meals with cited reference values ({skipped} skipped for missing references). "
         "MAPE = mean |estimate - reference| / reference over meals with reference > 0; failed lookups count as a 0 estimate. "
         "95% bootstrap CI on the per-meal errors.", "",
         "| Path | kcal MAPE | protein MAPE | carbs MAPE | fat MAPE |", "|---|---|---|---|---|"]
    csv_rows = []
    for path, label in (("cn", "CalorieNinjas (whole meal text)"), ("usda", "USDA fallback (parsed ingredients + scorer)")):
        s = summarize(results, path)
        L.append(f"| {label} | " + " | ".join(f"{s[k][0]:.1f}% [{s[k][1]:.1f}, {s[k][2]:.1f}] (n={s[k][3]})" for k, _ in NUTS) + " |")
        for k, _ in NUTS:
            csv_rows.append({"path": path, "nutrient": k, "mape_pct": round(s[k][0], 2), "ci_low": round(s[k][1], 2),
                             "ci_high": round(s[k][2], 2), "n": s[k][3]})
    for path, label in (("cn", "CalorieNinjas"), ("usda", "USDA fallback")):
        L += ["", f"### Five worst meals by calorie error: {label}", "",
              "| Meal | Reference kcal | Estimate kcal | Error | Automatic diagnosis | Items |", "|---|---|---|---|---|---|"]
        for err, est, r in worst(results, path):
            items = "<br>".join(r[path]["detail"]) if r[path] else "-"
            L.append(f"| {r['meal']['meal_text']} | {r['ref']['kcal']:.0f} | {est:.0f} | {err:.0f}% | {explain(r, path)} | {items} |")
    unknown = sum(r["usda"] is None for r in results)
    L += ["", f"USDA fallback path: {unknown} of {len(results)} meals were excluded because an ingredient had no stated weight "
          "(for example \"1 banana\"); the app asks the person for the weight in that case, so there is no estimate to score.",
          "", "Reference sources: " + "; ".join(sorted({m["ref_source"] for m in ready})), ""]
    update_section("meals", "\n".join(L))
    write_csv(BENCH / "meals_results.csv", csv_rows, ["path", "nutrient", "mape_pct", "ci_low", "ci_high", "n"])
    print(f"meals evaluated: {len(ready)}; live API calls {stats.api_calls}, cache hits {stats.cache_hits}")


if __name__ == "__main__":
    main()
