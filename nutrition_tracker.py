import re
import datetime
import streamlit as st
import requests
import plotly.graph_objects as go
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("USDA_API_KEY")
API_BASE = "https://api.nal.usda.gov/fdc/v1"

NUTRIENT_IDS = {"calories": 1008, "protein": 1003, "fat": 1004, "carbs": 1005, "fiber": 1079}
CALORIE_IDS  = [1008, 2047]

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
MAX_SANE_CALORIES      = 950
LOW_CONFIDENCE_THRESHOLD = 5

SOURCE_BADGES = {
    "Foundation":     "🟢 Foundation",
    "SR Legacy":      "🔵 SR Legacy",
    "Survey (FNDDS)": "🔵 Survey (FNDDS)",
    "Branded":        "🟡 Branded",
}

MEALS = ["🌅 Breakfast", "☀️ Lunch", "🌙 Dinner", "🍎 Snack"]
MEAL_COLORS = {
    "🌅 Breakfast": "#fff3e0", "☀️ Lunch": "#e3f2fd",
    "🌙 Dinner":    "#f3e5f5", "🍎 Snack": "#e8f5e9",
}
MEAL_TEXT_COLORS = {
    "🌅 Breakfast": "#e65100", "☀️ Lunch": "#1565c0",
    "🌙 Dinner":    "#6a1b9a", "🍎 Snack": "#2e7d32",
}

EXERCISES = {
    "🏃 Running": 10, "🚶 Walking": 4, "🚴 Cycling": 8,
    "🏊 Swimming": 9, "💪 Strength Training": 5, "🔥 HIIT": 12,
    "🧘 Yoga / Stretching": 3, "⚽ Sports / Games": 7,
    "🪜 Stair Climbing": 9, "💃 Dancing": 5,
}

ACTIVITY_LEVELS = {
    "Sedentary (desk job)":          1.2,
    "Lightly active (1-3x/week)":    1.375,
    "Moderately active (3-5x/week)": 1.55,
    "Very active (6-7x/week)":       1.725,
    "Extra active (physical job)":   1.9,
}

RDA = {"Calories": 2000, "Protein (g)": 50, "Carbs (g)": 300, "Fat (g)": 65, "Fiber (g)": 28}


# ── Input parsing ─────────────────────────────────────────────────────────────

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
        return 100.0, "g", _clean_food_name(text)
    qty_str, unit_str, food = match.groups()
    if "/" in qty_str:
        n, d = qty_str.split("/"); qty = float(n) / float(d)
    else:
        qty = float(qty_str)
    if unit_str:
        u = unit_str.lower().strip()
        if re.match(r"fl\.?\s*oz", u):   unit = "oz"
        elif u.startswith("cup"):         unit = "cup"
        elif u.startswith("tbsp"):        unit = "tbsp"
        elif u.startswith("tsp"):         unit = "tsp"
        elif u.startswith("lb"):          unit = "lb"
        elif u.startswith("piece"):       unit = "piece"
        elif u.startswith("slice"):       unit = "slice"
        else:
            unit = u.rstrip("s") if u.endswith("s") and u not in ("oz", "ml") else u
            unit = unit if unit in UNIT_TO_GRAMS else "g"
    else:
        unit = "g"
    return qty, unit, _clean_food_name(food)


def _clean_food_name(name: str) -> str:
    name = re.sub(r"[^\w\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


# ── USDA matching ─────────────────────────────────────────────────────────────

def _score(food: dict, q_words: list) -> float:
    desc   = food.get("description", "").lower()
    tokens = re.split(r"[\s,]+", desc)
    all_present = all(re.search(rf"\b{re.escape(w)}\b", desc) for w in q_words)
    starts_with = 10 if (q_words and tokens and tokens[0] == q_words[0] and all_present) else 0
    n = max(len(q_words) + 1, 3)
    first_token_relevant = bool(tokens and tokens[0] in q_words)
    in_first_tokens = 5 if (first_token_relevant and all(w in tokens[:n] for w in q_words)) else 0
    word_hits = sum(1 for w in q_words if re.search(rf"\b{re.escape(w)}\b", desc))
    is_raw_food = any(rw in " ".join(q_words) for rw in RAW_FOODS)
    user_specified_prep = any(w in q_words for w in ("raw","cooked","baked","grilled","boiled","fried","roasted"))
    if not is_raw_food and not user_specified_prep:
        cooked_bonus = 4 if "cooked" in desc else 0
        raw_penalty  = -3 if re.search(r"\braw\b", desc) else 0
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
    nutrients      = {n_["nutrientId"]: n_.get("value", 0) for n_ in food.get("foodNutrients", [])}
    calorie_penalty = -50 if nutrients.get(NUTRIENT_IDS["calories"], 0) > MAX_SANE_CALORIES else 0
    brevity        = -len(desc) / 200
    return (starts_with + in_first_tokens + word_hits + cooked_bonus + raw_penalty
            + first_mismatch + wrong_category + calorie_penalty + brevity)


def best_match(foods: list, query: str) -> tuple:
    q_words = [w.lower() for w in re.split(r"\s+", query.strip()) if w]
    scored  = [(f, _score(f, q_words)) for f in foods]
    return max(scored, key=lambda x: x[1])


def _fetch(query: str, data_type) -> list:
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
    all_foods: list = []
    for dt in ["Foundation", "Survey (FNDDS)", "SR Legacy"]:
        all_foods.extend(_fetch(query, dt))
    if not all_foods:
        all_foods = _fetch(query, None)
        if not all_foods:
            resp = requests.get(f"{API_BASE}/foods/search",
                                params={"query": query, "api_key": API_KEY, "pageSize": 5}, timeout=10)
            resp.raise_for_status()
            return None
    food, match_score = best_match(all_foods, query)
    nutrients = {n["nutrientId"]: n.get("value", 0) for n in food.get("foodNutrients", [])}
    calories  = round(next((nutrients[cid] for cid in CALORIE_IDS if nutrients.get(cid, 0) > 0), 0), 1)
    raw_type  = food.get("dataType", "Unknown")
    q_words   = [w.lower() for w in re.split(r"\s+", query.strip()) if w]
    desc_lower = food.get("description", "").lower()
    any_word_found = any(re.search(rf"\b{re.escape(w)}\b", desc_lower) for w in q_words)
    return {
        "description":        food.get("description", query),
        "calories":           calories,
        "protein":            round(nutrients.get(NUTRIENT_IDS["protein"], 0), 1),
        "fat":                round(nutrients.get(NUTRIENT_IDS["fat"],     0), 1),
        "carbs":              round(nutrients.get(NUTRIENT_IDS["carbs"],   0), 1),
        "fiber":              round(nutrients.get(NUTRIENT_IDS["fiber"],   0), 1),
        "source":             SOURCE_BADGES.get(raw_type, f"📄 {raw_type}"),
        "suspicious_calories": calories > MAX_SANE_CALORIES,
        "low_confidence":     match_score < LOW_CONFIDENCE_THRESHOLD or not any_word_found,
    }


# ── UI helpers ────────────────────────────────────────────────────────────────

def macro_bar_fig(carbs_g, prot_g, fat_g, height=80):
    """Reusable stacked macro bar chart."""
    cc, pc, fc = carbs_g * 4, prot_g * 4, fat_g * 9
    total = cc + pc + fc
    if total == 0:
        return None
    cp = round(cc / total * 100, 1)
    pp = round(pc / total * 100, 1)
    fp = round(100 - cp - pp, 1)
    fig = go.Figure()
    for name, val, color in [("Carbs", cp, "#f9a825"), ("Protein", pp, "#1976d2"), ("Fat", fp, "#8e24aa")]:
        fig.add_trace(go.Bar(
            name=name, x=[val], y=[""], orientation="h", marker_color=color,
            text=f"{name} {val}%", textposition="inside", insidetextanchor="middle",
            textfont=dict(color="white", size=12, family="Inter"),
        ))
    fig.update_layout(
        barmode="stack",
        xaxis=dict(range=[0, 100], visible=False),
        yaxis=dict(showticklabels=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="right", x=1,
                    font=dict(family="Inter", size=11)),
        height=height, margin=dict(l=0, r=0, t=28, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter"),
    )
    return fig


def calc_tdee(gender, age, weight_kg, height_cm, activity):
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if gender == "Male" else -161)
    return round(bmr * ACTIVITY_LEVELS.get(activity, 1.55))


def nutrition_grade(consumed, goal, protein, fiber, carbs, fat):
    if consumed == 0:
        return None, None, None
    score = 0
    if goal > 0:
        d = abs(consumed - goal) / goal
        score += 40 if d <= 0.05 else 32 if d <= 0.10 else 22 if d <= 0.20 else 12 if d <= 0.35 else 4
    score += 20 if protein >= 50 else 15 if protein >= 35 else 10 if protein >= 20 else 5 if protein >= 10 else 0
    score += 20 if fiber >= 25 else 15 if fiber >= 18 else 10 if fiber >= 12 else 5 if fiber >= 6 else 0
    tm = carbs * 4 + protein * 4 + fat * 9
    if tm > 0:
        cp = carbs * 4 / tm * 100; pp = protein * 4 / tm * 100; fp = fat * 9 / tm * 100
        score += 20 if (45 <= cp <= 65 and 15 <= pp <= 35 and 20 <= fp <= 35) else \
                 12 if (40 <= cp <= 70 and 12 <= pp <= 40) else 5
    if score >= 85: return "A", "#2e7d32", "Excellent! Your nutrition is very well balanced."
    elif score >= 70: return "B", "#558b2f", "Good work! Small improvements could round it out."
    elif score >= 55: return "C", "#f57f17", "Decent. Try to improve protein and fiber intake."
    elif score >= 40: return "D", "#e65100", "Needs improvement — focus on balance and fiber."
    else:             return "F", "#c62828", "Keep logging — you need more food or better balance."


def smart_tips(protein, fiber, cal, goal_cal, water_ml, meals_used):
    tips = []
    if protein < 30 and cal > 200:
        tips.append(("💪", "Low protein", "Try chicken, eggs, Greek yogurt, or lentils."))
    if fiber < 10 and cal > 200:
        tips.append(("🌿", "Low fiber", "Add vegetables, beans, or whole grains."))
    if water_ml < 1000:
        tips.append(("💧", "Low hydration", "Aim for at least 8 glasses (2 L) of water today."))
    if len(meals_used) < 2 and cal > 100:
        tips.append(("🍽️", "Log more meals", "Track all meals for accurate daily totals."))
    if goal_cal > 0 and cal > goal_cal * 1.1:
        tips.append(("⚠️", f"{round(cal - goal_cal)} kcal over goal", "Consider a lighter option next meal."))
    if not tips:
        tips.append(("✅", "On track!" if cal > 0 else "Start logging",
                     "Your nutrition looks balanced today!" if cal > 0 else "Search for a food above to get started."))
    return tips


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="NutriPulse", page_icon="🥗", layout="centered")

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp { background: #f0f5f0; }

.hero-banner {
    background: linear-gradient(135deg, #2d6a4f 0%, #40916c 50%, #52b788 100%);
    border-radius: 16px; padding: 32px 36px; margin-bottom: 20px;
    color: white; box-shadow: 0 8px 32px rgba(45,106,79,0.3);
}
.hero-banner h1 { font-size: 2.4rem; font-weight: 700; margin: 0 0 6px; letter-spacing: -0.5px; }
.hero-banner p  { font-size: 1rem; opacity: 0.88; margin: 0; }

div[data-testid="stVerticalBlockBorderWrapper"] {
    background: white !important; border-radius: 14px !important;
    border: 1px solid #daeada !important;
    box-shadow: 0 2px 14px rgba(0,0,0,0.07) !important;
    padding: 6px 4px !important; margin-bottom: 8px !important;
}

.section-title {
    font-size: 1.1rem; font-weight: 650; color: #2d6a4f;
    margin: 0 0 12px; display: flex; align-items: center; gap: 8px;
}

.macro-grid {
    display: grid; grid-template-columns: repeat(5,1fr); gap: 12px; margin: 16px 0;
}
.macro-card { border-radius: 12px; padding: 14px 10px; text-align: center; transition: transform 0.15s; }
.macro-card:hover { transform: translateY(-2px); }
.macro-card .macro-value { font-size: 1.4rem; font-weight: 700; line-height: 1.2; }
.macro-card .macro-label { font-size: 0.72rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.6px; margin-top: 4px; opacity: 0.8; }
.macro-calories { background:#fff3e0; color:#e65100; }
.macro-carbs    { background:#fff8e1; color:#f57f17; }
.macro-protein  { background:#e3f2fd; color:#1565c0; }
.macro-fat      { background:#f3e5f5; color:#6a1b9a; }
.macro-fiber    { background:#e8f5e9; color:#2e7d32; }

.totals-strip {
    display:flex; gap:12px; flex-wrap:wrap;
    background: linear-gradient(135deg,#2d6a4f,#40916c);
    border-radius:12px; padding:18px 22px; margin:16px 0; color:white;
}
.total-item { flex:1; min-width:90px; text-align:center; }
.total-item .t-val { font-size:1.35rem; font-weight:700; line-height:1.2; }
.total-item .t-lbl { font-size:0.7rem; text-transform:uppercase; letter-spacing:0.6px; opacity:0.82; margin-top:3px; }

.meal-header {
    display:flex; align-items:center; justify-content:space-between;
    border-radius:10px; padding:8px 14px; margin:14px 0 6px;
    font-weight:600; font-size:0.92rem;
}
.meal-header .meal-kcal { font-size:0.82rem; opacity:0.85; font-weight:500; }

.goal-bar-wrap { background:#e8f0e8; border-radius:99px; height:18px; overflow:hidden; margin:10px 0 6px; }
.goal-bar-fill { height:100%; border-radius:99px; transition:width 0.4s ease, background 0.4s; }
.goal-bar-fill.green  { background: linear-gradient(90deg,#52b788,#2d6a4f); }
.goal-bar-fill.yellow { background: linear-gradient(90deg,#f9a825,#f57f17); }
.goal-bar-fill.red    { background: linear-gradient(90deg,#ef5350,#b71c1c); }
.goal-stats { display:flex; justify-content:space-between; font-size:0.82rem; color:#555; margin-top:2px; }
.goal-stats .consumed { font-weight:700; font-size:1rem; color:#1a2e1a; }
.goal-stats .remaining-green  { color:#2d6a4f; font-weight:600; }
.goal-stats .remaining-yellow { color:#f57f17; font-weight:600; }
.goal-stats .remaining-red    { color:#c62828; font-weight:600; }

.mini-bar-wrap { background:#e8f0e8; border-radius:99px; height:10px; overflow:hidden; margin:4px 0 2px; }
.mini-bar-fill { height:100%; border-radius:99px; }
.mini-bar-label { display:flex; justify-content:space-between; font-size:0.75rem; color:#555; }

.water-btn button { border-radius:20px !important; }

.tip-card { border-radius:10px; padding:10px 14px; margin:6px 0; display:flex; gap:10px; align-items:flex-start; }
.tip-icon { font-size:1.3rem; line-height:1; }
.tip-title { font-weight:600; font-size:0.88rem; color:#1a2e1a; }
.tip-body  { font-size:0.82rem; color:#555; }

.grade-badge {
    display:inline-block; font-size:3rem; font-weight:700;
    width:80px; height:80px; border-radius:50%;
    display:flex; align-items:center; justify-content:center;
    margin: 0 auto 8px; color:white;
}

.source-pill { display:inline-block; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:600; background:#e8f5e9; color:#2d6a4f; margin-left:6px; }
.result-food-name { font-size:1rem; font-weight:600; color:#1a2e1a; margin-bottom:4px; }
.result-serving-info { font-size:0.82rem; color:#666; margin-bottom:16px; }

.food-log-empty { text-align:center; padding:36px 0; color:#888; font-size:0.95rem; }
.food-log-empty .empty-icon { font-size:2.5rem; display:block; margin-bottom:8px; }

div[data-testid="stTextInput"] input {
    border-radius:10px !important; border:1.5px solid #b7d5c0 !important;
    padding:10px 14px !important; font-size:0.95rem !important;
}
div[data-testid="stTextInput"] input:focus {
    border-color:#40916c !important; box-shadow:0 0 0 3px rgba(64,145,108,0.15) !important;
}
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg,#2d6a4f,#40916c) !important;
    border:none !important; border-radius:10px !important; padding:10px 24px !important;
    font-weight:600 !important; box-shadow:0 4px 12px rgba(45,106,79,0.3) !important;
}
div[data-testid="stButton"] > button[kind="secondary"] {
    border-radius:10px !important; border:1.5px solid #b7d5c0 !important;
    color:#2d6a4f !important; font-weight:500 !important;
}
div[data-testid="stRadio"] > div { gap:8px !important; }
div[data-testid="stRadio"] label {
    border:1.5px solid #b7d5c0 !important; border-radius:20px !important;
    padding:4px 14px !important; font-size:0.85rem !important;
}
div[data-testid="stAlert"] { border-radius:10px !important; }
div[data-testid="stDataFrame"] { border-radius:10px; overflow:hidden; border:1px solid #e0ece0 !important; }
div[data-testid="stTabs"] [data-baseweb="tab-list"] { gap:4px; }
div[data-testid="stTabs"] [data-baseweb="tab"] {
    border-radius:10px 10px 0 0; padding:8px 18px; font-weight:500;
}
hr { border-color:#dce8dc !important; margin:20px 0 !important; }
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────
_ss = st.session_state
if "food_log"      not in _ss: _ss.food_log      = []
if "exercise_log"  not in _ss: _ss.exercise_log  = []
if "last_result"   not in _ss: _ss.last_result   = None
if "last_input"    not in _ss: _ss.last_input     = None
if "serving_qty"   not in _ss: _ss.serving_qty    = 100.0
if "serving_unit"  not in _ss: _ss.serving_unit   = "g"
if "calorie_goal"  not in _ss: _ss.calorie_goal   = 2000
if "selected_meal" not in _ss: _ss.selected_meal  = "🌅 Breakfast"
if "water_ml"      not in _ss: _ss.water_ml       = 0
if "water_goal_ml" not in _ss: _ss.water_goal_ml  = 2000
if "recent_foods"  not in _ss: _ss.recent_foods   = []   # list of (input_str, result_dict)
if "history"       not in _ss: _ss.history        = []   # list of daily summary dicts
if "food_input"    not in _ss: _ss.food_input      = ""
if "cmp_r1"        not in _ss: _ss.cmp_r1         = None
if "cmp_r2"        not in _ss: _ss.cmp_r2         = None
if "profile"       not in _ss:
    _ss.profile = {"name": "", "age": 25, "gender": "Female",
                   "weight": 65.0, "height": 165.0,
                   "activity": "Moderately active (3-5x/week)"}
if "custom_goals"  not in _ss:
    _ss.custom_goals = {"protein": 50, "carbs": 300, "fat": 65, "fiber": 28}


# ── Hero Banner ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-banner">
    <h1>🥗 NutriPulse</h1>
    <p>Track what you eat · Powered by USDA FoodData Central</p>
</div>
""", unsafe_allow_html=True)

if not API_KEY:
    st.error("**USDA API key not found.** Create a `.env` file with `USDA_API_KEY=your_key`.")
    st.stop()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["🍽️ Today", "📊 Insights", "👤 Profile & Goals", "📅 History"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — TODAY
# ══════════════════════════════════════════════════════════════════════════════
with tab1:

    # ── Daily Calorie Goal ────────────────────────────────────────────────────
    with st.container(border=True):
        col_t, col_i = st.columns([3, 1])
        with col_t:
            st.markdown('<p class="section-title">🎯 Daily Calorie Goal</p>', unsafe_allow_html=True)
        with col_i:
            calorie_goal = st.number_input("Goal", min_value=500, max_value=5000,
                                           value=_ss.calorie_goal, step=50,
                                           label_visibility="collapsed")
            _ss.calorie_goal = calorie_goal

        consumed = round(sum(e["Calories (kcal)"] for e in _ss.food_log), 1)
        burned   = round(sum(e["Calories Burned"]  for e in _ss.exercise_log), 1)
        net      = round(consumed - burned, 1)
        goal     = _ss.calorie_goal
        pct      = min(net / goal, 1.0) if goal > 0 else 0
        pct_d    = min(round(pct * 100, 1), 100)

        if pct < 0.75:
            bc, rc, si = "green",  "remaining-green",  "✅"
            smsg = f"{goal - net:.0f} kcal remaining"
        elif pct < 1.0:
            bc, rc, si = "yellow", "remaining-yellow", "⚡"
            smsg = f"{goal - net:.0f} kcal remaining — almost there!"
        else:
            bc, rc, si = "red",    "remaining-red",    "🔴"
            smsg = f"{net - goal:.0f} kcal over goal"

        burned_note = f" · 🔥 {burned} burned" if burned > 0 else ""
        st.markdown(f"""
        <div class="goal-bar-wrap">
            <div class="goal-bar-fill {bc}" style="width:{pct_d}%"></div>
        </div>
        <div class="goal-stats">
            <span>{si} <span class="{rc}">{smsg}</span></span>
            <span><span class="consumed">{net}</span> / {goal} kcal net&nbsp;
            <span style="color:#888;font-size:0.78rem">({consumed} eaten{burned_note})</span></span>
        </div>""", unsafe_allow_html=True)

        # Macro mini-progress bars
        if consumed > 0 or any(_ss.custom_goals.values()):
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            cg = _ss.custom_goals
            tc = round(sum(e["Carbs (g)"]    for e in _ss.food_log), 1)
            tp = round(sum(e["Protein (g)"]  for e in _ss.food_log), 1)
            tf = round(sum(e["Fat (g)"]      for e in _ss.food_log), 1)
            tfib = round(sum(e["Fiber (g)"]  for e in _ss.food_log), 1)
            mc1, mc2, mc3, mc4 = st.columns(4)
            for col, label, val, goal_v, color in [
                (mc1, "Protein", tp,   cg["protein"], "#1976d2"),
                (mc2, "Carbs",   tc,   cg["carbs"],   "#f9a825"),
                (mc3, "Fat",     tf,   cg["fat"],     "#8e24aa"),
                (mc4, "Fiber",   tfib, cg["fiber"],   "#2e7d32"),
            ]:
                pct_m = min(round(val / goal_v * 100) if goal_v else 0, 100)
                col.markdown(
                    f'<div class="mini-bar-label"><span>{label}</span><span>{val}g / {goal_v}g</span></div>'
                    f'<div class="mini-bar-wrap"><div class="mini-bar-fill" style="width:{pct_m}%;background:{color}"></div></div>',
                    unsafe_allow_html=True,
                )

    # ── Water Tracker ─────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown('<p class="section-title">💧 Water Intake</p>', unsafe_allow_html=True)
        wg = _ss.water_goal_ml
        wc = _ss.water_ml
        w_pct = min(round(wc / wg * 100), 100) if wg else 0
        w_glasses = round(wc / 250, 1)
        w_goal_g  = round(wg / 250)

        w_color = "#1976d2" if w_pct < 75 else "#2e7d32"
        st.markdown(
            f'<div class="mini-bar-label"><span>💧 {w_glasses} / {w_goal_g} glasses &nbsp;·&nbsp; {wc} / {wg} ml</span><span>{w_pct}%</span></div>'
            f'<div class="mini-bar-wrap" style="height:14px"><div class="mini-bar-fill" style="width:{w_pct}%;background:{w_color}"></div></div>',
            unsafe_allow_html=True,
        )
        wc1, wc2, wc3, wc4, wc5 = st.columns(5)
        if wc1.button("+ 1 glass", use_container_width=True):
            _ss.water_ml += 250; st.rerun()
        if wc2.button("+ 500 ml",  use_container_width=True):
            _ss.water_ml += 500; st.rerun()
        if wc3.button("+ 1 L",     use_container_width=True):
            _ss.water_ml += 1000; st.rerun()
        if wc4.button("Reset",     use_container_width=True):
            _ss.water_ml = 0; st.rerun()
        with wc5:
            new_goal = st.number_input("Goal ml", min_value=500, max_value=5000,
                                       value=_ss.water_goal_ml, step=250,
                                       label_visibility="collapsed")
            _ss.water_goal_ml = new_goal

    # ── Food Search ───────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown('<p class="section-title">🔍 Search a Food</p>', unsafe_allow_html=True)

        # Recent foods quick-select
        if _ss.recent_foods:
            st.markdown("<span style='font-size:0.8rem;color:#888'>Recent:</span>", unsafe_allow_html=True)
            rf_cols = st.columns(min(len(_ss.recent_foods), 5))
            for i, (rf_label, _) in enumerate(_ss.recent_foods[:5]):
                if rf_cols[i].button(rf_label, key=f"rf_{i}", use_container_width=True):
                    _ss.food_input = rf_label
                    st.rerun()

        food_input = st.text_input(
            "Food item", value=_ss.food_input,
            placeholder="e.g. 2 cups oatmeal · 1.5 oz chicken · 3 tbsp peanut butter",
            label_visibility="collapsed", key="food_input_widget",
        )

        col_btn, col_hint = st.columns([1, 3])
        with col_btn:
            analyze_clicked = st.button("Analyze Food", type="primary", use_container_width=True)
        with col_hint:
            st.markdown(
                "<span style='color:#888;font-size:0.82rem;line-height:2.6'>"
                "Tip: include quantity & unit — e.g. <em>\"2 cups brown rice\"</em></span>",
                unsafe_allow_html=True,
            )

        if analyze_clicked:
            _ss.food_input = food_input
            if not food_input.strip():
                st.warning("Please enter a food item first.")
            else:
                qty, unit, food_name = parse_serving(food_input)
                with st.spinner(f"Looking up '{food_name}'…"):
                    try:
                        result = search_food(food_name)
                        if result is None:
                            st.warning("No results found — try a simpler name.")
                            _ss.last_result = None
                        else:
                            _ss.last_result   = result
                            _ss.last_input    = food_input
                            _ss.serving_qty   = qty
                            _ss.serving_unit  = unit
                            # Add to recent foods (max 10, no duplicates)
                            _ss.recent_foods = [(food_input, result)] + [
                                x for x in _ss.recent_foods if x[0] != food_input
                            ][:9]
                    except Exception as e:
                        st.error(f"API error: {e}")
                        _ss.last_result = None

    # ── Nutrition Info ────────────────────────────────────────────────────────
    if _ss.last_result:
        r = _ss.last_result
        with st.container(border=True):
            st.markdown('<p class="section-title">📊 Nutrition Info</p>', unsafe_allow_html=True)
            if r.get("low_confidence"):
                st.warning("⚠️ **Low confidence match** — try rephrasing, e.g. *'rolled oats'* instead of *'oatmeal'*.")
            if r.get("suspicious_calories"):
                st.error("🚨 **Unusual calorie value** — numbers may not be accurate.")

            col_qty, col_unit = st.columns([1, 2])
            serving_qty = col_qty.number_input("Amount", min_value=0.1, max_value=9999.0,
                                               value=float(_ss.serving_qty), step=0.5)
            unit_index  = UNITS.index(_ss.serving_unit) if _ss.serving_unit in UNITS else 0
            serving_unit = col_unit.selectbox("Unit", UNITS, index=unit_index)
            _ss.serving_qty  = serving_qty
            _ss.serving_unit = serving_unit

            grams  = serving_qty * UNIT_TO_GRAMS.get(serving_unit, 1.0)
            factor = grams / 100

            st.markdown(
                f'<div class="result-food-name">{r["description"]}'
                f'<span class="source-pill">{r.get("source","")}</span></div>'
                f'<div class="result-serving-info">Serving: {serving_qty:g} {serving_unit} = {grams:.0f} g</div>',
                unsafe_allow_html=True,
            )

            cal   = round(r["calories"] * factor, 1)
            carbs = round(r["carbs"]    * factor, 1)
            prot  = round(r["protein"]  * factor, 1)
            fat   = round(r["fat"]      * factor, 1)
            fiber = round(r["fiber"]    * factor, 1)

            st.markdown(f"""
            <div class="macro-grid">
                <div class="macro-card macro-calories"><div class="macro-value">{cal}</div><div class="macro-label">kcal</div></div>
                <div class="macro-card macro-carbs"><div class="macro-value">{carbs}g</div><div class="macro-label">Carbs</div></div>
                <div class="macro-card macro-protein"><div class="macro-value">{prot}g</div><div class="macro-label">Protein</div></div>
                <div class="macro-card macro-fat"><div class="macro-value">{fat}g</div><div class="macro-label">Fat</div></div>
                <div class="macro-card macro-fiber"><div class="macro-value">{fiber}g</div><div class="macro-label">Fiber</div></div>
            </div>""", unsafe_allow_html=True)

            fig_item = macro_bar_fig(carbs, prot, fat)
            if fig_item:
                st.plotly_chart(fig_item, use_container_width=True)

            meal_idx = MEALS.index(_ss.selected_meal) if _ss.selected_meal in MEALS else 0
            selected_meal = st.radio("Meal", MEALS, index=meal_idx, horizontal=True,
                                     label_visibility="collapsed")
            _ss.selected_meal = selected_meal

            if st.button("➕ Add to Today's Log", type="primary"):
                _ss.food_log.append({
                    "Meal": selected_meal,
                    "Food": f"{_ss.last_input} ({grams:.0f}g)",
                    "Calories (kcal)": cal, "Carbs (g)": carbs,
                    "Protein (g)": prot, "Fat (g)": fat, "Fiber (g)": fiber,
                })
                st.success(f"✅ Added **{_ss.last_input}** ({grams:.0f}g) to **{selected_meal}**!")

    # ── Today's Food Log ──────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown('<p class="section-title">📋 Today\'s Food Log</p>', unsafe_allow_html=True)

        if _ss.food_log:
            import pandas as pd
            df = pd.DataFrame(_ss.food_log)
            DCOLS = ["Food", "Calories (kcal)", "Carbs (g)", "Protein (g)", "Fat (g)", "Fiber (g)"]

            for meal in MEALS:
                mdf = df[df["Meal"] == meal][DCOLS] if "Meal" in df.columns else pd.DataFrame()
                if not mdf.empty:
                    mcal = round(mdf["Calories (kcal)"].sum(), 1)
                    bg = MEAL_COLORS.get(meal, "#f5f5f5"); col = MEAL_TEXT_COLORS.get(meal, "#333")
                    st.markdown(
                        f'<div class="meal-header" style="background:{bg};color:{col}">'
                        f'<span>{meal}</span><span class="meal-kcal">{mcal} kcal</span></div>',
                        unsafe_allow_html=True,
                    )
                    st.dataframe(mdf, use_container_width=True, hide_index=True)

            col_clr, col_exp, _ = st.columns([1, 1, 3])
            if col_clr.button("🗑️ Clear Log", use_container_width=True):
                _ss.food_log = []; _ss.last_result = None; st.rerun()

            # Export CSV
            csv_data = df[DCOLS].to_csv(index=False).encode("utf-8")
            col_exp.download_button(
                "⬇️ Export CSV", data=csv_data,
                file_name=f"nutripulse_{datetime.date.today()}.csv",
                mime="text/csv", use_container_width=True,
            )

            total_cal  = round(df["Calories (kcal)"].sum(), 1)
            total_carbs = round(df["Carbs (g)"].sum(), 1)
            total_prot = round(df["Protein (g)"].sum(), 1)
            total_fat  = round(df["Fat (g)"].sum(), 1)
            total_fib  = round(df["Fiber (g)"].sum(), 1)

            st.markdown(f"""
            <div class="totals-strip">
                <div class="total-item"><div class="t-val">{total_cal}</div><div class="t-lbl">kcal total</div></div>
                <div class="total-item"><div class="t-val">{total_carbs}g</div><div class="t-lbl">Carbs</div></div>
                <div class="total-item"><div class="t-val">{total_prot}g</div><div class="t-lbl">Protein</div></div>
                <div class="total-item"><div class="t-val">{total_fat}g</div><div class="t-lbl">Fat</div></div>
                <div class="total-item"><div class="t-val">{total_fib}g</div><div class="t-lbl">Fiber</div></div>
            </div>""", unsafe_allow_html=True)

            fig_daily = macro_bar_fig(total_carbs, total_prot, total_fat, height=120)
            if fig_daily:
                st.plotly_chart(fig_daily, use_container_width=True)
        else:
            st.markdown("""
            <div class="food-log-empty">
                <span class="empty-icon">🍽️</span>
                Your log is empty — search for a food above and tap <strong>Add to Today's Log</strong>.
            </div>""", unsafe_allow_html=True)

    # ── Exercise Tracker ──────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown('<p class="section-title">🏃 Exercise Tracker</p>', unsafe_allow_html=True)
        ec1, ec2, ec3 = st.columns([3, 2, 1])
        with ec1:
            exercise = st.selectbox("Exercise", list(EXERCISES.keys()), label_visibility="collapsed")
        with ec2:
            duration = st.number_input("Minutes", min_value=1, max_value=300, value=30, step=5,
                                       label_visibility="collapsed")
        with ec3:
            kcal_burned = round(EXERCISES[exercise] * duration, 1)
            st.markdown(f"<div style='padding-top:6px;font-size:0.85rem;color:#2d6a4f;font-weight:600'>≈ {kcal_burned} kcal</div>",
                        unsafe_allow_html=True)
        if st.button("➕ Log Exercise", type="primary"):
            _ss.exercise_log.append({"Exercise": exercise, "Duration (min)": duration, "Calories Burned": kcal_burned})
            st.success(f"✅ Logged **{exercise}** for {duration} min — ~{kcal_burned} kcal burned!")
        if _ss.exercise_log:
            import pandas as pd
            ex_df = pd.DataFrame(_ss.exercise_log)
            st.dataframe(ex_df, use_container_width=True, hide_index=True)
            total_burned = round(ex_df["Calories Burned"].sum(), 1)
            st.markdown(f"<div style='text-align:right;font-size:0.85rem;color:#2d6a4f;font-weight:600;margin-top:4px'>🔥 Total burned: {total_burned} kcal</div>",
                        unsafe_allow_html=True)
            col_xclr, _ = st.columns([1, 4])
            if col_xclr.button("🗑️ Clear Exercise Log", use_container_width=True):
                _ss.exercise_log = []; st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — INSIGHTS
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    import pandas as pd

    if not _ss.food_log:
        st.info("Log some food in the **Today** tab to see insights here.")
    else:
        df = pd.DataFrame(_ss.food_log)
        total_cal   = round(df["Calories (kcal)"].sum(), 1)
        total_carbs = round(df["Carbs (g)"].sum(), 1)
        total_prot  = round(df["Protein (g)"].sum(), 1)
        total_fat   = round(df["Fat (g)"].sum(), 1)
        total_fib   = round(df["Fiber (g)"].sum(), 1)

        # ── Nutrition Grade ───────────────────────────────────────────────────
        with st.container(border=True):
            st.markdown('<p class="section-title">🏅 Today\'s Nutrition Grade</p>', unsafe_allow_html=True)
            grade, gcolor, gmsg = nutrition_grade(total_cal, _ss.calorie_goal, total_prot, total_fib, total_carbs, total_fat)
            if grade:
                gc1, gc2 = st.columns([1, 4])
                with gc1:
                    st.markdown(
                        f'<div style="width:80px;height:80px;border-radius:50%;background:{gcolor};'
                        f'display:flex;align-items:center;justify-content:center;'
                        f'font-size:2.2rem;font-weight:700;color:white;margin:auto">{grade}</div>',
                        unsafe_allow_html=True,
                    )
                with gc2:
                    st.markdown(f"**{gmsg}**")
                    st.caption("Based on calorie adherence, protein, fiber, and macro balance.")

        # ── Smart Tips ────────────────────────────────────────────────────────
        with st.container(border=True):
            st.markdown('<p class="section-title">💡 Smart Suggestions</p>', unsafe_allow_html=True)
            meals_used = set(df["Meal"].unique()) if "Meal" in df.columns else set()
            tips = smart_tips(total_prot, total_fib, total_cal, _ss.calorie_goal, _ss.water_ml, meals_used)
            for icon, title, body in tips:
                st.markdown(
                    f'<div class="tip-card" style="background:#f8fdf8;border:1px solid #daeada">'
                    f'<span class="tip-icon">{icon}</span>'
                    f'<div><div class="tip-title">{title}</div><div class="tip-body">{body}</div></div></div>',
                    unsafe_allow_html=True,
                )

        # ── Nutrient Radar vs RDA ─────────────────────────────────────────────
        with st.container(border=True):
            st.markdown('<p class="section-title">🕸️ Nutrients vs Daily Targets</p>', unsafe_allow_html=True)
            rda_goal = _ss.calorie_goal if _ss.calorie_goal > 0 else 2000
            categories = ["Calories", "Protein (g)", "Carbs (g)", "Fat (g)", "Fiber (g)"]
            rda_vals   = [rda_goal, _ss.custom_goals["protein"], _ss.custom_goals["carbs"],
                          _ss.custom_goals["fat"], _ss.custom_goals["fiber"]]
            actual_vals = [total_cal, total_prot, total_carbs, total_fat, total_fib]
            pcts = [min(round(a / r * 100, 1) if r else 0, 150) for a, r in zip(actual_vals, rda_vals)]

            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(
                r=pcts + [pcts[0]], theta=categories + [categories[0]],
                fill="toself", fillcolor="rgba(64,145,108,0.2)",
                line=dict(color="#40916c", width=2), name="Today",
            ))
            fig_radar.add_trace(go.Scatterpolar(
                r=[100] * (len(categories) + 1), theta=categories + [categories[0]],
                line=dict(color="#b7d5c0", width=1.5, dash="dash"), name="Target",
            ))
            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 150],
                                           ticksuffix="%", tickfont=dict(size=10))),
                legend=dict(orientation="h", yanchor="bottom", y=-0.15),
                height=320, margin=dict(l=40, r=40, t=20, b=20),
                paper_bgcolor="white", font=dict(family="Inter"),
            )
            st.plotly_chart(fig_radar, use_container_width=True)
            st.caption("Shows % of daily target reached. Dashed line = 100% of goal.")

        # ── Meal Composition Donut ────────────────────────────────────────────
        with st.container(border=True):
            st.markdown('<p class="section-title">🥧 Calories by Meal</p>', unsafe_allow_html=True)
            if "Meal" in df.columns:
                meal_cals = df.groupby("Meal")["Calories (kcal)"].sum().reset_index()
                meal_cals = meal_cals[meal_cals["Calories (kcal)"] > 0]
                if not meal_cals.empty:
                    colors = [MEAL_TEXT_COLORS.get(m, "#888") for m in meal_cals["Meal"]]
                    fig_donut = go.Figure(go.Pie(
                        labels=meal_cals["Meal"], values=meal_cals["Calories (kcal)"],
                        hole=0.5, marker_colors=colors,
                        textinfo="label+percent", textfont=dict(family="Inter", size=12),
                    ))
                    fig_donut.update_layout(
                        height=280, margin=dict(l=0, r=0, t=10, b=10),
                        showlegend=False, paper_bgcolor="white", font=dict(family="Inter"),
                    )
                    st.plotly_chart(fig_donut, use_container_width=True)

    # ── Food Comparison ───────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown('<p class="section-title">⚖️ Food Comparison</p>', unsafe_allow_html=True)
        fc1, fc2 = st.columns(2)
        with fc1:
            cmp1 = st.text_input("Food 1", placeholder="e.g. brown rice", key="cmp1")
        with fc2:
            cmp2 = st.text_input("Food 2", placeholder="e.g. white rice",  key="cmp2")

        if st.button("Compare (per 100g)", type="primary"):
            if cmp1.strip() and cmp2.strip():
                with st.spinner("Fetching…"):
                    try:
                        _ss.cmp_r1 = search_food(_clean_food_name(cmp1))
                        _ss.cmp_r2 = search_food(_clean_food_name(cmp2))
                    except Exception as e:
                        st.error(f"Error: {e}")

        if _ss.cmp_r1 and _ss.cmp_r2:
            r1, r2 = _ss.cmp_r1, _ss.cmp_r2
            labels  = ["Calories (kcal)", "Carbs (g)", "Protein (g)", "Fat (g)", "Fiber (g)"]
            v1 = [r1["calories"], r1["carbs"], r1["protein"], r1["fat"], r1["fiber"]]
            v2 = [r2["calories"], r2["carbs"], r2["protein"], r2["fat"], r2["fiber"]]
            colors1 = ["#40916c"] * len(labels)
            colors2 = ["#1976d2"] * len(labels)

            fig_cmp = go.Figure()
            fig_cmp.add_trace(go.Bar(name=r1["description"][:30], x=labels, y=v1, marker_color="#40916c"))
            fig_cmp.add_trace(go.Bar(name=r2["description"][:30], x=labels, y=v2, marker_color="#1976d2"))
            fig_cmp.update_layout(
                barmode="group",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(family="Inter", size=11)),
                height=300, margin=dict(l=0, r=0, t=36, b=0),
                paper_bgcolor="white", plot_bgcolor="white", font=dict(family="Inter"),
                yaxis=dict(gridcolor="#f0f0f0"),
            )
            st.plotly_chart(fig_cmp, use_container_width=True)

            # Side-by-side table
            cmp_df = pd.DataFrame({
                "Nutrient": labels,
                r1["description"][:25]: v1,
                r2["description"][:25]: v2,
            })
            st.dataframe(cmp_df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PROFILE & GOALS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:

    # ── User Profile ──────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown('<p class="section-title">👤 Your Profile</p>', unsafe_allow_html=True)
        p = _ss.profile
        pc1, pc2 = st.columns(2)
        p["name"]   = pc1.text_input("Name",   value=p["name"])
        p["gender"] = pc2.selectbox("Gender", ["Female", "Male"], index=0 if p["gender"]=="Female" else 1)
        pc3, pc4, pc5 = st.columns(3)
        p["age"]    = pc3.number_input("Age",        min_value=10, max_value=100, value=p["age"],   step=1)
        p["weight"] = pc4.number_input("Weight (kg)", min_value=30.0, max_value=250.0, value=p["weight"], step=0.5)
        p["height"] = pc5.number_input("Height (cm)", min_value=100.0, max_value=250.0, value=p["height"], step=0.5)
        p["activity"] = st.selectbox("Activity Level", list(ACTIVITY_LEVELS.keys()),
                                     index=list(ACTIVITY_LEVELS.keys()).index(p["activity"]))
        _ss.profile = p

        tdee = calc_tdee(p["gender"], p["age"], p["weight"], p["height"], p["activity"])
        st.markdown(
            f"<div style='background:#e8f5e9;border-radius:10px;padding:12px 16px;margin-top:8px'>"
            f"<b>Estimated daily calorie need (TDEE):</b> "
            f"<span style='font-size:1.3rem;font-weight:700;color:#2d6a4f'>{tdee} kcal</span>"
            f"<span style='color:#888;font-size:0.8rem'> &nbsp;(Mifflin-St Jeor formula)</span></div>",
            unsafe_allow_html=True,
        )
        if st.button("Apply TDEE as Calorie Goal", type="primary"):
            _ss.calorie_goal = tdee
            st.success(f"✅ Calorie goal updated to {tdee} kcal!")

    # ── Custom Macro Goals ────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown('<p class="section-title">🎯 Daily Macro Goals</p>', unsafe_allow_html=True)
        cg = _ss.custom_goals
        mg1, mg2, mg3, mg4 = st.columns(4)
        cg["protein"] = mg1.number_input("Protein (g)", min_value=10, max_value=500, value=cg["protein"], step=5)
        cg["carbs"]   = mg2.number_input("Carbs (g)",   min_value=10, max_value=800, value=cg["carbs"],   step=10)
        cg["fat"]     = mg3.number_input("Fat (g)",     min_value=10, max_value=300, value=cg["fat"],     step=5)
        cg["fiber"]   = mg4.number_input("Fiber (g)",   min_value=5,  max_value=100, value=cg["fiber"],   step=1)
        _ss.custom_goals = cg
        st.caption("These goals power the macro progress bars in the Today tab.")

    # ── Recent Foods ──────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown('<p class="section-title">🕐 Recent Foods</p>', unsafe_allow_html=True)
        if _ss.recent_foods:
            for i, (label, res) in enumerate(_ss.recent_foods):
                rc1, rc2, rc3 = st.columns([3, 2, 1])
                rc1.markdown(f"**{label}**")
                rc2.markdown(f"<span style='color:#888;font-size:0.85rem'>{res['description'][:35]}</span>",
                             unsafe_allow_html=True)
                if rc3.button("Search", key=f"recent_search_{i}"):
                    _ss.food_input = label; st.rerun()
            if st.button("Clear Recent Foods"):
                _ss.recent_foods = []; st.rerun()
        else:
            st.markdown("<span style='color:#888;font-size:0.9rem'>No recent foods yet — search for something in the Today tab.</span>",
                        unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — HISTORY
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    import pandas as pd

    with st.container(border=True):
        st.markdown('<p class="section-title">📅 Daily History</p>', unsafe_allow_html=True)
        st.caption("Save a snapshot of today's totals to build your history log.")

        if st.button("💾 Save Today's Summary", type="primary"):
            today_str = datetime.date.today().strftime("%d %b %Y")
            consumed_now = round(sum(e["Calories (kcal)"] for e in _ss.food_log), 1)
            burned_now   = round(sum(e["Calories Burned"]  for e in _ss.exercise_log), 1)
            snap = {
                "Date":              today_str,
                "Calories Eaten":    consumed_now,
                "Calories Burned":   burned_now,
                "Net Calories":      round(consumed_now - burned_now, 1),
                "Goal":              _ss.calorie_goal,
                "Protein (g)":       round(sum(e["Protein (g)"] for e in _ss.food_log), 1),
                "Carbs (g)":         round(sum(e["Carbs (g)"]   for e in _ss.food_log), 1),
                "Fat (g)":           round(sum(e["Fat (g)"]     for e in _ss.food_log), 1),
                "Fiber (g)":         round(sum(e["Fiber (g)"]   for e in _ss.food_log), 1),
                "Water (ml)":        _ss.water_ml,
                "Foods Logged":      len(_ss.food_log),
            }
            # Remove existing entry for today if re-saving
            _ss.history = [h for h in _ss.history if h["Date"] != today_str] + [snap]
            st.success(f"✅ Saved summary for {today_str}!")

        if _ss.history:
            hist_df = pd.DataFrame(_ss.history)
            st.dataframe(hist_df, use_container_width=True, hide_index=True)

            # Export history CSV
            hist_csv = hist_df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Export History CSV", data=hist_csv,
                               file_name="nutripulse_history.csv", mime="text/csv")

            # Calorie Trend Chart
            if len(_ss.history) >= 2:
                st.markdown('<p class="section-title" style="margin-top:16px">📈 Calorie Trend</p>',
                            unsafe_allow_html=True)
                fig_trend = go.Figure()
                fig_trend.add_trace(go.Scatter(
                    x=hist_df["Date"], y=hist_df["Calories Eaten"],
                    mode="lines+markers", name="Eaten",
                    line=dict(color="#40916c", width=2.5),
                    marker=dict(size=7, color="#40916c"),
                ))
                fig_trend.add_trace(go.Scatter(
                    x=hist_df["Date"], y=hist_df["Net Calories"],
                    mode="lines+markers", name="Net",
                    line=dict(color="#1976d2", width=2, dash="dot"),
                    marker=dict(size=6, color="#1976d2"),
                ))
                if "Goal" in hist_df.columns:
                    fig_trend.add_trace(go.Scatter(
                        x=hist_df["Date"], y=hist_df["Goal"],
                        mode="lines", name="Goal",
                        line=dict(color="#f9a825", width=1.5, dash="dash"),
                    ))
                fig_trend.update_layout(
                    xaxis=dict(title="Date", gridcolor="#f0f0f0"),
                    yaxis=dict(title="kcal", gridcolor="#f0f0f0"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(family="Inter", size=11)),
                    height=280, margin=dict(l=0, r=0, t=36, b=0),
                    paper_bgcolor="white", plot_bgcolor="white", font=dict(family="Inter"),
                )
                st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.markdown("<span style='color:#888;font-size:0.9rem'>No history saved yet. Log food and tap <b>Save Today's Summary</b>.</span>",
                        unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;color:#999;font-size:0.75rem;margin-top:8px;padding-bottom:20px">
    NutriPulse · Data from USDA FoodData Central · Values per serving shown
</div>
""", unsafe_allow_html=True)
