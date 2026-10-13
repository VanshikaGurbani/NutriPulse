"""Today tab: search first, then the result breakdown, a slim summary, the log, water and exercise.

The whole tab is one st.fragment, so widget clicks inside it (chips, amounts, water, exercise, picking a match)
rerun only this tab. Changes that other tabs must show (adding or removing food, undo) call st.rerun(scope="app").
"""
import uuid

import streamlit as st
import streamlit.components.v1 as components

from nutripulse import apis, feedback, lookup
from nutripulse.cache import stats
from nutripulse.nutrition import suggest_macros
from nutripulse.ui import onboarding
from nutripulse.ui.common import (
    EXERCISES, MEAL_ICON, MEALS, C_CARBS, C_FAT, C_FIBER, C_PROTEIN, confidence_badge, badge, default_meal, esc, fnum,
    macro_bar_html, muted, progress_html, today_str,
)

LOOKUP_TTL_S = 3600
_flag = {"ran": False}


@st.cache_data(ttl=LOOKUP_TTL_S, show_spinner=False)
def _cached_lookup(query: str):
    _flag["ran"] = True
    return lookup.lookup_meal(query)


@st.cache_data(ttl=LOOKUP_TTL_S, show_spinner=False)
def cached_alternatives(name: str):
    _flag["ran"] = True
    return lookup.alternatives(name)


def counted(fn, arg):
    """Call a cached lookup and record whether st.cache_data served it (feeds the API-calls-saved counter)."""
    _flag["ran"] = False
    out = fn(arg)
    if not _flag["ran"]:
        stats.record_hit()
    return out


# ── helpers ──────────────────────────────────────────────────────────────────

def _ss():
    return st.session_state


def _queue_search(query: str):
    _ss().np_pending = query.strip()


def _on_chip():
    label = _ss().get("np_chip")
    if label:
        _queue_search(_ss().np_chip_map.get(label, label))
        _ss().np_chip = None


def _toast_after_rerun(msg: str, icon: str = "✅"):
    _ss().np_toast = (msg, icon)


def _focus_search_on_desktop():
    """Focus the search box on load, for mouse/keyboard users only (on touch devices it would pop up the keyboard)."""
    components.html(
        """<script>
        (function () {
          var p = window.parent; if (!p || !p.matchMedia || !p.matchMedia('(pointer: fine)').matches) return;
          var tries = 0, t = setInterval(function () {
            var el = p.document.querySelector('input[aria-label="Food search"]');
            if (el && !p.document.activeElement.matches('input,textarea,select')) { el.focus(); clearInterval(t); }
            if (++tries > 25) clearInterval(t);
          }, 200);
        })();
        </script>""", height=1)


# ── search ───────────────────────────────────────────────────────────────────

def _new_result(query: str, res: dict) -> dict:
    items = []
    for it in res["items"]:
        it = dict(it)
        it["uid"] = uuid.uuid4().hex[:8]
        items.append(it)
    return {"id": uuid.uuid4().hex[:8], "query": query, "path": res["path"], "items": items, "alts": {}}


def run_search(store, query: str):
    first = not _ss().get("np_searched")
    msg = f"Looking up “{query}”…" + (" The first lookup can take a few seconds while the nutrition databases wake up." if first else "")
    _ss().np_error = None
    try:
        with st.spinner(msg):
            res = counted(_cached_lookup, query)
    except apis.ServiceError as e:
        _ss().np_error = e.user_message
        return
    _ss().np_searched = True
    if res is None:
        _ss().np_result = None
        _ss().np_error = (f"No match for “{query}”. Try a simpler name (for example “rice” instead of a brand or recipe), "
                          "or check the spelling.")
        return
    _ss().np_result = _new_result(query, res)
    store.push_recent(query)


def render_search(store):
    with st.form("np_search", clear_on_submit=False, border=False):
        c_in, c_btn = st.columns([5, 1], vertical_alignment="bottom")
        q = c_in.text_input("Food search", placeholder="What did you eat? e.g. 2 cups oatmeal",
                            label_visibility="collapsed", key="np_q")
        submitted = c_btn.form_submit_button("Search", type="primary", use_container_width=True)
    if submitted:
        if q.strip():
            _queue_search(q)
        else:
            _ss().np_error = "Type what you ate first, for example “1 banana” or “2 cups rice”."
    muted("Include an amount if you can (“2 cups rice”). Several foods in one phrase are split into separate ingredients.")

    options, mapping = [], {}
    for f in store.favorites():
        label = f"★ {f}"
        options.append(label)
        mapping[label] = f
    for r in store.recents(8):
        if r not in store.favorites() and len(options) < 10:
            options.append(r)
            mapping[r] = r
    if options:
        _ss().np_chip_map = mapping
        st.pills("Recent and favorite foods", options, selection_mode="single", key="np_chip", on_change=_on_chip,
                 label_visibility="collapsed")


# ── result card ──────────────────────────────────────────────────────────────

def _source_text(it: dict) -> str:
    return it["source"] if it["source"] == "CalorieNinjas" else f"USDA · {it.get('source_detail', '').split(' ', 1)[-1]}"


def _breakdown_table(items: list) -> str:
    rows = []
    for it in items:
        n = lookup.nutrients_for(it)
        rows.append(f'<tr><td>{esc(it["name"])}</td><td class="num">{lookup.format_amount(it["grams"])} g</td>'
                    f'<td class="num">{fnum(n["kcal"])}</td><td>{confidence_badge(it.get("confidence"))}<br>{badge(_source_text(it))}</td></tr>')
    tot = lookup.totals(items)
    rows.append(f'<tr><th scope="row">Total</th><td></td><td class="num"><b>{fnum(tot["kcal"])}</b></td><td></td></tr>')
    return ('<div class="np-scroll"><table class="np-table"><caption>Ingredients found</caption><thead><tr>'
            '<th scope="col">Ingredient</th><th scope="col" class="num">Amount</th><th scope="col" class="num">kcal</th>'
            '<th scope="col">Match and source</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


def _on_thumb(rid: str):
    res = _ss().get("np_result")
    val = _ss().get(f"np_fb_{rid}")
    if not res or res["id"] != rid or val is None:
        return
    for it in res["items"]:
        try:
            feedback.log_feedback(res["query"], "calorieninjas" if it["source"] == "CalorieNinjas" else "usda",
                                  it.get("fdc_id"), it.get("score"), 1 if val == 1 else -1)
        except Exception:
            pass


def _apply_alt(res: dict, it: dict, alt: dict, rank: int):
    try:
        feedback.log_feedback(res["query"], "calorieninjas" if it["source"] == "CalorieNinjas" else "usda", it.get("fdc_id"), it.get("score"), -1)
        feedback.log_choice(res["query"], it["name"], it.get("fdc_id"), alt["fdc_id"], rank)
    except Exception:
        pass
    idx = res["items"].index(it)
    res["items"][idx] = dict(lookup.swap_match(it, alt), uid=it["uid"], alternatives=it.get("alternatives"))
    _ss().np_toast_inline = f"Match updated to “{alt['name']}”."


def _render_item_controls(res: dict, it: dict, many: bool):
    uid = it["uid"]
    low = it.get("confidence") == "low"
    with st.container(border=many):
        if many:
            st.markdown(f"**{esc(it['name'])}**")
        c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
        it["grams"] = c1.number_input(f"Amount of {it['name']} (grams)", min_value=1.0, max_value=5000.0, step=5.0,
                                      value=float(it["grams"]), key=f"np_amt_{res['id']}_{uid}")
        if many and c2.button("Remove", key=f"np_rm_{res['id']}_{uid}", use_container_width=True, help=f"Remove {it['name']} from this meal"):
            res["items"] = [x for x in res["items"] if x["uid"] != uid]
            st.rerun(scope="fragment")
        label = "⚠ Low match: pick another" if low else "Not right? Pick another match"
        with st.expander(label, expanded=low):
            alts = it.get("alternatives") or res["alts"].get(uid)
            if not alts:
                if st.button(f"Show other matches for “{it['query_name']}”", key=f"np_alts_{res['id']}_{uid}"):
                    try:
                        with st.spinner("Searching USDA…"):
                            res["alts"][uid] = counted(cached_alternatives, it["query_name"])
                    except apis.ServiceError as e:
                        st.warning(e.user_message)
                    st.rerun(scope="fragment")
                muted("Lists the five best USDA matches so you can choose the right food.")
            else:
                labels = [f"{a['name']} · {fnum(a['per100']['kcal'])} kcal/100 g · {a['source_detail'].split(' ', 1)[-1]}" for a in alts]
                pick = st.radio("Choose the right match", labels, key=f"np_pick_{res['id']}_{uid}", label_visibility="collapsed")
                if st.button("Use this match", key=f"np_use_{res['id']}_{uid}"):
                    i = labels.index(pick)
                    _apply_alt(res, it, alts[i], i + 1)
                    st.rerun(scope="fragment")


def render_result(store):
    res = _ss().get("np_result")
    if not res:
        return
    items = res["items"]
    with st.container(border=True):
        if not items:
            st.info("All ingredients removed. Search again to start over.")
            return
        st.markdown(f"**{esc(res['query'])}**")
        if _ss().get("np_toast_inline"):
            st.success(_ss().pop("np_toast_inline"))
        for it in items:
            if it.get("confidence") == "low":
                st.warning(f"“{it['name']}” may not be the right food. Open “Pick another match” below to choose a better one.")
        st.markdown(_breakdown_table(items), unsafe_allow_html=True)
        tot = lookup.totals(items)
        st.markdown(macro_bar_html(tot["carbs"], tot["protein"], tot["fat"]), unsafe_allow_html=True)
        muted(f"Protein {fnum(tot['protein'])} g · Carbs {fnum(tot['carbs'])} g · Fat {fnum(tot['fat'])} g · Fibre {fnum(tot['fiber'])} g"
              + (f" · Sugar {fnum(tot['sugar'])} g · Sodium {fnum(tot['sodium'])} mg" if tot["sugar"] or tot["sodium"] else ""))

        for it in items:
            _render_item_controls(res, it, many=len(items) > 1)

        meal = st.segmented_control("Add to meal", MEALS, default=default_meal(), key=f"np_meal_{res['id']}", selection_mode="single")
        meal = meal or default_meal()
        c_add, c_fav = st.columns([3, 2], vertical_alignment="center")
        if c_add.button(f"Add to {meal}", type="primary", use_container_width=True, key=f"np_add_{res['id']}"):
            ids = store.add_entries(today_str(), [lookup.to_entry(it, meal, res["query"]) for it in items])
            _ss().np_undo = {"kind": "added", "ids": ids, "label": f"{res['query']} to {meal}"}
            _toast_after_rerun(f"Added {res['query']} to {meal}. Undo is above the log.")
            _ss().np_result = None
            st.rerun(scope="app")
        fav = res["query"] in store.favorites()
        if c_fav.button("★ Saved" if fav else "☆ Save as favorite", key=f"np_fav_{res['id']}", use_container_width=True):
            store.toggle_favorite(res["query"])
            st.rerun(scope="fragment")
        st.feedback("thumbs", key=f"np_fb_{res['id']}", on_change=_on_thumb, args=(res["id"],))
        muted("Was this the right food? Your thumbs help improve matching.")


# ── summary, log, water, exercise ────────────────────────────────────────────

def render_strip(store):
    s = store.settings()
    t = store.totals(today_str())
    goal = s.get("calorie_goal")
    net = t["net"]
    if goal:
        pct = max(0, min(100, round(net / goal * 100)))
        left = goal - net
        note = f"{fnum(left)} kcal left" if left >= 0 else f"{fnum(-left)} kcal over"
        mark = "✓" if left >= 0 else "▲"
        main = f"{fnum(net)} of {fnum(goal)} kcal"
        color = C_FIBER if left >= goal * 0.25 else "#b36b00" if left >= 0 else "#b3261e"
        bar = (f'<div class="np-bar" role="progressbar" aria-label="Calories today" aria-valuemin="0" aria-valuemax="100" '
               f'aria-valuenow="{pct}"><span style="width:{pct}%;background:{color}"></span></div>')
    else:
        pct, note, mark, bar = 0, "No daily goal set (add one in Profile)", "ⓘ", ""
        main = f"{fnum(net)} kcal today"
    extra = f" · {fnum(t['kcal'])} eaten, {fnum(t['burned'])} burned" if t["burned"] else ""
    macros = []
    for label, key, gkey in (("Protein", "protein", "goal_protein"), ("Carbs", "carbs", "goal_carbs"), ("Fat", "fat", "goal_fat")):
        g = s.get(gkey)
        macros.append(f"<span>{label} {fnum(t[key])}{f' / {fnum(g)}' if g else ''} g</span>")
    st.markdown(f'<div class="np-strip"><div class="np-strip-top"><span class="np-strip-main">{main}</span>'
                f'<span class="np-strip-note">{mark} {note}{extra}</span></div>{bar}'
                f'<div class="np-strip-macros">{"".join(macros)}</div></div>', unsafe_allow_html=True)


def _undo_button(store):
    undo = _ss().get("np_undo")
    if not undo:
        return
    if st.button(f"↩ Undo: {undo['kind']} {undo['label']}", key="np_undo_btn"):
        if undo["kind"] == "added":
            store.delete_entries(undo["ids"])
            _toast_after_rerun("Removed again.", "↩")
        elif undo["kind"] == "deleted":
            store.restore_entries(undo["rows"])
            _toast_after_rerun("Restored.", "↩")
        _ss().np_undo = None
        st.rerun(scope="app")


def render_log(store):
    day = today_str()
    entries = store.entries(day)
    with st.container(border=True):
        st.markdown("**Today's log**")
        _undo_button(store)
        if not entries:
            st.markdown('<div class="np-empty">Nothing logged yet. Search a food above and tap <b>Add</b>.</div>', unsafe_allow_html=True)
            return
        if any(e["sample"] for e in entries):
            st.info("This day contains sample data.")
        for meal in MEALS:
            rows = [e for e in entries if e["meal"] == meal]
            if not rows:
                continue
            kcal = sum(r["kcal"] for r in rows)
            st.markdown(f'<div class="np-meal"><span><span aria-hidden="true">{MEAL_ICON[meal]}</span> {meal}</span><span>{fnum(kcal)} kcal</span></div>',
                        unsafe_allow_html=True)
            st.markdown("".join(f'<div class="np-entry"><span>{esc(r["name"])} <small>{lookup.format_amount(r["grams"])} g</small></span>'
                                f'<span>{fnum(r["kcal"])} kcal</span></div>' for r in rows), unsafe_allow_html=True)
        with st.popover("Edit or remove an item", use_container_width=True):
            labels = {f"{e['meal']} · {e['name']} · {lookup.format_amount(e['grams'])} g": e for e in entries}
            pick = st.selectbox("Item", list(labels))
            e = labels[pick]
            new_g = st.number_input("Amount (grams)", min_value=1.0, max_value=5000.0, step=5.0, value=float(e["grams"]), key=f"np_edit_{e['id']}")
            c1, c2 = st.columns(2)
            if c1.button("Update amount", key=f"np_upd_{e['id']}", use_container_width=True):
                store.update_entry_grams(e["id"], new_g)
                _toast_after_rerun(f"Updated {e['name']}.")
                st.rerun(scope="app")
            if c2.button("Remove item", key=f"np_del_{e['id']}", use_container_width=True):
                removed = store.delete_entries([e["id"]])
                _ss().np_undo = {"kind": "deleted", "rows": removed, "label": e["name"]}
                _toast_after_rerun(f"Removed {e['name']}. Undo is above the log.", "🗑️")
                st.rerun(scope="app")


def render_macros(store):
    s = store.settings()
    t = store.totals(today_str())
    with st.container(border=True):
        st.markdown("**Today's macros**")
        st.markdown(macro_bar_html(t["carbs"], t["protein"], t["fat"]) or '<p class="np-muted">Log a food to see your macro split.</p>',
                    unsafe_allow_html=True)
        st.markdown(progress_html("Protein", t["protein"], s.get("goal_protein"), "g", C_PROTEIN)
                    + progress_html("Carbs", t["carbs"], s.get("goal_carbs"), "g", C_CARBS)
                    + progress_html("Fat", t["fat"], s.get("goal_fat"), "g", C_FAT)
                    + progress_html("Fibre", t["fiber"], s.get("goal_fiber"), "g", C_FIBER), unsafe_allow_html=True)


WATER_OPTIONS = {"−250 ml": -250, "+250 ml": 250, "+500 ml": 500, "+1 L": 1000}


def _on_water(store):
    pick = _ss().get("np_water_pick")
    if pick:
        store.add_water(today_str(), WATER_OPTIONS[pick])
        _ss().np_water_pick = None


def render_water(store):
    s = store.settings()
    goal = s.get("water_goal_ml", 2000)
    ml = store.water(today_str())
    with st.expander(f"Water: {ml / 1000:.1f} of {goal / 1000:.1f} L"):
        st.markdown(progress_html("Water", ml, goal, "ml", "#0072B2"), unsafe_allow_html=True)
        muted(f"About {ml / 250:.1f} glasses of 250 ml. The goal is {fnum(goal)} ml; change it in Profile.")
        st.segmented_control("Add water", list(WATER_OPTIONS), key="np_water_pick", on_change=_on_water, args=(store,))


def render_exercise(store):
    day = today_str()
    ex = store.exercises(day)
    burned = sum(x["kcal"] for x in ex)
    with st.expander(f"Exercise: {fnum(burned)} kcal burned"):
        name = st.selectbox("Activity", list(EXERCISES), key="np_ex_name")
        minutes = st.number_input("Minutes", min_value=1, max_value=300, value=30, step=5, key="np_ex_min")
        kcal = round(EXERCISES[name] * minutes)
        muted(f"Estimated {fnum(kcal)} kcal (rough: {EXERCISES[name]} kcal per minute for a typical adult).")
        if st.button("Log exercise", key="np_ex_add", type="primary"):
            store.add_exercise(day, name, minutes, kcal)
            st.rerun(scope="fragment")
        if ex:
            st.markdown("".join(f'<div class="np-entry"><span>{esc(x["name"])} <small>{fnum(x["minutes"])} min</small></span>'
                                f'<span>{fnum(x["kcal"])} kcal</span></div>' for x in ex), unsafe_allow_html=True)
            labels = {f"{x['name']} · {fnum(x['minutes'])} min": x for x in ex}
            pick = st.selectbox("Remove an activity", list(labels), key="np_ex_rm_pick")
            if st.button("Remove activity", key="np_ex_rm"):
                store.delete_exercise([labels[pick]["id"]])
                st.rerun(scope="fragment")


# ── fragment entry point ─────────────────────────────────────────────────────

@st.fragment
def render(store):
    pending = _ss().pop("np_pending", None)
    render_search(store)
    pending = _ss().pop("np_pending", None) or pending
    if pending:
        run_search(store, pending)
    if _ss().get("np_error"):
        st.warning(_ss().np_error)
    render_strip(store)
    left, right = st.columns([3, 2], gap="large")
    with left:
        render_result(store)
        render_log(store)
    with right:
        onboarding.render(store, compact=True)
        render_macros(store)
        render_water(store)
        render_exercise(store)
    _focus_search_on_desktop()


__all__ = ["render", "cached_alternatives", "counted", "suggest_macros"]
