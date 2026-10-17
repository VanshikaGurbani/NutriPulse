"""Profile tab: body stats (no defaults), goals, units, sample data, and deleting your data."""
import streamlit as st

from nutripulse.nutrition import calc_tdee, suggest_goal, suggest_macros
from nutripulse.ui import onboarding
from nutripulse.ui.common import fnum, muted, today_str


def _stats_section(store):
    with st.container(border=True):
        st.markdown("**About you**")
        muted("Used only to estimate your daily calories (Mifflin-St Jeor). Nothing is pre-filled; leave it empty if you prefer not to say.")
        units = onboarding.units_control(store, "np_units")
        profile, missing = onboarding.body_stats_inputs("pf", units, store.profile())
        if st.button("Save body stats", type="primary", key="pf_save"):
            if profile is None:
                st.error("Still needed: " + ", ".join(missing) + ".")
            else:
                store.set_profile(profile)
                st.session_state.np_toast = ("Body stats saved.", "✅")
                st.rerun(scope="fragment")
        saved = store.profile()
        if saved:
            tdee = calc_tdee(saved["sex"], saved["age"], saved["weight_kg"], saved["height_cm"], saved["activity"])
            st.markdown(f"**Estimated daily need: {fnum(tdee)} kcal** (maintenance)")
            c1, c2, c3 = st.columns(3)
            for col, obj, label in ((c1, "lose", "Use for losing"), (c2, "maintain", "Use for maintaining"), (c3, "gain", "Use for gaining")):
                g = suggest_goal(tdee, obj)
                if col.button(f"{label}: {fnum(g)}", key=f"pf_goal_{obj}", use_container_width=True):
                    m = suggest_macros(g)
                    store.update_settings(calorie_goal=g, goal_protein=m["protein"], goal_carbs=m["carbs"], goal_fat=m["fat"], goal_fiber=m["fiber"],
                                          onboarded=True)
                    st.session_state.np_toast = (f"Calorie goal set to {fnum(g)} kcal/day.", "🎯")
                    st.rerun(scope="app")


def _goal_section(store):
    s = store.settings()
    with st.container(border=True):
        st.markdown("**Daily goals**")
        muted("Leave a goal empty to track without a target. Suggested macros use a 20% protein / 50% carbs / 30% fat split of your calorie goal.")
        with st.form("pf_goals", border=False):
            kcal = st.number_input("Calorie goal (kcal)", min_value=800, max_value=6000, step=50, value=s.get("calorie_goal"), placeholder="No goal")
            sug = suggest_macros(kcal) if kcal else {}
            c1, c2 = st.columns(2)
            prot = c1.number_input("Protein (g)", min_value=10, max_value=500, step=5, value=s.get("goal_protein"), placeholder=f"suggested {sug.get('protein', '–')}")
            carbs = c2.number_input("Carbs (g)", min_value=10, max_value=800, step=10, value=s.get("goal_carbs"), placeholder=f"suggested {sug.get('carbs', '–')}")
            c3, c4 = st.columns(2)
            fat = c3.number_input("Fat (g)", min_value=10, max_value=300, step=5, value=s.get("goal_fat"), placeholder=f"suggested {sug.get('fat', '–')}")
            fiber = c4.number_input("Fibre (g)", min_value=5, max_value=100, step=1, value=s.get("goal_fiber"), placeholder="suggested 25")
            water = st.number_input("Water goal (ml)", min_value=500, max_value=6000, step=250, value=s.get("water_goal_ml", 2000))
            saved = st.form_submit_button("Save goals", type="primary")
        if saved:
            store.update_settings(calorie_goal=int(kcal) if kcal else None, goal_protein=prot, goal_carbs=carbs, goal_fat=fat, goal_fiber=fiber,
                                  water_goal_ml=int(water), onboarded=True)
            st.session_state.np_toast = ("Goals saved.", "✅")
            st.rerun(scope="app")


def _data_section(store):
    with st.container(border=True):
        st.markdown("**Your data**")
        muted("Your log and settings are stored on the app server under the private link in your address bar. Bookmark this page to come back "
              "to them, and do not share the link. The server may reset its storage after a restart or long inactivity, so download your "
              "history from the History tab if it matters to you.")
        if store.has_sample():
            if st.button("Remove sample data", key="pf_rm_sample"):
                store.clear_sample()
                st.session_state.np_toast = ("Sample data removed.", "🧹")
                st.rerun(scope="app")
        else:
            if st.button("Load a sample week", key="pf_sample"):
                store.load_sample_days(today_str(), 7)
                st.session_state.np_toast = ("Sample week loaded.", "📊")
                st.rerun(scope="app")
        with st.popover("Delete all my data"):
            st.markdown("This removes your log, history, goals and profile from the server. It cannot be undone.")
            sure = st.checkbox("Yes, delete everything", key="pf_wipe_ok")
            if st.button("Delete everything", disabled=not sure, key="pf_wipe"):
                store.wipe_all()
                for k in list(st.session_state):
                    if k.startswith(("np_", "ob_", "pf_")):
                        del st.session_state[k]
                st.session_state.np_toast = ("All your data was deleted.", "🗑️")
                st.rerun(scope="app")


@st.fragment
def render(store):
    _stats_section(store)
    _goal_section(store)
    _data_section(store)
