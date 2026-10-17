"""Insights tab: grade, tips, goal radar, calories by meal, food comparison. Works for any logged day."""
import plotly.graph_objects as go
import streamlit as st

from nutripulse import apis
from nutripulse.nutrition import nutrition_grade, smart_tips
from nutripulse.ui.common import MEALS, esc, fnum, friendly_day, today_str
from nutripulse.ui.today import cached_alternatives, counted

GRADE_COLORS = {"A": "#1b5e3b", "B": "#33691e", "C": "#7a5200", "D": "#a13c00", "F": "#a4262c"}   # white text passes 4.5:1
MEAL_COLORS = {"Breakfast": "#E69F00", "Lunch": "#56B4E9", "Dinner": "#009E73", "Snack": "#CC79A7"}
LAYOUT = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#14261a", size=13))


def _empty_state(store, where: str):
    st.markdown(f'<div class="np-empty"><b>Nothing to show here yet.</b><br>{where} Or look around with a made-up week first.</div>',
                unsafe_allow_html=True)
    if st.button("Load a sample week", key=f"sample_{where[:6]}", help="Adds seven illustrative days you can remove in one tap"):
        store.load_sample_days(today_str(), 7)
        st.session_state.np_toast = ("Sample week loaded. Remove it any time in Profile.", "📊")
        st.rerun(scope="app")


@st.fragment(run_every="5s")
def _tips(store, day: str):
    """Tiny fragment that re-reads water/intake so tips stay fresh after a water tap in the Today tab."""
    t = store.totals(day)
    meals_used = {e["meal"] for e in store.entries(day)}
    for icon, title, body in smart_tips(t["protein"], t["fiber"], t["kcal"], store.settings().get("calorie_goal") or 0, t["water_ml"], meals_used):
        st.markdown(f'<div class="np-tip"><b><span aria-hidden="true">{icon}</span> {esc(title)}</b><br>{esc(body)}</div>', unsafe_allow_html=True)


def _radar(t: dict, s: dict):
    cats = [("Calories", t["kcal"], s.get("calorie_goal")), ("Protein", t["protein"], s.get("goal_protein")),
            ("Carbs", t["carbs"], s.get("goal_carbs")), ("Fat", t["fat"], s.get("goal_fat")), ("Fibre", t["fiber"], s.get("goal_fiber"))]
    cats = [(n, v, g) for n, v, g in cats if g]
    if len(cats) < 3:
        st.markdown('<p class="np-muted">Set a calorie goal and macro goals in Profile to see how today compares with your targets.</p>',
                    unsafe_allow_html=True)
        return
    pcts = [min(round(v / g * 100), 150) for _, v, g in cats]
    names = [c[0] for c in cats]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=pcts + [pcts[0]], theta=names + [names[0]], fill="toself", name="Today",
                                  line=dict(color="#0072B2", width=3), fillcolor="rgba(0,114,178,0.2)"))
    fig.add_trace(go.Scatterpolar(r=[100] * (len(names) + 1), theta=names + [names[0]], name="Target (100%)",
                                  line=dict(color="#444", width=2, dash="dash")))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 150], ticksuffix="%")), height=320, margin=dict(l=40, r=40, t=20, b=40),
                      legend=dict(orientation="h", y=-0.15), **LAYOUT)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('<p class="np-muted">' + " · ".join(f"{n} {p}%" for n, p in zip(names, pcts)) + " of target</p>", unsafe_allow_html=True)


def _by_meal(store, day: str):
    es = store.entries(day)
    data = {m: sum(e["kcal"] for e in es if e["meal"] == m) for m in MEALS}
    data = {m: v for m, v in data.items() if v > 0}
    if not data:
        return
    fig = go.Figure(go.Pie(labels=[f"{m} ({fnum(v)} kcal)" for m, v in data.items()], values=list(data.values()), hole=0.5,
                           marker=dict(colors=[MEAL_COLORS[m] for m in data], line=dict(color="#fff", width=2)),
                           textinfo="percent", textfont=dict(size=14, color="#111"), sort=False))
    fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=10), legend=dict(orientation="h", y=-0.1), **LAYOUT)
    st.plotly_chart(fig, use_container_width=True)


def _compare():
    with st.expander("Compare two foods (per 100 g)"):
        with st.form("np_compare", border=False):
            a = st.text_input("First food", placeholder="e.g. brown rice")
            b = st.text_input("Second food", placeholder="e.g. white rice")
            go_ = st.form_submit_button("Compare", type="primary")
        if go_ and a.strip() and b.strip():
            try:
                with st.spinner("Fetching…"):
                    ra = counted(cached_alternatives, a.strip())
                    rb = counted(cached_alternatives, b.strip())
            except apis.ServiceError as e:
                st.warning(e.user_message)
                return
            if not ra or not rb:
                st.warning("Could not find one of those foods. Try a simpler name.")
                return
            st.session_state.np_cmp = (ra[0], rb[0])
        pair = st.session_state.get("np_cmp")
        if pair:
            x, y = pair
            keys = [("kcal", "Calories (kcal)"), ("carbs", "Carbs (g)"), ("protein", "Protein (g)"), ("fat", "Fat (g)"), ("fiber", "Fibre (g)")]
            fig = go.Figure()
            fig.add_trace(go.Bar(name=x["name"][:30], x=[k[1] for k in keys], y=[x["per100"][k[0]] for k in keys], marker_color="#0072B2"))
            fig.add_trace(go.Bar(name=y["name"][:30], x=[k[1] for k in keys], y=[y["per100"][k[0]] for k in keys], marker_color="#E69F00",
                                 marker_pattern_shape="/"))
            fig.update_layout(barmode="group", height=300, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=1.15), **LAYOUT)
            st.plotly_chart(fig, use_container_width=True)
            rows = "".join(f'<tr><th scope="row">{lab}</th><td class="num">{fnum(x["per100"][k], 1)}</td><td class="num">{fnum(y["per100"][k], 1)}</td></tr>'
                           for k, lab in keys)
            st.markdown(f'<div class="np-scroll"><table class="np-table"><caption>Per 100 g</caption><thead><tr><th scope="col">Nutrient</th>'
                        f'<th scope="col" class="num">{esc(x["name"][:30])}</th><th scope="col" class="num">{esc(y["name"][:30])}</th></tr></thead>'
                        f'<tbody>{rows}</tbody></table></div>', unsafe_allow_html=True)


@st.fragment
def render(store):
    s = store.settings()
    days = sorted({today_str()} | {h["day"] for h in store.history()}, reverse=True)
    day = st.selectbox("Day", days, format_func=lambda d: friendly_day(d) + (" (today)" if d == today_str() else ""), key="np_ins_day")
    t = store.totals(day)
    if t["foods"] == 0:
        _empty_state(store, "Log a food in the Today tab and your grade, tips and charts appear here.")
    else:
        grade, _, msg = nutrition_grade(t["kcal"], s.get("calorie_goal") or 0, t["protein"], t["fiber"], t["carbs"], t["fat"])
        with st.container(border=True):
            st.markdown("**Nutrition grade**")
            c1, c2 = st.columns([1, 4], vertical_alignment="center")
            c1.markdown(f'<div class="np-grade" style="background:{GRADE_COLORS[grade]}" role="img" aria-label="Grade {grade}">{grade}</div>',
                        unsafe_allow_html=True)
            c2.markdown(f"**{msg}**")
            c2.markdown('<p class="np-muted">Based on calorie adherence (needs a calorie goal), protein, fibre and macro balance. '
                        "A rough guide, not a medical assessment.</p>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("**Suggestions**")
            _tips(store, day)
        with st.container(border=True):
            st.markdown("**Nutrients vs your targets**")
            _radar(t, s)
        with st.container(border=True):
            st.markdown("**Calories by meal**")
            _by_meal(store, day)
    _compare()
