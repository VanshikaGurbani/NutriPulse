"""NutriPulse: Streamlit entry point. All logic lives in the nutripulse package; this file only wires the page together."""
import streamlit as st

from nutripulse import apis, feedback
from nutripulse.cache import stats
from nutripulse.ui import common, history, insights, profile, style, today

st.set_page_config(page_title="NutriPulse", page_icon="🥗", layout="wide")
style.inject()

if not apis.usda_key():
    st.error("**USDA API key not found.** Create a `.env` file with `USDA_API_KEY=your_key` (see `.env.example`).")
    st.stop()

store = common.get_store()

if st.session_state.get("np_toast"):
    msg, icon = st.session_state.pop("np_toast")
    st.toast(msg, icon=icon)

st.markdown('<div class="np-header"><h1>🥗 NutriPulse</h1><span class="np-muted">Log what you eat in seconds</span></div>',
            unsafe_allow_html=True)

tab_today, tab_insights, tab_history, tab_profile = st.tabs(["Today", "Insights", "History", "Profile"])
with tab_today:
    today.render(store)
with tab_insights:
    insights.render(store)
with tab_history:
    history.render(store)
with tab_profile:
    profile.render(store)

with st.expander("How matching works"):
    st.markdown(
        "- Your phrase is first sent to **CalorieNinjas**, which splits it into foods and amounts.\n"
        "- If it has no answer, we search **USDA FoodData Central** and rank the results with a rule-based scorer "
        "(it prefers names that start with your words, cooked over raw for prepared foods, and rejects implausible calories).\n"
        "- The **match badges** (High / Medium / Low) come from that score. They are hints, not guarantees. "
        "If a match looks wrong, open **Not right? Pick another match** and choose the right food.")
st.markdown('<p class="np-muted">Nutrition data: <a href="https://fdc.nal.usda.gov/">USDA FoodData Central</a> and '
            '<a href="https://calorieninjas.com/">CalorieNinjas</a>. Values are estimates for general information only and are '
            "<b>not medical or dietary advice</b>; talk to a qualified professional about your health needs.</p>", unsafe_allow_html=True)

if st.query_params.get("admin") == "1":
    with st.expander("Match feedback (admin)", expanded=True):
        try:
            fs = feedback.summary()
            st.write(f"API calls this server process: {stats.api_calls} made, {stats.cache_hits} served from cache "
                     f"({stats.hit_rate:.0%} hit rate). Match corrections logged: {feedback.choice_count()}.")
            if fs["total"] == 0:
                st.info("No thumbs recorded yet.")
            else:
                st.metric("Match-confirmed rate", f"{fs['confirmed_rate']:.0%}", help=f"{fs['up']} up of {fs['total']} votes")
                st.caption("Small samples from a few users are not a reliable accuracy estimate.")
                st.dataframe([{"source": k, "up": v["up"], "votes": v["total"]} for k, v in fs["by_source"].items()], hide_index=True)
                if fs["recent_down"]:
                    st.dataframe([dict(zip(("time", "query", "source", "fdc_id", "score"), row)) for row in fs["recent_down"]], hide_index=True)
        except Exception as e:
            st.warning(f"Feedback store unavailable: {e}")
