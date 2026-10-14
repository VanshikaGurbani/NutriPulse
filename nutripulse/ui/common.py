"""Shared UI helpers: identity, store, time of day, formatting, accessible HTML pieces."""
import datetime
import html
import uuid
from zoneinfo import ZoneInfo

import streamlit as st

from nutripulse.store import Store

MEALS = ["Breakfast", "Lunch", "Dinner", "Snack"]
MEAL_ICON = {"Breakfast": "🌅", "Lunch": "☀️", "Dinner": "🌙", "Snack": "🍎"}

# Okabe-Ito colour-blind-safe palette. Colour is never the only cue: every use sits next to a text label.
C_CARBS, C_PROTEIN, C_FAT, C_FIBER, C_KCAL = "#E69F00", "#0072B2", "#CC79A7", "#009E73", "#D55E00"
MACRO_COLORS = {"carbs": C_CARBS, "protein": C_PROTEIN, "fat": C_FAT}

EXERCISES = {
    "Running": 10, "Walking": 4, "Cycling": 8, "Swimming": 9, "Strength training": 5, "HIIT": 12,
    "Yoga / stretching": 3, "Sports / games": 7, "Stair climbing": 9, "Dancing": 5,
}  # kcal per minute (rough, for a typical adult; same figures the app always used)

esc = html.escape


def get_uid() -> str:
    """A private random id kept in the URL (?u=...) so a refresh or bookmark restores the same data."""
    uid = st.query_params.get("u")
    if not uid:
        uid = uuid.uuid4().hex[:16]
        st.query_params["u"] = uid
    return uid


def get_store() -> Store:
    if "np_store" not in st.session_state:
        st.session_state.np_store = Store(get_uid())
    return st.session_state.np_store


def now_local() -> datetime.datetime:
    tz = getattr(st.context, "timezone", None)
    try:
        return datetime.datetime.now(ZoneInfo(tz)) if tz else datetime.datetime.now()
    except Exception:
        return datetime.datetime.now()


def today_str() -> str:
    return now_local().date().isoformat()


def default_meal(now: datetime.datetime | None = None) -> str:
    h = (now or now_local()).hour
    return "Breakfast" if h < 11 else "Lunch" if h < 15 else "Dinner" if 17 <= h < 22 else "Snack"


def fnum(x, digits=0) -> str:
    """Sensible number text: 1,240 (not 1240.00); one decimal only when asked for."""
    return f"{x:,.{digits}f}"


def friendly_day(day: str) -> str:
    d = datetime.date.fromisoformat(day)
    return d.strftime("%a %d %b").replace(" 0", " ")


def muted(text: str) -> None:
    st.markdown(f'<p class="np-muted">{esc(text)}</p>', unsafe_allow_html=True)


def progress_html(label: str, value: float, goal: float | None, unit: str, color: str) -> str:
    """Labelled progress bar. The text carries the numbers, so the colour is decoration."""
    if goal:
        pct = max(0, min(100, round(value / goal * 100)))
        text = f"{fnum(value)} / {fnum(goal)} {unit}"
    else:
        pct, text = 0, f"{fnum(value)} {unit} (no goal set)"
    return (f'<div class="np-prog"><div class="np-prog-row"><span>{esc(label)}</span><span>{text}</span></div>'
            f'<div class="np-bar" role="progressbar" aria-label="{esc(label)}" aria-valuemin="0" aria-valuemax="100" '
            f'aria-valuenow="{pct}"><span style="width:{pct}%;background:{color}"></span></div></div>')


def macro_bar_html(carbs_g: float, protein_g: float, fat_g: float) -> str:
    """Stacked macro bar in calories, legend in the same left-to-right order, with a text value list beside it."""
    parts = [("Carbs", carbs_g * 4, carbs_g, C_CARBS), ("Protein", protein_g * 4, protein_g, C_PROTEIN), ("Fat", fat_g * 9, fat_g, C_FAT)]
    total = sum(p[1] for p in parts)
    if total <= 0:
        return ""
    segs, items, desc = [], [], []
    for name, kcal, grams, color in parts:
        pct = kcal / total * 100
        desc.append(f"{name} {pct:.0f}%")
        label = f"{pct:.0f}%" if pct >= 12 else ""
        segs.append(f'<span class="np-seg" style="width:{pct:.1f}%;background:{color}">{label}</span>')
        items.append(f'<li><span class="np-swatch" style="background:{color}"></span><b>{name}</b> {pct:.0f}% of calories · {fnum(grams)} g</li>')
    return (f'<div class="np-macrobar" role="img" aria-label="Calories from {", ".join(desc)}">{"".join(segs)}</div>'
            f'<ul class="np-legend">{"".join(items)}</ul>')


def badge(text: str, kind: str = "neutral") -> str:
    return f'<span class="np-badge np-{kind}">{esc(text)}</span>'


CONFIDENCE_BADGE = {
    "high": ("● Name closely matches", "good"), "medium": ("◐ Partial name match", "warn"), "low": ("○ Weak name match, check it", "bad"),
    "nlp": ("NLP-parsed", "neutral"), "chosen": ("✓ You chose this", "good"), "sample": ("Sample data", "neutral"),
}


def confidence_badge(conf: str | None) -> str:
    text, kind = CONFIDENCE_BADGE.get(conf or "", ("—", "neutral"))
    return badge(text, kind)
