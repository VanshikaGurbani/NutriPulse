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


def strip_quantity(text: str) -> str:
    """Remove leading quantities/units so USDA search gets just the food name."""
    # Remove leading numbers (int or decimal) and common unit words
    text = text.strip()
    text = re.sub(
        r"^\d+(\.\d+)?\s*(cups?|cup|tbsp|tsp|oz|g|kg|lb|lbs|ml|l|pieces?|slices?|servings?|large|medium|small|grilled|baked|fried|boiled|cooked|raw)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return text or text


def search_food(query: str) -> dict | None:
    """Call USDA API and return first result's nutrients, or None."""
    params = {"query": query, "api_key": API_KEY, "pageSize": 1}
    resp = requests.get(f"{API_BASE}/foods/search", params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    foods = data.get("foods", [])
    if not foods:
        return None
    food = foods[0]
    nutrients = {n["nutrientId"]: n.get("value", 0) for n in food.get("foodNutrients", [])}
    return {
        "description": food.get("description", query),
        "calories": round(nutrients.get(NUTRIENT_IDS["calories"], 0), 1),
        "protein": round(nutrients.get(NUTRIENT_IDS["protein"], 0), 1),
        "fat": round(nutrients.get(NUTRIENT_IDS["fat"], 0), 1),
        "carbs": round(nutrients.get(NUTRIENT_IDS["carbs"], 0), 1),
        "fiber": round(nutrients.get(NUTRIENT_IDS["fiber"], 0), 1),
    }


# ── Session state init ────────────────────────────────────────────────────────
if "food_log" not in st.session_state:
    st.session_state.food_log = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_input" not in st.session_state:
    st.session_state.last_input = None

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
    "Enter a food (e.g. '2 cups oatmeal', '1 grilled chicken breast')",
    placeholder="2 cups oatmeal",
)

if st.button("Analyze Food", type="primary"):
    if not food_input.strip():
        st.warning("Please enter a food item first.")
    else:
        query = strip_quantity(food_input)
        with st.spinner(f"Looking up '{query}'…"):
            try:
                result = search_food(query)
                if result is None:
                    st.warning(
                        "No results found — try a simpler food name like 'brown rice' or 'chicken breast'"
                    )
                    st.session_state.last_result = None
                else:
                    st.session_state.last_result = result
                    st.session_state.last_input = food_input
            except Exception as e:
                st.error(f"API error: {e}")
                st.session_state.last_result = None

# ── Nutrition card ────────────────────────────────────────────────────────────
if st.session_state.last_result:
    r = st.session_state.last_result
    st.subheader(f"Results for: {st.session_state.last_input}")
    st.caption(f"USDA match: *{r['description']}* (per 100 g)")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Calories", f"{r['calories']} kcal")
    col2.metric("Carbs", f"{r['carbs']} g")
    col3.metric("Protein", f"{r['protein']} g")
    col4.metric("Fat", f"{r['fat']} g")
    st.metric("Fiber", f"{r['fiber']} g", label_visibility="visible")

    if st.button("➕ Add to Today's Log"):
        entry = {
            "Food": st.session_state.last_input,
            "Calories (kcal)": r["calories"],
            "Carbs (g)": r["carbs"],
            "Protein (g)": r["protein"],
            "Fat (g)": r["fat"],
            "Fiber (g)": r["fiber"],
        }
        st.session_state.food_log.append(entry)
        st.success(f"Added '{st.session_state.last_input}' to your log!")

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
