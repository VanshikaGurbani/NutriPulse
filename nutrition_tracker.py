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
      +5   first token is a query word AND all query words in opening tokens
           (handles USDA "Rice, brown" style — but NOT "Bread, oatmeal")
      +1   each query word found as a whole word anywhere (word-boundary safe)
      +4   description contains "cooked"                  (users log what they ate)
      -3   description contains "raw"                     (penalise uncooked entries)
      -8   description's first token is NOT any query word (off-topic leading word)
      -10  wrong-category: first token off-topic AND a query word only appears
           after a comma (e.g. "Bread, oatmeal" for query "oatmeal")
      -50  calories > 900 kcal/100g                       (branded data error)
      -len slight penalty for long descriptions
    """
    desc = food.get("description", "").lower()
    tokens = re.split(r"[\s,]+", desc)

    # Strong bonus: opens with the first query word AND all query words are present
    all_present = all(re.search(rf"\b{re.escape(w)}\b", desc) for w in q_words)
    starts_with = 10 if (q_words and tokens and tokens[0] == q_words[0] and all_present) else 0

    # USDA often inverts names: "Rice, brown" → "brown rice" — reward that.
    # Guard: only fires when the first token is itself a query word, so "Bread, oatmeal"
    # does NOT get this bonus for query "oatmeal" (first token "bread" ∉ q_words).
    n = max(len(q_words) + 1, 3)
    first_token_relevant = bool(tokens and tokens[0] in q_words)
    in_first_tokens = 5 if (first_token_relevant and all(w in tokens[:n] for w in q_words)) else 0

    # Whole-word matches only — "corn" must NOT score on "popcorn"
    word_hits = sum(1 for w in q_words if re.search(rf"\b{re.escape(w)}\b", desc))

    # Prefer cooked results — users log food they have eaten, not raw ingredients.
    is_raw_food = any(rw in " ".join(q_words) for rw in RAW_FOODS)
    user_specified_prep = any(w in q_words for w in ("raw", "cooked", "baked", "grilled", "boiled", "fried", "roasted"))
    if not is_raw_food and not user_specified_prep:
        cooked_bonus = 4 if "cooked" in desc else 0
        raw_penalty  = -3 if re.search(r"\braw\b", desc) else 0
    else:
        cooked_bonus = 0
        raw_penalty  = 0

    # Penalise if the description opens with a word unrelated to the query
    first_mismatch = -8 if (tokens and tokens[0] not in q_words) else 0

    # Extra penalty: wrong-category pattern — "Bread, oatmeal" for query "oatmeal"
    # means oatmeal-flavoured bread, not oatmeal.  Detected when:
    #   • first token is off-topic (not a query word)
    #   • a query word appears only in a secondary comma-segment
    wrong_category = 0
    if first_mismatch and q_words:
        segments = [s.strip() for s in desc.split(",")]
        query_in_secondary = (
            len(segments) > 1
            and not any(re.search(rf"\b{re.escape(w)}\b", segments[0]) for w in q_words)
            and any(
                re.search(rf"\b{re.escape(w)}\b", seg)
                for w in q_words
                for seg in segments[1:]
            )
        )
        wrong_category = -10 if query_in_secondary else 0

    # Penalise physically impossible calorie values
    nutrients = {n_["nutrientId"]: n_.get("value", 0) for n_ in food.get("foodNutrients", [])}
    calorie_penalty = -50 if nutrients.get(NUTRIENT_IDS["calories"], 0) > MAX_SANE_CALORIES else 0

    brevity = -len(desc) / 200
    return (starts_with + in_first_tokens + word_hits + cooked_bonus + raw_penalty
            + first_mismatch + wrong_category + calorie_penalty + brevity)


def best_match(foods: list, query: str) -> tuple:
    """Pick the highest-scoring food and return (food_dict, score)."""
    q_words = [w.lower() for w in re.split(r"\s+", query.strip()) if w]
    scored = [(f, _score(f, q_words)) for f in foods]
    return max(scored, key=lambda x: x[1])


def _fetch(query: str, data_type: str | None) -> list:
    """Single USDA API call for one data type."""
    params = {"query": query, "api_key": API_KEY, "pageSize": 8}
    if data_type:
        params["dataType"] = data_type
    try:
        resp = requests.get(f"{API_BASE}/foods/search", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("foods", [])
    except requests.HTTPError:
        return []


def search_food(query: str):
    """Search USDA FoodData Central using a multi-source strategy.

    All three high-quality sources are always queried so the scorer always
    has a rich, diverse candidate pool to choose from regardless of which
    individual source happens to return fewer results.
    """
    all_foods: list = []

    # Always query all three trusted sources — don't gate SR Legacy behind a
    # threshold, because Foundation/Survey may return off-topic results that
    # would suppress SR Legacy even when SR Legacy has the best match.
    for dt in ["Foundation", "Survey (FNDDS)", "SR Legacy"]:
        all_foods.extend(_fetch(query, dt))

    if not all_foods:
        all_foods = _fetch(query, None)
        if not all_foods:
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


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="NutriPulse", page_icon="🥗", layout="centered")

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Google Font ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── Page background ── */
.stApp {
    background: #f0f5f0;
}

/* ── Hero banner ── */
.hero-banner {
    background: linear-gradient(135deg, #2d6a4f 0%, #40916c 50%, #52b788 100%);
    border-radius: 16px;
    padding: 32px 36px;
    margin-bottom: 28px;
    color: white;
    box-shadow: 0 8px 32px rgba(45, 106, 79, 0.3);
}
.hero-banner h1 {
    font-size: 2.4rem;
    font-weight: 700;
    margin: 0 0 6px 0;
    letter-spacing: -0.5px;
}
.hero-banner p {
    font-size: 1rem;
    opacity: 0.88;
    margin: 0;
}

/* ── Section cards (native st.container border) ── */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: white !important;
    border-radius: 14px !important;
    border: 1px solid #daeada !important;
    box-shadow: 0 2px 14px rgba(0,0,0,0.07) !important;
    padding: 6px 4px !important;
    margin-bottom: 8px !important;
}

.section-title {
    font-size: 1.1rem;
    font-weight: 650;
    color: #2d6a4f;
    margin: 0 0 12px 0;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* ── Macro metric cards ── */
.macro-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    margin: 16px 0;
}
.macro-card {
    border-radius: 12px;
    padding: 14px 10px;
    text-align: center;
    transition: transform 0.15s ease;
}
.macro-card:hover { transform: translateY(-2px); }
.macro-card .macro-value {
    font-size: 1.4rem;
    font-weight: 700;
    line-height: 1.2;
}
.macro-card .macro-label {
    font-size: 0.72rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-top: 4px;
    opacity: 0.8;
}

.macro-calories { background: #fff3e0; color: #e65100; }
.macro-carbs    { background: #fff8e1; color: #f57f17; }
.macro-protein  { background: #e3f2fd; color: #1565c0; }
.macro-fat      { background: #f3e5f5; color: #6a1b9a; }
.macro-fiber    { background: #e8f5e9; color: #2e7d32; }

/* ── Food log table ── */
.food-log-empty {
    text-align: center;
    padding: 36px 0;
    color: #888;
    font-size: 0.95rem;
}
.food-log-empty .empty-icon {
    font-size: 2.5rem;
    display: block;
    margin-bottom: 8px;
}

/* ── Source pill ── */
.source-pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    background: #e8f5e9;
    color: #2d6a4f;
    margin-left: 6px;
}

/* ── Result food name ── */
.result-food-name {
    font-size: 1rem;
    font-weight: 600;
    color: #1a2e1a;
    margin-bottom: 4px;
}
.result-serving-info {
    font-size: 0.82rem;
    color: #666;
    margin-bottom: 16px;
}

/* ── Daily totals strip ── */
.totals-strip {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    background: linear-gradient(135deg, #2d6a4f, #40916c);
    border-radius: 12px;
    padding: 18px 22px;
    margin: 16px 0;
    color: white;
}
.total-item {
    flex: 1;
    min-width: 90px;
    text-align: center;
}
.total-item .t-val {
    font-size: 1.35rem;
    font-weight: 700;
    line-height: 1.2;
}
.total-item .t-lbl {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    opacity: 0.82;
    margin-top: 3px;
}

/* ── Streamlit overrides ── */
div[data-testid="stTextInput"] input {
    border-radius: 10px !important;
    border: 1.5px solid #b7d5c0 !important;
    padding: 10px 14px !important;
    font-size: 0.95rem !important;
}
div[data-testid="stTextInput"] input:focus {
    border-color: #40916c !important;
    box-shadow: 0 0 0 3px rgba(64,145,108,0.15) !important;
}

/* Primary button */
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #2d6a4f, #40916c) !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 10px 24px !important;
    font-weight: 600 !important;
    letter-spacing: 0.3px !important;
    box-shadow: 0 4px 12px rgba(45,106,79,0.3) !important;
    transition: all 0.2s !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 18px rgba(45,106,79,0.4) !important;
}

/* Secondary button */
div[data-testid="stButton"] > button[kind="secondary"] {
    border-radius: 10px !important;
    border: 1.5px solid #b7d5c0 !important;
    color: #2d6a4f !important;
    font-weight: 500 !important;
}

/* Number input & selectbox */
div[data-testid="stNumberInput"] input,
div[data-testid="stSelectbox"] > div {
    border-radius: 10px !important;
}

/* Divider */
hr {
    border-color: #dce8dc !important;
    margin: 24px 0 !important;
}

/* Success / warning / error messages */
div[data-testid="stAlert"] {
    border-radius: 10px !important;
}

/* Streamlit default metric — hide (we use custom cards) */
div[data-testid="metric-container"] {
    background: white;
    border-radius: 12px;
    padding: 12px 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    border: 1px solid #e8f0e8;
}

/* Dataframe */
div[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #e0ece0 !important;
}

/* ── Calorie progress bar ── */
.goal-bar-wrap {
    background: #e8f0e8;
    border-radius: 99px;
    height: 18px;
    overflow: hidden;
    margin: 10px 0 6px;
}
.goal-bar-fill {
    height: 100%;
    border-radius: 99px;
    transition: width 0.4s ease, background 0.4s ease;
}
.goal-bar-fill.green  { background: linear-gradient(90deg, #52b788, #2d6a4f); }
.goal-bar-fill.yellow { background: linear-gradient(90deg, #f9a825, #f57f17); }
.goal-bar-fill.red    { background: linear-gradient(90deg, #ef5350, #b71c1c); }

.goal-stats {
    display: flex;
    justify-content: space-between;
    font-size: 0.82rem;
    color: #555;
    margin-top: 2px;
}
.goal-stats .consumed { font-weight: 700; font-size: 1rem; color: #1a2e1a; }
.goal-stats .remaining-green  { color: #2d6a4f; font-weight: 600; }
.goal-stats .remaining-yellow { color: #f57f17; font-weight: 600; }
.goal-stats .remaining-red    { color: #c62828; font-weight: 600; }

/* ── Meal section headers ── */
.meal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-radius: 10px;
    padding: 8px 14px;
    margin: 14px 0 6px;
    font-weight: 600;
    font-size: 0.92rem;
}
.meal-header .meal-kcal {
    font-size: 0.82rem;
    opacity: 0.85;
    font-weight: 500;
}

/* ── Meal radio pill selector ── */
div[data-testid="stRadio"] > div {
    gap: 8px !important;
}
div[data-testid="stRadio"] label {
    border: 1.5px solid #b7d5c0 !important;
    border-radius: 20px !important;
    padding: 4px 14px !important;
    font-size: 0.85rem !important;
    cursor: pointer;
    transition: all 0.15s;
}
div[data-testid="stRadio"] label:hover {
    background: #e8f5e9 !important;
}
</style>
""", unsafe_allow_html=True)


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
if "calorie_goal" not in st.session_state:
    st.session_state.calorie_goal = 2000
if "selected_meal" not in st.session_state:
    st.session_state.selected_meal = "🌅 Breakfast"
if "exercise_log" not in st.session_state:
    st.session_state.exercise_log = []

MEALS = ["🌅 Breakfast", "☀️ Lunch", "🌙 Dinner", "🍎 Snack"]

# Approximate kcal burned per minute for a ~70 kg person
EXERCISES = {
    "🏃 Running":            10,
    "🚶 Walking":             4,
    "🚴 Cycling":             8,
    "🏊 Swimming":            9,
    "💪 Strength Training":   5,
    "🔥 HIIT":               12,
    "🧘 Yoga / Stretching":   3,
    "⚽ Sports / Games":       7,
    "🪜 Stair Climbing":       9,
    "💃 Dancing":              5,
}
MEAL_COLORS = {
    "🌅 Breakfast": "#fff3e0",
    "☀️ Lunch":     "#e3f2fd",
    "🌙 Dinner":    "#f3e5f5",
    "🍎 Snack":     "#e8f5e9",
}
MEAL_TEXT_COLORS = {
    "🌅 Breakfast": "#e65100",
    "☀️ Lunch":     "#1565c0",
    "🌙 Dinner":    "#6a1b9a",
    "🍎 Snack":     "#2e7d32",
}


# ── Hero Banner ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-banner">
    <h1>🥗 NutriPulse</h1>
    <p>Track what you eat · Powered by USDA FoodData Central</p>
</div>
""", unsafe_allow_html=True)

# ── API key check ─────────────────────────────────────────────────────────────
if not API_KEY:
    st.error(
        "**USDA API key not found.**\n\n"
        "Create a `.env` file in this folder with:\n"
        "```\nUSDA_API_KEY=your_key_here\n```\n"
        "Get a free key at https://fdc.nal.usda.gov/api-guide.html"
    )
    st.stop()

# ── Daily Calorie Goal Card ───────────────────────────────────────────────────
with st.container(border=True):
    col_goal_title, col_goal_input = st.columns([3, 1])
    with col_goal_title:
        st.markdown('<p class="section-title">🎯 Daily Calorie Goal</p>', unsafe_allow_html=True)
    with col_goal_input:
        calorie_goal = st.number_input(
            "Goal (kcal)",
            min_value=500,
            max_value=5000,
            value=st.session_state.calorie_goal,
            step=50,
            label_visibility="collapsed",
        )
        st.session_state.calorie_goal = calorie_goal

    # Calculate consumed from food log and burned from exercise log
    consumed = round(sum(e["Calories (kcal)"] for e in st.session_state.food_log), 1)
    burned   = round(sum(e["Calories Burned"] for e in st.session_state.exercise_log), 1)
    net      = round(consumed - burned, 1)
    goal     = st.session_state.calorie_goal
    pct      = min(net / goal, 1.0) if goal > 0 else 0
    pct_display = min(round(pct * 100, 1), 100)

    # Pick colour tier based on net calories
    if pct < 0.75:
        bar_class = "green"
        remaining_class = "remaining-green"
        status_icon = "✅"
        status_msg = f"{goal - net:.0f} kcal remaining"
    elif pct < 1.0:
        bar_class = "yellow"
        remaining_class = "remaining-yellow"
        status_icon = "⚡"
        status_msg = f"{goal - net:.0f} kcal remaining — almost there!"
    else:
        bar_class = "red"
        remaining_class = "remaining-red"
        status_icon = "🔴"
        status_msg = f"{net - goal:.0f} kcal over goal"

    burned_note = f" · 🔥 {burned} burned" if burned > 0 else ""
    st.markdown(f"""
    <div class="goal-bar-wrap">
        <div class="goal-bar-fill {bar_class}" style="width:{pct_display}%"></div>
    </div>
    <div class="goal-stats">
        <span>{status_icon} <span class="{remaining_class}">{status_msg}</span></span>
        <span><span class="consumed">{net}</span> / {goal} kcal net&nbsp;<span style="color:#888;font-size:0.78rem">({consumed} eaten{burned_note})</span></span>
    </div>
    """, unsafe_allow_html=True)

# ── Food Search Card ──────────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown('<p class="section-title">🔍 Search a Food</p>', unsafe_allow_html=True)

    food_input = st.text_input(
        "Food item",
        placeholder="e.g. 2 cups oatmeal · 1.5 oz chicken · 3 tbsp peanut butter",
        label_visibility="collapsed",
    )

    col_btn, col_hint = st.columns([1, 3])
    with col_btn:
        analyze_clicked = st.button("Analyze Food", type="primary", use_container_width=True)
    with col_hint:
        st.markdown(
            "<span style='color:#888;font-size:0.82rem;line-height:2.6'>Tip: include quantity & unit — e.g. <em>\"2 cups brown rice\"</em></span>",
            unsafe_allow_html=True,
        )

    if analyze_clicked:
        if not food_input.strip():
            st.warning("Please enter a food item first.")
        else:
            qty, unit, food_name = parse_serving(food_input)
            with st.spinner(f"Looking up '{food_name}'…"):
                try:
                    result = search_food(food_name)
                    if result is None:
                        st.warning(
                            "No results found — try a simpler name like 'brown rice' or 'chicken breast'."
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

# ── Nutrition Results Card ────────────────────────────────────────────────────
if st.session_state.last_result:
    r = st.session_state.last_result

    with st.container(border=True):
        st.markdown('<p class="section-title">📊 Nutrition Info</p>', unsafe_allow_html=True)

        # Confidence / data quality warnings
        if r.get("low_confidence"):
            st.warning(
                "⚠️ **Low confidence match** — the USDA result may not be exact. "
                "Try rephrasing, e.g. *'rolled oats'* instead of *'oatmeal'*."
            )
        if r.get("suspicious_calories"):
            st.error(
                "🚨 **Unusual calorie value** — this may be branded product data. Numbers may not be accurate."
            )

        # Serving size controls
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

        # Food name + source badge + serving info
        st.markdown(
            f'<div class="result-food-name">{r["description"]}'
            f'<span class="source-pill">{r.get("source", "")}</span></div>'
            f'<div class="result-serving-info">Serving: {serving_qty:g} {serving_unit} = {grams:.0f} g</div>',
            unsafe_allow_html=True,
        )

        # Macro cards
        cal   = round(r["calories"] * factor, 1)
        carbs = round(r["carbs"]    * factor, 1)
        prot  = round(r["protein"]  * factor, 1)
        fat   = round(r["fat"]      * factor, 1)
        fiber = round(r["fiber"]    * factor, 1)

        st.markdown(f"""
        <div class="macro-grid">
            <div class="macro-card macro-calories">
                <div class="macro-value">{cal}</div>
                <div class="macro-label">kcal</div>
            </div>
            <div class="macro-card macro-carbs">
                <div class="macro-value">{carbs}g</div>
                <div class="macro-label">Carbs</div>
            </div>
            <div class="macro-card macro-protein">
                <div class="macro-value">{prot}g</div>
                <div class="macro-label">Protein</div>
            </div>
            <div class="macro-card macro-fat">
                <div class="macro-value">{fat}g</div>
                <div class="macro-label">Fat</div>
            </div>
            <div class="macro-card macro-fiber">
                <div class="macro-value">{fiber}g</div>
                <div class="macro-label">Fiber</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Macro breakdown chart for this food item
        item_carb_cal = carbs * 4
        item_prot_cal = prot  * 4
        item_fat_cal  = fat   * 9
        item_total    = item_carb_cal + item_prot_cal + item_fat_cal
        if item_total > 0:
            cp = round(item_carb_cal / item_total * 100, 1)
            pp = round(item_prot_cal / item_total * 100, 1)
            fp = round(100 - cp - pp, 1)
            fig_item = go.Figure()
            for name, val, color in [
                ("Carbs",   cp, "#f9a825"),
                ("Protein", pp, "#1976d2"),
                ("Fat",     fp, "#8e24aa"),
            ]:
                fig_item.add_trace(go.Bar(
                    name=name, x=[val], y=[""], orientation="h",
                    marker_color=color,
                    text=f"{name} {val}%", textposition="inside",
                    insidetextanchor="middle",
                    textfont=dict(color="white", size=12, family="Inter"),
                ))
            fig_item.update_layout(
                barmode="stack",
                xaxis=dict(range=[0, 100], visible=False),
                yaxis=dict(showticklabels=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.1,
                            xanchor="right", x=1,
                            font=dict(family="Inter", size=11)),
                height=80, margin=dict(l=0, r=0, t=28, b=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter"),
            )
            st.plotly_chart(fig_item, use_container_width=True)

        # Meal selector
        meal_idx = MEALS.index(st.session_state.selected_meal) if st.session_state.selected_meal in MEALS else 0
        selected_meal = st.radio(
            "Add to meal",
            MEALS,
            index=meal_idx,
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state.selected_meal = selected_meal

        if st.button("➕ Add to Today's Log", type="primary"):
            entry = {
                "Meal": selected_meal,
                "Food": f"{st.session_state.last_input} ({grams:.0f}g)",
                "Calories (kcal)": cal,
                "Carbs (g)": carbs,
                "Protein (g)": prot,
                "Fat (g)": fat,
                "Fiber (g)": fiber,
            }
            st.session_state.food_log.append(entry)
            st.success(f"✅ Added **{st.session_state.last_input}** ({grams:.0f}g) to **{selected_meal}**!")

# ── Daily Food Log Card ───────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown('<p class="section-title">📋 Today\'s Food Log</p>', unsafe_allow_html=True)

    if st.session_state.food_log:
        import pandas as pd

        df = pd.DataFrame(st.session_state.food_log)

        # ── Grouped by meal ───────────────────────────────────────────────────
        DISPLAY_COLS = ["Food", "Calories (kcal)", "Carbs (g)", "Protein (g)", "Fat (g)", "Fiber (g)"]
        for meal in MEALS:
            meal_df = df[df["Meal"] == meal][DISPLAY_COLS] if "Meal" in df.columns else pd.DataFrame()
            if not meal_df.empty:
                meal_cal = round(meal_df["Calories (kcal)"].sum(), 1)
                bg  = MEAL_COLORS.get(meal, "#f5f5f5")
                col = MEAL_TEXT_COLORS.get(meal, "#333")
                st.markdown(
                    f'<div class="meal-header" style="background:{bg};color:{col}">'
                    f'<span>{meal}</span>'
                    f'<span class="meal-kcal">{meal_cal} kcal</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(meal_df, use_container_width=True, hide_index=True)

        col_clear, _ = st.columns([1, 4])
        with col_clear:
            if st.button("🗑️ Clear Log", use_container_width=True):
                st.session_state.food_log = []
                st.session_state.last_result = None
                st.rerun()

        # ── Daily totals strip ────────────────────────────────────────────────
        total_cal     = round(df["Calories (kcal)"].sum(), 1)
        total_carbs   = round(df["Carbs (g)"].sum(), 1)
        total_protein = round(df["Protein (g)"].sum(), 1)
        total_fat     = round(df["Fat (g)"].sum(), 1)
        total_fiber   = round(df["Fiber (g)"].sum(), 1)

        st.markdown(f"""
        <div class="totals-strip">
            <div class="total-item">
                <div class="t-val">{total_cal}</div>
                <div class="t-lbl">kcal total</div>
            </div>
            <div class="total-item">
                <div class="t-val">{total_carbs}g</div>
                <div class="t-lbl">Carbs</div>
            </div>
            <div class="total-item">
                <div class="t-val">{total_protein}g</div>
                <div class="t-lbl">Protein</div>
            </div>
            <div class="total-item">
                <div class="t-val">{total_fat}g</div>
                <div class="t-lbl">Fat</div>
            </div>
            <div class="total-item">
                <div class="t-val">{total_fiber}g</div>
                <div class="t-lbl">Fiber</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Macro breakdown chart ─────────────────────────────────────────────
        st.markdown('<p class="section-title" style="margin-top:20px">🥧 Macro Breakdown</p>', unsafe_allow_html=True)

        carb_cal = total_carbs * 4
        protein_cal = total_protein * 4
        fat_cal = total_fat * 9
        total_macro_cal = carb_cal + protein_cal + fat_cal

        if total_macro_cal > 0:
            carb_pct    = round(carb_cal    / total_macro_cal * 100, 1)
            protein_pct = round(protein_cal / total_macro_cal * 100, 1)
            fat_pct     = round(100 - carb_pct - protein_pct, 1)

            fig = go.Figure()
            fig.add_trace(go.Bar(
                name="Carbs",
                x=[carb_pct], y=["Macros"],
                orientation="h",
                marker_color="#f9a825",
                text=f"Carbs {carb_pct}%",
                textposition="inside", insidetextanchor="middle",
                textfont=dict(color="white", size=13, family="Inter"),
            ))
            fig.add_trace(go.Bar(
                name="Protein",
                x=[protein_pct], y=["Macros"],
                orientation="h",
                marker_color="#1976d2",
                text=f"Protein {protein_pct}%",
                textposition="inside", insidetextanchor="middle",
                textfont=dict(color="white", size=13, family="Inter"),
            ))
            fig.add_trace(go.Bar(
                name="Fat",
                x=[fat_pct], y=["Macros"],
                orientation="h",
                marker_color="#8e24aa",
                text=f"Fat {fat_pct}%",
                textposition="inside", insidetextanchor="middle",
                textfont=dict(color="white", size=13, family="Inter"),
            ))
            fig.update_layout(
                barmode="stack",
                xaxis=dict(title="% of Calories", range=[0, 100], gridcolor="#f0f0f0"),
                yaxis=dict(showticklabels=False),
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.05,
                    xanchor="right", x=1,
                    font=dict(family="Inter", size=12),
                ),
                height=160,
                margin=dict(l=0, r=0, t=36, b=36),
                paper_bgcolor="white",
                plot_bgcolor="white",
                font=dict(family="Inter"),
            )
            st.plotly_chart(fig, use_container_width=True)

    else:
        st.markdown("""
        <div class="food-log-empty">
            <span class="empty-icon">🍽️</span>
            Your log is empty — search for a food above and tap <strong>Add to Today's Log</strong>.
        </div>
        """, unsafe_allow_html=True)

# ── Exercise Tracker Card ─────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown('<p class="section-title">🏃 Exercise Tracker</p>', unsafe_allow_html=True)

    col_ex, col_dur, col_add = st.columns([3, 2, 1])
    with col_ex:
        exercise = st.selectbox(
            "Exercise", list(EXERCISES.keys()),
            label_visibility="collapsed",
        )
    with col_dur:
        duration = st.number_input(
            "Minutes", min_value=1, max_value=300, value=30, step=5,
            label_visibility="collapsed",
        )
    with col_add:
        kcal_burned = round(EXERCISES[exercise] * duration, 1)
        st.markdown(
            f"<div style='padding-top:6px;font-size:0.85rem;color:#2d6a4f;"
            f"font-weight:600'>≈ {kcal_burned} kcal</div>",
            unsafe_allow_html=True,
        )

    if st.button("➕ Log Exercise", type="primary"):
        st.session_state.exercise_log.append({
            "Exercise": exercise,
            "Duration (min)": duration,
            "Calories Burned": kcal_burned,
        })
        st.success(f"✅ Logged **{exercise}** for {duration} min — ~{kcal_burned} kcal burned!")

    if st.session_state.exercise_log:
        import pandas as pd
        ex_df = pd.DataFrame(st.session_state.exercise_log)
        st.dataframe(ex_df, use_container_width=True, hide_index=True)

        total_burned = round(ex_df["Calories Burned"].sum(), 1)
        st.markdown(
            f"<div style='text-align:right;font-size:0.85rem;color:#2d6a4f;"
            f"font-weight:600;margin-top:4px'>🔥 Total burned today: {total_burned} kcal</div>",
            unsafe_allow_html=True,
        )
        col_ex_clear, _ = st.columns([1, 4])
        with col_ex_clear:
            if st.button("🗑️ Clear Exercise Log", use_container_width=True):
                st.session_state.exercise_log = []
                st.rerun()

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center; color:#999; font-size:0.75rem; margin-top:8px; padding-bottom:20px">
    NutriPulse · Data from USDA FoodData Central · Values per serving shown
</div>
""", unsafe_allow_html=True)
