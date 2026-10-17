"""Query parsing and USDA relevance scoring."""
import re
from concurrent.futures import ThreadPoolExecutor

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
    "cup": 240.0, "tbsp": 15.0, "tsp": 5.0, "ml": 1.0, "l": 1000.0, "floz": 29.57,
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


# Unit spellings people type, mapped to the keys of UNIT_TO_GRAMS.
_UNIT_ALIASES = {
    "g": "g", "gm": "g", "gram": "g", "grams": "g", "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "oz": "oz", "ounce": "oz", "ounces": "oz", "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "cup": "cup", "cups": "cup", "tbsp": "tbsp", "tbsps": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "tsp": "tsp", "tsps": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "piece": "piece", "pieces": "piece", "slice": "slice", "slices": "slice",
}
# Units whose weight depends on the food: the app cannot know them, so it must ask instead of guessing.
FOOD_DEPENDENT_UNITS = {"piece", "slice"}
# Volume units are converted as if the food weighed the same as water (an approximation worth saying out loud).
VOLUME_UNITS = {"cup", "tbsp", "tsp", "ml", "l", "floz"}

_UNIT_RE = r"fl\.?\s*oz|" + "|".join(sorted((re.escape(k) for k in _UNIT_ALIASES), key=len, reverse=True))
_SERVING_RE = re.compile(
    rf"^(\d+\s+\d+/\d+|\d+(?:\.\d+)?(?:/\d+)?)\s*(?:({_UNIT_RE})(?=\s|$))?\s*(?:of\s+)?(.+)$", flags=re.IGNORECASE)


def _quantity(qty_str: str) -> float:
    parts = qty_str.split()
    total = 0.0
    for part in parts:
        if "/" in part:
            n, d = part.split("/")
            total += float(n) / float(d)
        else:
            total += float(part)
    return total


def _canonical_unit(unit_str):
    if not unit_str:
        return None
    u = re.sub(r"\s+", " ", unit_str.lower().strip())
    if re.match(r"fl\.?\s*oz", u):
        return "floz"
    return _UNIT_ALIASES.get(u)


def parse_serving(text: str):
    """(quantity, unit, food name). Missing quantity -> 100 g; missing unit -> grams. Use parse_amount when you
    need to know whether the amount was actually stated."""
    m = _SERVING_RE.match(text.strip())
    if not m:
        return 100.0, "g", clean_food_name(text)
    qty_str, unit_str, food = m.groups()
    return _quantity(qty_str), _canonical_unit(unit_str) or "g", clean_food_name(food)


def parse_amount(text: str) -> dict:
    """Like parse_serving, but honest about what was stated.

    known=True only for mass/volume units (g, oz, cup, tbsp, ml, ...). A bare count ("2 eggs"), a piece/slice, or no amount at all
    gives known=False and grams=None: the caller must ask the person for a weight rather than invent one.
    """
    text = text.strip()
    m = _SERVING_RE.match(text)
    if not m:
        return {"name": clean_food_name(text), "qty": None, "unit": None, "grams": None, "known": False, "approx": False, "hint": text}
    qty_str, unit_str, food = m.groups()
    qty, unit, name = _quantity(qty_str), _canonical_unit(unit_str), clean_food_name(food)
    if unit is None or unit in FOOD_DEPENDENT_UNITS:
        label = f"{qty:g} {unit + ('s' if qty != 1 else '') + ' of' if unit else ''} {name}".replace("  ", " ").strip()
        return {"name": name, "qty": qty, "unit": unit, "grams": None, "known": False, "approx": False, "hint": label}
    return {"name": name, "qty": qty, "unit": unit, "grams": qty * UNIT_TO_GRAMS[unit], "known": True,
            "approx": unit in VOLUME_UNITS, "hint": text}


CONNECTOR_WORDS = {"and", "with", "of", "plus", "the", "a", "an", "in", "on"}
_SPLIT_RE = re.compile(r"\s*(?:,|\+|&|;|\band\b|\bwith\b|\bplus\b)\s*", flags=re.IGNORECASE)
MAX_PARTS = 6


def split_phrase(text: str) -> list:
    """'2 cups rice and carrots, 1 egg' -> ['2 cups rice', 'carrots', '1 egg'] (at most MAX_PARTS)."""
    return [p.strip() for p in _SPLIT_RE.split(text) if p and p.strip()][:MAX_PARTS]


def covers_query(description: str, name: str) -> bool:
    """True when every content word of the query appears in a food description, so the match explains the whole phrase."""
    desc = description.lower()
    words = [w for w in query_words(name) if w not in CONNECTOR_WORDS]
    return bool(words) and all(re.search(rf"\b{re.escape(w)}\b", desc) for w in words)


PORTION_WORDS = {"cup": ("cup", "cups"), "tbsp": ("tbsp", "tablespoon", "tablespoons"), "tsp": ("tsp", "teaspoon", "teaspoons")}


def _portion_unit_count(p: dict) -> float:
    """How many of its unit a USDA portion covers: its `amount`, else a leading number in the label ('2 cups'), else 1."""
    if p.get("amount"):
        return float(p["amount"])
    m = re.match(r"^(\d+(?:\.\d+)?(?:/\d+)?)\s", p["label"].strip())
    if m:
        n = m.group(1)
        return float(n.split("/")[0]) / float(n.split("/")[1]) if "/" in n else float(n)
    return 1.0


def grams_from_portions(portions: list, unit: str, qty: float):
    """Grams for `qty` of a volume unit using THIS food's USDA portion data, or None when it has no matching portion.
    Prefers a plain portion ('cup', '1 cup') over a qualified one ('cup, sliced')."""
    words = PORTION_WORDS.get(unit)
    if not words:
        return None
    best = None
    for p in portions:
        text = re.sub(r"^\d+(?:\.\d+)?(?:/\d+)?\s*", "", p["label"].lower().strip())
        if text in words:
            tier = 0
        elif any(text.startswith(w + ",") or text.startswith(w + " ") for w in words):
            tier = 1
        else:
            continue
        if best is None or tier < best[0]:
            best = (tier, p)
    if best is None:
        return None
    p = best[1]
    return qty * p["grams"] / _portion_unit_count(p), p["label"]


def clean_food_name(name: str) -> str:
    name = re.sub(r"[^\w\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


def query_words(query: str) -> list:
    return [w.lower() for w in re.split(r"\s+", query.strip()) if w]


# Weight of each scoring term. Every term is a 0/1 indicator except word_hits (a count)
# and brevity (description length / 200), so score = sum(weight * term).
DEFAULT_WEIGHTS = {
    "starts_with": 10.0, "in_first_tokens": 5.0, "word_hits": 1.0,
    "cooked_bonus": 4.0, "raw_penalty": -3.0, "first_mismatch": -8.0,
    "wrong_category": -10.0, "calorie_penalty": -50.0, "brevity": -1.0,
}
# Ablation groups: the cooked/raw heuristic is one idea implemented as two terms.
ABLATION_GROUPS = {
    "starts_with": ["starts_with"], "in_first_tokens": ["in_first_tokens"],
    "cooked_raw": ["cooked_bonus", "raw_penalty"], "first_mismatch": ["first_mismatch"],
    "wrong_category": ["wrong_category"], "calorie_penalty": ["calorie_penalty"], "brevity": ["brevity"],
}


def score_terms(food: dict, q_words: list) -> dict:
    """Unweighted value of every scoring term for one candidate."""
    desc = food.get("description", "").lower()
    tokens = re.split(r"[\s,]+", desc)
    all_present = all(re.search(rf"\b{re.escape(w)}\b", desc) for w in q_words)
    starts_with = 1 if (q_words and tokens and tokens[0] == q_words[0] and all_present) else 0
    n = max(len(q_words) + 1, 3)
    first_token_relevant = bool(tokens and tokens[0] in q_words)
    in_first_tokens = 1 if (first_token_relevant and all(w in tokens[:n] for w in q_words)) else 0
    word_hits = sum(1 for w in q_words if re.search(rf"\b{re.escape(w)}\b", desc))
    is_raw_food = any(rw in " ".join(q_words) for rw in RAW_FOODS)
    user_specified_prep = any(w in q_words for w in ("raw", "cooked", "baked", "grilled", "boiled", "fried", "roasted"))
    if not is_raw_food and not user_specified_prep:
        cooked_bonus = 1 if "cooked" in desc else 0
        raw_penalty = 1 if re.search(r"\braw\b", desc) else 0
    else:
        cooked_bonus = raw_penalty = 0
    first_mismatch = 1 if (tokens and tokens[0] not in q_words) else 0
    wrong_category = 0
    if first_mismatch and q_words:
        segs = [s.strip() for s in desc.split(",")]
        if (len(segs) > 1
                and not any(re.search(rf"\b{re.escape(w)}\b", segs[0]) for w in q_words)
                and any(re.search(rf"\b{re.escape(w)}\b", sg) for w in q_words for sg in segs[1:])):
            wrong_category = 1
    nutrients = {n_["nutrientId"]: n_.get("value", 0) for n_ in food.get("foodNutrients", [])}
    calorie_penalty = 1 if nutrients.get(NUTRIENT_IDS["calories"], 0) > MAX_SANE_CALORIES else 0
    return {
        "starts_with": starts_with, "in_first_tokens": in_first_tokens, "word_hits": word_hits,
        "cooked_bonus": cooked_bonus, "raw_penalty": raw_penalty, "first_mismatch": first_mismatch,
        "wrong_category": wrong_category, "calorie_penalty": calorie_penalty, "brevity": len(desc) / 200,
    }


def _score(food: dict, q_words: list, weights: dict | None = None) -> float:
    w = weights or DEFAULT_WEIGHTS
    terms = score_terms(food, q_words)
    return sum(w[k] * v for k, v in terms.items())


def best_match(foods: list, query: str) -> tuple:
    q_words = query_words(query)
    scored = [(f, _score(f, q_words)) for f in foods]
    return max(scored, key=lambda x: x[1])


def candidate_lists(query: str, parallel: bool = False) -> list:
    """USDA results per data-type call, in API order. Falls back to one untyped call.
    parallel=True issues the typed searches concurrently (the app path); the result is identical.
    If nothing came back and at least one call was refused (after retries), raises ServiceError instead of reporting
    "no results": the food may well exist, the service just did not answer."""
    if parallel:
        with ThreadPoolExecutor(max_workers=len(USDA_DATA_TYPES)) as pool:
            checked = list(pool.map(lambda dt: apis.usda_fetch_checked(query, dt), USDA_DATA_TYPES))
    else:
        checked = [apis.usda_fetch_checked(query, dt) for dt in USDA_DATA_TYPES]
    lists, failed = [c[0] for c in checked], any(c[1] for c in checked)
    if not any(lists):
        foods, failed_untyped = apis.usda_fetch_checked(query, None)
        lists = [foods]
        failed = failed or failed_untyped
        if not foods and failed:
            raise apis.ServiceError("unavailable")
    return lists


def collect_candidates(query: str, parallel: bool = False) -> list:
    """All USDA candidates the app considers, in API order."""
    return [f for lst in candidate_lists(query, parallel) for f in lst]


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


def ranked_candidates(query: str, k: int = 5, parallel: bool = False) -> list:
    """Top-k USDA candidates as (food, score), best first (stable on ties, like best_match)."""
    foods = collect_candidates(query, parallel)
    q_words = query_words(query)
    scored = sorted(((f, _score(f, q_words)) for f in foods), key=lambda x: -x[1])
    return scored[:k]


def search_food(query: str, parallel: bool = False):
    foods = collect_candidates(query, parallel)
    if not foods:
        return None
    food, match_score = best_match(foods, query)
    return to_result(food, match_score, query)
