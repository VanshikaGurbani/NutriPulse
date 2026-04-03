import re
import streamlit as st
import requests
import plotly.graph_objects as go
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("USDA_API_KEY")
API_BASE = "https://api.nal.usda.gov/fdc/v1"

NUTRIENT_IDS = {
    "calories": 1008,
    "protein": 1003,
    "fat": 1004,
    "carbs": 1005,
    "fiber": 1079,
}

# Foundation foods sometimes store calories under ID 2047 (Atwater specific
# factors) instead of 1008 — we check both and use whichever is non-zero.
CALORIE_IDS = [1008, 2047]

# Foods that are almost always consumed raw — skip the "cooked" scoring bonus
RAW_FOODS = {
    "apple", "banana", "orange", "grape", "strawberr", "blueberr", "mango",
    "watermelon", "pineapple", "peach", "pear", "cherry", "kiwi", "melon",
    "avocado", "tomato", "cucumber", "lettuce", "spinach", "kale",
    "carrot", "celery", "oil", "butter", "honey", "milk", "yogurt",
    "cheese", "juice", "nuts", "almond", "walnut", "cashew", "peanut",
}

UNIT_TO_GRAMS = {
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.35,
    "lb": 453.6,
    "cup": 240.0,
    "tbsp": 15.0,
    "tsp": 5.0,
    "ml": 1.0,
    "piece": 100.0,
    "slice": 30.0,
}

UNITS = list(UNIT_TO_GRAMS.keys())

# Anything above this is physically impossible per 100g (pure fat ≈ 900 kcal)
MAX_SANE_CALORIES = 950

# Minimum score for a result to be considered a confident match
LOW_CONFIDENCE_THRESHOLD = 5

# Source badge labels shown in the UI
SOURCE_BADGES = {
    "Foundation": "🟢 Foundation",
    "SR Legacy": "🔵 SR Legacy",
    "Survey (FNDDS)": "🔵 Survey (FNDDS)",
    "Branded": "🟡 Branded",
}


# ── Input parsing ─────────────────────────────────────────────────────────────

def parse_serving(text: str):
    """
    Extract leading quantity + unit from food input text.
    Returns (quantity, unit, food_name).
      "3.5 cups of oatmeal"  -> (3.5, "cup", "oatmeal")
      "1/2 cup rice"         -> (0.5, "cup", "rice")
      "1.5 oz chicken"       -> (1.5, "oz", "chicken")
      "oatmeal"              -> (100.0, "g", "oatmeal")  # sensible default
    """
    text = text.strip()
    match = re.match(
        r"^(\d+(?:\.\d+)?(?:/\d+)?)\s*"          # quantity: int, decimal, or fraction
        r"(cups?|tbsps?|tsps?|fl\.?\s*oz|oz"       # units
        r"|kg|lbs?|g|ml|l|pieces?|slices?)?\s*"
        r"(?:of\s+)?(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return 100.0, "g", _clean_food_name(text)

    qty_str, unit_str, food = match.groups()

    # Handle fractions like "1/2"
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

    return qty, unit, _clean_food_name(food)


def _clean_food_name(name: str) -> str:
    """Strip punctuation, collapse spaces — keeps the USDA query clean."""
    name = re.sub(r"[^\w\s]", "", name)   # remove punctuation
    name = re.sub(r"\s+", " ", name)       # collapse multiple spaces
    return name.strip()


# ── USDA matching ─────────────────────────────────────────────────────────────

def _score(food: dict, q_words: list) -> float:
    """
    Score a USDA food result for relevance to the query.

      +10  description's first token == first query word  (strong direct match)
      +5   all query words appear in the opening tokens   (handles USDA "Rice, brown" style)
      +1   each query word found as a whole word anywhere (word-boundary safe)
      +4   description contains "cooked"                  (users log what they ate)
      -3   description contains "raw"                     (penalise uncooked entries)
      -5   description's first token is NOT any query word (off-topic leading word)
      -50  calories > 900 kcal/100g                       (branded data error)
      -len slight penalty for long descriptions
    """
    desc = food.get("description", "").lower()
    tokens = re.split(r"[\s,]+", desc)

    # Strong bonus: opens with the first query word AND all query words are present
    # (guards against "Olive garden dressing" beating "Oil, olive" for "olive oil")
    all_present = all(re.search(rf"\b{re.escape(w)}\b", desc) for w in q_words)
    starts_with = 10 if (q_words and tokens and tokens[0] == q_words[0] and all_present) else 0

    # USDA often inverts names: "Rice, brown" for "brown rice" — reward that
    n = max(len(q_words) + 1, 3)
    in_first_tokens = 5 if all(w in tokens[:n] for w in q_words) else 0

    # Whole-word matches only — "corn" must NOT score on "popcorn"
    word_hits = sum(1 for w in q_words if re.search(rf"\b{re.escape(w)}\b", desc))

    # Prefer cooked results — users log food they have eaten, not raw ingredients.
    # Skip this adjustment for foods that are naturally consumed raw (fruits, oils, etc.)
    is_raw_food = any(rw in " ".join(q_words) for rw in RAW_FOODS)
    user_specified_prep = any(w in q_words for w in ("raw", "cooked", "baked", "grilled", "boiled", "fried", "roasted"))
    if not is_raw_food and not user_specified_prep:
        cooked_bonus = 4 if "cooked" in desc else 0
        raw_penalty  = -3 if re.search(r"\braw\b", desc) else 0
    else:
        cooked_bonus = 0
        raw_penalty  = 0

    # Penalise if the description opens with a word unrelated to the query
    # e.g. "Flour, rice, brown" for query "brown rice" → first token "flour" ∉ q_words
    first_mismatch = -5 if (tokens and tokens[0] not in q_words) else 0

    # Penalise physically impossible calorie values (branded product data errors)
    nutrients = {n_["nutrientId"]: n_.get("value", 0) for n_ in food.get("foodNutrients", [])}
    calorie_penalty = -50 if nutrients.get(NUTRIENT_IDS["calories"], 0) > MAX_SANE_CALORIES else 0

    brevity = -len(desc) / 200
    return (starts_with + in_first_tokens + word_hits + cooked_bonus + raw_penalty
            + first_mismatch + calorie_penalty + brevity)


def best_match(foods: list, query: str) -> tuple:
    """Pick the highest-scoring food and return (food_dict, score)."""
    q_words = [w.lower() for w in re.split(r"\s+", query.strip()) if w]
    scored = [(f, _score(f, q_words)) for f in foods]
    return max(scored, key=lambda x: x[1])


def _fetch(query: str, data_type: str | None) -> list:
    """
    Single USDA API call for one data type (or all types if data_type is None).
    Returns list of food dicts; returns [] on HTTP errors so callers can continue.
    Each dataType is sent in its own request — the USDA API does NOT accept
    comma-separated values and rejects them with a 400.
    """
    params = {"query": query, "api_key": API_KEY, "pageSize": 5}
    if data_type:
        params["dataType"] = data_type
    try:
        resp = requests.get(f"{API_BASE}/foods/search", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("foods", [])
    except requests.HTTPError:
        return []


def search_food(query: str):
    """
    Search USDA FoodData Central using a tiered, multi-source strategy.

    Strategy:
      Tier 1  Foundation + Survey (FNDDS) queried SEPARATELY — avoids the
              400 error that occurs when combining them as one comma-separated
              dataType value. Candidates from both are pooled so best_match
              can compare across sources (e.g. Foundation's "Flour, rice, brown"
              loses to Survey's "Rice, brown" for the query "brown rice").
      Tier 2  SR Legacy — added if Tier 1 returned fewer than 3 candidates.
      Tier 3  No filter — last resort; may include Branded products.
    """
    all_foods: list = []

    # Tier 1 — query each high-quality source separately and pool results
    for dt in ["Foundation", "Survey (FNDDS)"]:
        all_foods.extend(_fetch(query, dt))

    # Tier 2 — widen the pool if Tier 1 gave too few candidates
    if len(all_foods) < 3:
        all_foods.extend(_fetch(query, "SR Legacy"))

    # Tier 3 — no-filter fallback (includes Branded)
    if not all_foods:
        all_foods = _fetch(query, None)
        if not all_foods:
            # Final attempt: raise so the UI shows the real error message
            resp = requests.get(
                f"{API_BASE}/foods/search",
                params={"query": query, "api_key": API_KEY, "pageSize": 5},
                timeout=10,
            )
            resp.raise_for_status()
            return None

    food, match_score = best_match(all_foods, query)
    nutrients = {n["nutrientId"]: n.get("value", 0)
                 for n in food.get("foodNutrients", [])}

    # Foundation foods may store calories under ID 2047 instead of 1008
    calories = round(
        next((nutrients[cid] for cid in CALORIE_IDS if nutrients.get(cid, 0) > 0), 0),
        1
    )

    raw_type = food.get("dataType", "Unknown")
    source_label = SOURCE_BADGES.get(raw_type, f"📄 {raw_type}")

    q_words = [w.lower() for w in re.split(r"\s+", query.strip()) if w]
    desc_lower = food.get("description", "").lower()
    any_word_found = any(re.search(rf"\b{re.escape(w)}\b", desc_lower) for w in q_words)
    low_confidence = match_score < LOW_CONFIDENCE_THRESHOLD or not any_word_found

    return {
        "description": food.get("description", query),
        "calories": calories,
        "protein": round(nutrients.get(NUTRIENT_IDS["protein"], 0), 1),
        "fat": round(nutrients.get(NUTRIENT_IDS["fat"], 0), 1),
        "carbs": round(nutrients.get(NUTRIENT_IDS["carbs"], 0), 1),
        "fiber": round(nutrients.get(NUTRIENT_IDS["fiber"], 0), 1),
        "source": source_label,
        "suspicious_calories": calories > MAX_SANE_CALORIES,
        "low_confidence": low_confidence,
    }


# ── Session state init ────────────────────────────────────────────────────────
if "food_log" not in st.session_state:
    st.session_state.food_log = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_input" not in st.session_state:
    st.session_state.last_input = None
if "serving_qty" not in st.session_state:
    st.session_state.serving_qty = 100.0
if "serving_unit" not in st.session_state:
    st.session_state.serving_unit = "g"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Nutrition Tracker", page_icon="🥗", layout="centered")
st.title("🥗 Nutrition Tracker")
st.caption("Powered by USDA FoodData Central")

# ── API key check ─────────────────────────────────────────────────────────────
if not API_KEY:
    st.error(
        "**USDA API key not found.**\n\n"
        "Create a `.env` file in this folder with:\n"
        "```\nUSDA_API_KEY=your_key_here\n```\n"
        "Get a free key at https://fdc.nal.usda.gov/api-guide.html"
    )
    st.stop()

# ── Food Search ───────────────────────────────────────────────────────────────
st.header("Food Search")
food_input = st.text_input(
    "Enter a food (e.g. '2 cups oatmeal', '1.5 oz chicken', '3 tbsp peanut butter')",
    placeholder="2 cups oatmeal",
)

if st.button("Analyze Food", type="primary"):
    if not food_input.strip():
        st.warning("Please enter a food item first.")
    else:
        qty, unit, food_name = parse_serving(food_input)
        with st.spinner(f"Looking up '{food_name}'…"):
            try:
                result = search_food(food_name)
                if result is None:
                    st.warning(
                        "No results found — try a simpler food name like "
                        "'brown rice' or 'chicken breast'"
                    )
                    st.session_state.last_result = None
                else:
                    st.session_state.last_result = result
                    st.session_state.last_input = food_input
                    st.session_state.serving_qty = qty
                    st.session_state.serving_unit = unit
            except Exception as e:
                st.error(f"API error: {e}")
                st.session_state.last_result = None

# ── Nutrition card ────────────────────────────────────────────────────────────
if st.session_state.last_result:
    r = st.session_state.last_result
    st.subheader(f"Results for: {st.session_state.last_input}")

    # ── Confidence / data quality warnings ───────────────────────────────────
    if r.get("low_confidence"):
        st.warning(
            "⚠️ **Low confidence match** — the USDA result may not match "
            "your food exactly. Try rephrasing (e.g. 'rolled oats' instead of 'oatmeal')."
        )
    if r.get("suspicious_calories"):
        st.error(
            "🚨 **Unusual calorie value detected** — this result may be from a "
            "branded product with incorrect per-100g data. The numbers may not "
            "be accurate."
        )

    # ── Serving size controls ─────────────────────────────────────────────────
    col_qty, col_unit = st.columns([1, 2])
    serving_qty = col_qty.number_input(
        "Amount",
        min_value=0.1,
        max_value=9999.0,
        value=float(st.session_state.serving_qty),
        step=0.5,
    )
    unit_index = (
        UNITS.index(st.session_state.serving_unit)
        if st.session_state.serving_unit in UNITS
        else 0
    )
    serving_unit = col_unit.selectbox("Unit", UNITS, index=unit_index)

    st.session_state.serving_qty = serving_qty
    st.session_state.serving_unit = serving_unit

    grams = serving_qty * UNIT_TO_GRAMS.get(serving_unit, 1.0)
    factor = grams / 100

    # Source badge + serving info
    st.caption(
        f"USDA match: *{r['description']}* · **{grams:.0f} g** serving "
        f"· {r.get('source', '')}"
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Calories", f"{round(r['calories'] * factor, 1)} kcal")
    col2.metric("Carbs", f"{round(r['carbs'] * factor, 1)} g")
    col3.metric("Protein", f"{round(r['protein'] * factor, 1)} g")
    col4.metric("Fat", f"{round(r['fat'] * factor, 1)} g")
    st.metric("Fiber", f"{round(r['fiber'] * factor, 1)} g", label_visibility="visible")

    if st.button("➕ Add to Today's Log"):
        entry = {
            "Food": f"{st.session_state.last_input} ({grams:.0f}g)",
            "Calories (kcal)": round(r["calories"] * factor, 1),
            "Carbs (g)": round(r["carbs"] * factor, 1),
            "Protein (g)": round(r["protein"] * factor, 1),
            "Fat (g)": round(r["fat"] * factor, 1),
            "Fiber (g)": round(r["fiber"] * factor, 1),
        }
        st.session_state.food_log.append(entry)
        st.success(f"Added '{st.session_state.last_input}' ({grams:.0f}g) to your log!")

st.divider()

# ── Daily Food Log ────────────────────────────────────────────────────────────
st.header("Today's Food Log")

if st.session_state.food_log:
    import pandas as pd

    df = pd.DataFrame(st.session_state.food_log)
    st.dataframe(df, use_container_width=True, hide_index=True)

    if st.button("🗑️ Clear Log"):
        st.session_state.food_log = []
        st.session_state.last_result = None
        st.rerun()

    # ── Running totals ────────────────────────────────────────────────────────
    st.subheader("Daily Totals")
    total_cal = round(df["Calories (kcal)"].sum(), 1)
    total_carbs = round(df["Carbs (g)"].sum(), 1)
    total_protein = round(df["Protein (g)"].sum(), 1)
    total_fat = round(df["Fat (g)"].sum(), 1)

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Total Calories", f"{total_cal} kcal")
    t2.metric("Total Carbs", f"{total_carbs} g")
    t3.metric("Total Protein", f"{total_protein} g")
    t4.metric("Total Fat", f"{total_fat} g")

    # ── Macro breakdown chart ─────────────────────────────────────────────────
    st.subheader("Macro Breakdown")
    carb_cal = total_carbs * 4
    protein_cal = total_protein * 4
    fat_cal = total_fat * 9
    total_macro_cal = carb_cal + protein_cal + fat_cal

    if total_macro_cal > 0:
        carb_pct = round(carb_cal / total_macro_cal * 100, 1)
        protein_pct = round(protein_cal / total_macro_cal * 100, 1)
        fat_pct = round(100 - carb_pct - protein_pct, 1)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Carbs",
            x=[carb_pct],
            y=["Macros"],
            orientation="h",
            marker_color="#4C72B0",
            text=f"Carbs {carb_pct}%",
            textposition="inside",
            insidetextanchor="middle",
        ))
        fig.add_trace(go.Bar(
            name="Protein",
            x=[protein_pct],
            y=["Macros"],
            orientation="h",
            marker_color="#55A868",
            text=f"Protein {protein_pct}%",
            textposition="inside",
            insidetextanchor="middle",
        ))
        fig.add_trace(go.Bar(
            name="Fat",
            x=[fat_pct],
            y=["Macros"],
            orientation="h",
            marker_color="#DD8452",
            text=f"Fat {fat_pct}%",
            textposition="inside",
            insidetextanchor="middle",
        ))
        fig.update_layout(
            barmode="stack",
            xaxis=dict(title="% of Calories", range=[0, 100]),
            yaxis=dict(showticklabels=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=180,
            margin=dict(l=10, r=10, t=40, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Your log is empty. Search for a food above and add it to your log.")
