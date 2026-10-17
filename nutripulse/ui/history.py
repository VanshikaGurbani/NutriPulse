"""History tab: days are saved automatically on every change. No manual save step."""
import csv
import io

import plotly.graph_objects as go
import streamlit as st

from nutripulse.ui.common import fnum, friendly_day, muted
from nutripulse.ui.insights import LAYOUT, _empty_state


def _csv(rows: list) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Eaten kcal", "Burned kcal", "Net kcal", "Goal kcal", "Protein g", "Carbs g", "Fat g", "Fibre g", "Water ml", "Foods", "Sample"])
    for r in rows:
        w.writerow([r["day"], r["kcal"], r["burned"], r["net"], r.get("goal") or "", r["protein"], r["carbs"], r["fat"], r["fiber"],
                    r["water_ml"], r["foods"], "yes" if r.get("sample") else ""])
    return buf.getvalue().encode("utf-8")


@st.fragment(run_every="5s")
def _table(store):
    """Refreshes by itself so water/exercise logged in Today shows up without a manual reload."""
    rows = store.history()
    if not rows:
        return
    body = "".join(
        f'<tr><th scope="row">{friendly_day(r["day"])}{" (sample)" if r.get("sample") else ""}</th><td class="num">{fnum(r["kcal"])}</td>'
        f'<td class="num">{fnum(r["burned"])}</td><td class="num">{fnum(r["net"])}</td><td class="num">{fnum(r["goal"]) if r.get("goal") else "–"}</td>'
        f'<td class="num">{fnum(r["protein"])}</td><td class="num">{fnum(r["carbs"])}</td><td class="num">{fnum(r["fat"])}</td>'
        f'<td class="num">{fnum(r["water_ml"])}</td></tr>' for r in reversed(rows[-30:]))
    st.markdown('<div class="np-scroll"><table class="np-table"><caption>Last 30 logged days</caption><thead><tr><th scope="col">Day</th>'
                '<th scope="col" class="num">Eaten kcal</th><th scope="col" class="num">Burned</th><th scope="col" class="num">Net</th>'
                '<th scope="col" class="num">Goal</th><th scope="col" class="num">Protein g</th><th scope="col" class="num">Carbs g</th>'
                '<th scope="col" class="num">Fat g</th><th scope="col" class="num">Water ml</th></tr></thead><tbody>' + body + "</tbody></table></div>",
                unsafe_allow_html=True)


def _trend(rows: list):
    if len(rows) < 2:
        muted("Log a second day to see your calorie trend.")
        return
    days = [friendly_day(r["day"]) for r in rows[-30:]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=days, y=[r["kcal"] for r in rows[-30:]], mode="lines+markers", name="Eaten",
                             line=dict(color="#0072B2", width=3), marker=dict(size=8, symbol="circle")))
    fig.add_trace(go.Scatter(x=days, y=[r["net"] for r in rows[-30:]], mode="lines+markers", name="Net of exercise",
                             line=dict(color="#D55E00", width=2, dash="dot"), marker=dict(size=8, symbol="square")))
    goals = [r.get("goal") for r in rows[-30:]]
    if any(goals):
        fig.add_trace(go.Scatter(x=days, y=goals, mode="lines", name="Goal", line=dict(color="#444", width=2, dash="dash")))
    fig.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0), yaxis_title="kcal", legend=dict(orientation="h", y=1.15), **LAYOUT)
    st.plotly_chart(fig, use_container_width=True)


@st.fragment
def render(store):
    rows = store.history()
    if not rows:
        _empty_state(store, "Days are saved automatically as you log food, water and exercise. Nothing to press.")
        return
    muted("Saved automatically each time you log. Sample days are marked.")
    with st.container(border=True):
        st.markdown("**Calorie trend**")
        _trend(rows)
    with st.container(border=True):
        _table(store)
        st.download_button("Download history (CSV)", data=_csv(rows), file_name="nutripulse_history.csv", mime="text/csv")
