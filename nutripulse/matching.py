"""Query parsing and USDA relevance scoring."""
import re

from . import apis
from .apis import NUTRIENT_IDS

CALORIE_IDS = [1008, 2047]

RAW_FOODS = {
    "apple", "banana", "orange", "grape", "strawberr", "blueberr", "mango",
    "watermelon", "pineapple", "peach", "pear", "cherry", "kiwi", "melon",
    "avocado", "tomato", "cucumber", "lettuce", "spinach", "kale",
    "carrot", "celery", "oil", "butter", "honey", "milk", "yogurt",
    "cheese", "juice", "nuts", "almond", "walnut", "cashew", "peanut",
}

UNIT_TO_GRAMS = {
    "g": 1.0, "kg": 1000.0, "oz": 28.35, "lb": 453.6,
    "cup": 240.0, "tbsp": 15.0, "tsp": 5.0, "ml": 1.0,
    "piece": 100.0, "slice": 30.0,
}
UNITS = list(UNIT_TO_GRAMS.keys())
MAX_SANE_CALORIES = 950
LOW_CONFIDENCE_THRESHOLD = 5

SOURCE_BADGES = {
    "Foundation":     "🟢 Foundation",
    "SR Legacy":      "🔵 SR Legacy",
    "Survey (FNDDS)": "🔵 Survey (FNDDS)",
    "Branded":        "🟡 Branded",
}

USDA_DATA_TYPES = ["Foundation", "Survey (FNDDS)", "SR Legacy"]


def parse_serving(text: str):
    text = text.strip()
    match = re.match(
        r"^(\d+(?:\.\d+)?(?:/\d+)?)\s*"
        r"(cups?|tbsps?|tsps?|fl\.?\s*oz|oz"
        r"|kg|lbs?|g|ml|l|pieces?|slices?)?\s*"
        r"(?:of\s+)?(.+)$",
        text, flags=re.IGNORECASE,
    )
    if not match:
        return 100.0, "g", clean_food_name(text)
    qty_str, unit_str, food = match.groups()
    if "/" in qty_str:
        n, d = qty_str.split("/")
        qty = float(n) / float(d)
    else:
        qty = float(qty_str)
    if unit_str:
        u = unit_str.lower().strip()
        if re.match(r"fl\.?\s*oz", u):
            unit = "oz"
        elif u.startswith("cup"):
            unit = "cup"
        elif u.startswith("tbsp"):
            unit = "tbsp"
        elif u.startswith("tsp"):
            unit = "tsp"
        elif u.startswith("lb"):
            unit = "lb"
        elif u.startswith("piece"):
            unit = "piece"
        elif u.startswith("slice"):
            unit = "slice"
        else:
            unit = u.rstrip("s") if u.endswith("s") and u not in ("oz", "ml") else u
            unit = unit if unit in UNIT_TO_GRAMS else "g"
    else:
        unit = "g"
    return qty, unit, clean_food_name(food)


def clean_food_name(name: str) -> str:
    name = re.sub(r"[^\w\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


def query_words(query: str) -> list:
    return [w.lower() for w in re.split(r"\s+", query.strip()) if w]


def _score(food: dict, q_words: list) -> float:
    desc = food.get("description", "").lower()
    tokens = re.split(r"[\s,]+", desc)
    all_present = all(re.search(rf"\b{re.escape(w)}\b", desc) for w in q_words)
    starts_with = 10 if (q_words and tokens and tokens[0] == q_words[0] and all_present) else 0
    n = max(len(q_words) + 1, 3)
    first_token_relevant = bool(tokens and tokens[0] in q_words)
    in_first_tokens = 5 if (first_token_relevant and all(w in tokens[:n] for w in q_words)) else 0
    word_hits = sum(1 for w in q_words if re.search(rf"\b{re.escape(w)}\b", desc))
    is_raw_food = any(rw in " ".join(q_words) for rw in RAW_FOODS)
    user_specified_prep = any(w in q_words for w in ("raw", "cooked", "baked", "grilled", "boiled", "fried", "roasted"))
    if not is_raw_food and not user_specified_prep:
        cooked_bonus = 4 if "cooked" in desc else 0
        raw_penalty = -3 if re.search(r"\braw\b", desc) else 0
    else:
        cooked_bonus = raw_penalty = 0
    first_mismatch = -8 if (tokens and tokens[0] not in q_words) else 0
    wrong_category = 0
    if first_mismatch and q_words:
        segs = [s.strip() for s in desc.split(",")]
        if (len(segs) > 1
                and not any(re.search(rf"\b{re.escape(w)}\b", segs[0]) for w in q_words)
                and any(re.search(rf"\b{re.escape(w)}\b", sg) for w in q_words for sg in segs[1:])):
            wrong_category = -10
    nutrients = {n_["nutrientId"]: n_.get("value", 0) for n_ in food.get("foodNutrients", [])}
    calorie_penalty = -50 if nutrients.get(NUTRIENT_IDS["calories"], 0) > MAX_SANE_CALORIES else 0
    brevity = -len(desc) / 200
    return (starts_with + in_first_tokens + word_hits + cooked_bonus + raw_penalty
            + first_mismatch + wrong_category + calorie_penalty + brevity)


def best_match(foods: list, query: str) -> tuple:
    q_words = query_words(query)
    scored = [(f, _score(f, q_words)) for f in foods]
    return max(scored, key=lambda x: x[1])


def collect_candidates(query: str) -> list:
    """All USDA candidates the app considers, in API order."""
    foods: list = []
    for dt in USDA_DATA_TYPES:
        foods.extend(apis.usda_fetch(query, dt))
    if not foods:
        foods = apis.usda_fetch(query, None)
    return foods


def to_result(food: dict, match_score: float, query: str) -> dict:
    nutrients = {n["nutrientId"]: n.get("value", 0) for n in food.get("foodNutrients", [])}
    calories = round(next((nutrients[cid] for cid in CALORIE_IDS if nutrients.get(cid, 0) > 0), 0), 1)
    raw_type = food.get("dataType", "Unknown")
    desc_lower = food.get("description", "").lower()
    any_word_found = any(re.search(rf"\b{re.escape(w)}\b", desc_lower) for w in query_words(query))
    return {
        "description":        food.get("description", query),
        "fdc_id":             food.get("fdcId"),
        "score":              round(match_score, 2),
        "calories":           calories,
        "protein":            round(nutrients.get(NUTRIENT_IDS["protein"], 0), 1),
        "fat":                round(nutrients.get(NUTRIENT_IDS["fat"], 0), 1),
        "carbs":              round(nutrients.get(NUTRIENT_IDS["carbs"], 0), 1),
        "fiber":              round(nutrients.get(NUTRIENT_IDS["fiber"], 0), 1),
        "source":             SOURCE_BADGES.get(raw_type, f"📄 {raw_type}"),
        "suspicious_calories": calories > MAX_SANE_CALORIES,
        "low_confidence":     match_score < LOW_CONFIDENCE_THRESHOLD or not any_word_found,
    }


def search_food(query: str):
    foods = collect_candidates(query)
    if not foods:
        return None
    food, match_score = best_match(foods, query)
    return to_result(food, match_score, query)
