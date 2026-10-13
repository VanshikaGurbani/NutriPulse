"""First-run setup (goal, body stats, done) and the body-stats inputs shared with the Profile tab.

Nothing is pre-filled with example values. A person who skips gets no calorie goal at all (the app then shows
intake without a target) rather than an invented one.
"""
import streamlit as st

from nutripulse.nutrition import (
    ACTIVITY_LEVELS, calc_tdee, cm_to_ftin, ftin_to_cm, kg_to_lb, lb_to_kg, suggest_goal, suggest_macros,
)
from nutripulse.ui.common import fnum, muted

OBJECTIVES = {"Lose weight": "lose", "Maintain my weight": "maintain", "Gain weight": "gain", "Just track what I eat": None}
SEXES = ["Female", "Male"]


def body_stats_inputs(prefix: str, units: str, existing: dict | None = None):
    """Widgets for sex, age, height, weight, activity. Returns (metric_profile | None, [missing field names])."""
    ex = existing or {}
    sex = st.radio("Sex used in the calorie formula", SEXES, horizontal=True, key=f"{prefix}_sex",
                   index=SEXES.index(ex["sex"]) if ex.get("sex") in SEXES else None)
    age = st.number_input("Age (years)", min_value=10, max_value=100, step=1, value=ex.get("age"), key=f"{prefix}_age", placeholder="e.g. 30")
    if units == "metric":
        height_cm = st.number_input("Height (cm)", min_value=100.0, max_value=250.0, step=0.5, value=ex.get("height_cm"),
                                    key=f"{prefix}_h_cm", placeholder="e.g. 170")
        weight_kg = st.number_input("Weight (kg)", min_value=30.0, max_value=250.0, step=0.5, value=ex.get("weight_kg"),
                                    key=f"{prefix}_w_kg", placeholder="e.g. 65")
    else:
        ft0, in0 = cm_to_ftin(ex["height_cm"]) if ex.get("height_cm") else (None, None)
        c1, c2 = st.columns(2)
        ft = c1.number_input("Height (ft)", min_value=3, max_value=8, step=1, value=ft0, key=f"{prefix}_h_ft", placeholder="5")
        inch = c2.number_input("(in)", min_value=0, max_value=11, step=1, value=in0, key=f"{prefix}_h_in", placeholder="7")
        height_cm = ftin_to_cm(ft, inch) if ft is not None and inch is not None else None
        lb = st.number_input("Weight (lb)", min_value=66.0, max_value=550.0, step=1.0,
                             value=round(kg_to_lb(ex["weight_kg"]), 1) if ex.get("weight_kg") else None, key=f"{prefix}_w_lb", placeholder="e.g. 145")
        weight_kg = lb_to_kg(lb) if lb is not None else None
    levels = list(ACTIVITY_LEVELS)
    activity = st.selectbox("Activity level", levels, key=f"{prefix}_act", index=levels.index(ex["activity"]) if ex.get("activity") in levels else None,
                            placeholder="Choose one")
    missing = [n for n, v in (("sex", sex), ("age", age), ("height", height_cm), ("weight", weight_kg), ("activity level", activity)) if v is None]
    if missing:
        return None, missing
    return {"sex": sex, "age": int(age), "height_cm": round(float(height_cm), 1), "weight_kg": round(float(weight_kg), 1), "activity": activity}, []


def units_control(store, key: str):
    s = store.settings()
    cur = s.get("units", "metric")
    pick = st.segmented_control("Units", ["Metric", "Imperial"], default=cur.title(), key=key, selection_mode="single")
    units = (pick or cur.title()).lower()
    if units != cur:
        store.update_settings(units=units)
    return units


def finish(store, objective, profile, goal):
    """Persist the outcome. goal=None means 'no calorie goal'."""
    upd = {"onboarded": True, "calorie_goal": goal}
    if goal:
        m = suggest_macros(goal)
        upd.update(goal_protein=m["protein"], goal_carbs=m["carbs"], goal_fat=m["fat"], goal_fiber=m["fiber"])
    store.update_settings(**upd)
    if profile:
        store.set_profile(profile)


def render(store, compact: bool = False):
    """The setup card. Shows nothing once onboarding is finished or skipped."""
    if store.settings().get("onboarded"):
        return
    ss = st.session_state
    step = ss.setdefault("ob_step", 1)
    with st.container(border=True):
        st.markdown(f'<p class="np-step">Quick setup · step {step} of 3 (optional)</p>', unsafe_allow_html=True)
        if step == 1:
            st.markdown("**What is your goal?**")
            pick = st.radio("Goal", list(OBJECTIVES), key="ob_goal", index=None, label_visibility="collapsed")
            c1, c2 = st.columns(2)
            if c1.button("Next", type="primary", key="ob_next1", use_container_width=True, disabled=pick is None):
                ss.ob_objective = OBJECTIVES[pick]
                if ss.ob_objective is None:
                    finish(store, None, None, None)
                    ss.pop("ob_step", None)
                    st.rerun(scope="app")
                ss.ob_step = 2
                st.rerun(scope="fragment")
            if c2.button("Skip setup", key="ob_skip1", use_container_width=True):
                finish(store, None, None, None)
                st.rerun(scope="app")
        elif step == 2:
            st.markdown("**About you**")
            muted("Used only to estimate your daily calories (Mifflin-St Jeor). Stored under your private link.")
            units = units_control(store, "ob_units")
            profile, missing = body_stats_inputs("ob", units, store.profile())
            c1, c2, c3 = st.columns(3)
            if c1.button("Back", key="ob_back2", use_container_width=True):
                ss.ob_step = 1
                st.rerun(scope="fragment")
            if c2.button("Next", type="primary", key="ob_next2", use_container_width=True):
                if profile is None:
                    st.error("Still needed: " + ", ".join(missing) + ".")
                else:
                    ss.ob_profile = profile
                    ss.ob_step = 3
                    st.rerun(scope="fragment")
            if c3.button("Skip setup", key="ob_skip2", use_container_width=True):
                finish(store, None, None, None)
                st.rerun(scope="app")
        else:
            profile, objective = ss.get("ob_profile"), ss.get("ob_objective", "maintain")
            tdee = calc_tdee(profile["sex"], profile["age"], profile["weight_kg"], profile["height_cm"], profile["activity"])
            suggested = suggest_goal(tdee, objective)
            st.markdown("**Your daily target**")
            muted(f"Estimated maintenance: {fnum(tdee)} kcal/day. For “{objective}” we suggest {fnum(suggested)} kcal/day "
                  f"({'-500' if objective == 'lose' else '+300' if objective == 'gain' else '±0'} kcal from maintenance). "
                  "This is a general estimate, not medical advice. Adjust it freely.")
            goal = st.number_input("Daily calorie goal (kcal)", min_value=800, max_value=6000, step=50, value=suggested, key="ob_goal_val")
            c1, c2 = st.columns(2)
            if c1.button("Back", key="ob_back3", use_container_width=True):
                ss.ob_step = 2
                st.rerun(scope="fragment")
            if c2.button("Finish", type="primary", key="ob_finish", use_container_width=True):
                finish(store, objective, profile, int(goal))
                ss.np_toast = (f"Goal set to {fnum(goal)} kcal/day. You can change it in Profile.", "🎯")
                for k in ("ob_step", "ob_profile", "ob_objective"):
                    ss.pop(k, None)
                st.rerun(scope="app")
