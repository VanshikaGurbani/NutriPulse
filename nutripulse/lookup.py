"""One lookup path for the UI: free text in, a list of ingredients out.

Each ingredient keeps its own per-100 g nutrition so the UI can show a breakdown, edit amounts, remove items and
swap a match. CalorieNinjas is tried first (it splits a phrase into items); USDA is the fallback.
"""
from . import apis, matching

NUTRIENTS = ("kcal", "protein", "carbs", "fat", "fiber", "sugar", "sodium")

# Matcher score thresholds for the confidence badge. `low` mirrors the app's existing LOW_CONFIDENCE_THRESHOLD;
# `high` is a display choice (not tuned or validated). The score measures NAME similarity, not correctness, so badges are worded that way.
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
    whole = _usda_item(query, parallel)
    parts = matching.split_phrase(query)
    name = matching.parse_amount(query)["name"]
    # "white rice and carrots" matched as one food explains only part of the phrase: look each part up on its own.
    # A dish that the phrase fully explains ("macaroni and cheese") is kept whole.
    if len(parts) > 1 and (whole is None or not matching.covers_query(whole["name"], name)):
        items = [it for it in (_usda_item(part, parallel) for part in parts) if it]
        if items:
            return {"path": "usda", "items": items}
    return {"path": "usda", "items": [whole]} if whole else None


def resolve_amount(amt: dict, fdc_id) -> dict:
    """Grams for a parsed amount, using this food's own USDA serving sizes where they exist.

    - mass units are exact;
    - cup/tbsp/tsp use the food's portion data (a cup of cooked white rice is 174 g, not water's 240 g) and fall back to the
      water-density approximation, flagged;
    - a bare count, piece, slice or no amount has no known weight: show 100 g as a flagged placeholder and offer the
      food's real serving sizes to choose from.
    """
    out = {"grams": None, "known": amt["known"], "approx": amt["approx"], "note": None, "portions": [], "qty": amt.get("qty") or 1.0}
    if amt["known"]:
        out["grams"] = amt["grams"]
        if amt["unit"] in matching.PORTION_WORDS and fdc_id:
            hit = matching.grams_from_portions(apis.usda_portions(fdc_id), amt["unit"], amt["qty"])
            if hit:
                out.update(grams=round(hit[0], 1), approx=False, note=f"Using USDA's serving size for this food: “{hit[1]}”.")
        return out
    out["grams"] = 100.0
    out["portions"] = apis.usda_portions(fdc_id)[:12] if fdc_id else []
    return out


def _usda_item(text: str, parallel: bool):
    amt = matching.parse_amount(text)
    ranked = matching.ranked_candidates(amt["name"], 5, parallel)
    if not ranked:
        return None
    food, score = ranked[0]
    result = matching.to_result(food, score, amt["name"])
    res = resolve_amount(amt, result["fdc_id"])
    item = usda_item(result, amt["name"], res["grams"])
    item.update(amount_known=res["known"], amount_hint=amt["hint"], amount_approx=res["approx"], amount_note=res["note"],
                portions=res["portions"], amount_qty=res["qty"])
    item["alternatives"] = [_alt_record(f, sc, amt["name"]) for f, sc in ranked]     # free: same candidate list, no extra API call
    return item


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
