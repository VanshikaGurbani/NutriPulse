"""One lookup path for the UI: free text in, a list of ingredients out.

Each ingredient keeps its own per-100 g nutrition so the UI can show a breakdown, edit amounts, remove items and
swap a match. CalorieNinjas is tried first (it splits a phrase into items); USDA is the fallback.
"""
from . import apis, matching

NUTRIENTS = ("kcal", "protein", "carbs", "fat", "fiber", "sugar", "sodium")

# Matcher score thresholds for the confidence badge. `low` mirrors the app's existing LOW_CONFIDENCE_THRESHOLD;
# `high` is a display choice (not tuned or validated), so the badge is a hint, not a calibrated probability.
HIGH_SCORE = 10.0


def _per100_from_cn(item: dict) -> dict:
    g = item.get("serving_size_g") or 100
    f = 100 / g
    return {"kcal": item.get("calories", 0) * f, "protein": item.get("protein_g", 0) * f,
            "carbs": item.get("carbohydrates_total_g", 0) * f, "fat": item.get("fat_total_g", 0) * f,
            "fiber": item.get("fiber_g", 0) * f, "sugar": item.get("sugar_g", 0) * f, "sodium": item.get("sodium_mg", 0) * f}


def usda_confidence(result: dict) -> str:
    if result.get("low_confidence") or result.get("suspicious_calories"):
        return "low"
    return "high" if result.get("score", 0) >= HIGH_SCORE else "medium"


def usda_item(result: dict, name: str, grams: float) -> dict:
    return {"name": result["description"], "query_name": name, "grams": round(grams, 1), "source": "USDA",
            "source_detail": result["source"], "confidence": usda_confidence(result), "fdc_id": result.get("fdc_id"),
            "score": result.get("score"),
            "per100": {"kcal": result["calories"], "protein": result["protein"], "carbs": result["carbs"], "fat": result["fat"],
                       "fiber": result["fiber"], "sugar": 0.0, "sodium": 0.0}}


def lookup_meal(query: str, parallel: bool = True) -> dict | None:
    """Returns {"path": "calorieninjas" | "usda", "items": [...]} or None when nothing matched.
    Raises apis.ServiceError when the fallback cannot reach USDA."""
    items = apis.nlp_items(query)
    if items:
        out = []
        for i in items:
            if not i.get("serving_size_g"):
                continue
            out.append({"name": i["name"].title(), "query_name": i["name"], "grams": round(i["serving_size_g"], 1),
                        "source": "CalorieNinjas", "source_detail": "NLP-parsed", "confidence": "nlp", "fdc_id": None,
                        "score": None, "per100": _per100_from_cn(i), "amount_known": True})
        if out:
            return {"path": "calorieninjas", "items": out}
    amt = matching.parse_amount(query)
    name = amt["name"]
    ranked = matching.ranked_candidates(name, 5, parallel)
    if not ranked:
        return None
    food, score = ranked[0]
    # When the weight was not stated (a bare count, a slice, no amount) we show 100 g, the basis USDA values are listed for,
    # flag it, and make the person confirm or change it. We never invent a weight for "1 banana".
    item = usda_item(matching.to_result(food, score, name), name, amt["grams"] if amt["known"] else 100.0)
    item.update(amount_known=amt["known"], amount_hint=amt["hint"], amount_approx=amt["approx"])
    item["alternatives"] = [_alt_record(f, sc, name) for f, sc in ranked]     # free: same candidate list, no extra API call
    return {"path": "usda", "items": [item]}


def _alt_record(food: dict, score: float, name: str) -> dict:
    r = matching.to_result(food, score, name)
    return {"fdc_id": r["fdc_id"], "name": r["description"], "score": r["score"], "source_detail": r["source"],
            "confidence": usda_confidence(r),
            "per100": {"kcal": r["calories"], "protein": r["protein"], "carbs": r["carbs"], "fat": r["fat"],
                       "fiber": r["fiber"], "sugar": 0.0, "sodium": 0.0}}


def alternatives(name: str, k: int = 5, parallel: bool = True) -> list:
    """Top-k USDA candidates for one ingredient name, best first, as swappable per-100 g records."""
    return [_alt_record(f, sc, name) for f, sc in matching.ranked_candidates(name, k, parallel)]


def swap_match(item: dict, alt: dict) -> dict:
    """Replace an ingredient's nutrition with a chosen alternative, keeping its amount."""
    return dict(item, name=alt["name"], per100=dict(alt["per100"]), source="USDA", source_detail=alt["source_detail"],
                confidence="chosen", fdc_id=alt["fdc_id"], score=alt["score"])


def nutrients_for(item: dict, grams: float | None = None) -> dict:
    g = item["grams"] if grams is None else grams
    return {k: round(item["per100"][k] * g / 100, 1) for k in NUTRIENTS}


def totals(items: list) -> dict:
    out = {k: 0.0 for k in NUTRIENTS}
    for it in items:
        for k, v in nutrients_for(it).items():
            out[k] += v
    return {k: round(v, 1) for k, v in out.items()}


def to_entry(item: dict, meal: str, query: str) -> dict:
    n = nutrients_for(item)
    return {"meal": meal, "name": item["name"], "query": query, "grams": item["grams"], "kcal": n["kcal"], "protein": n["protein"],
            "carbs": n["carbs"], "fat": n["fat"], "fiber": n["fiber"], "sugar": n["sugar"], "sodium": n["sodium"],
            "source": item["source"], "fdc_id": item.get("fdc_id"), "confidence": item.get("confidence")}


def format_amount(grams: float) -> str:
    """'416.00' -> '416'; '0.5' stays '0.5'."""
    return f"{grams:,.0f}" if abs(grams - round(grams)) < 0.05 else f"{grams:,.1f}"
