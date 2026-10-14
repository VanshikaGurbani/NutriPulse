"""Headless UI tests with Streamlit's AppTest. Lookups are faked; no network."""
import pytest
from streamlit.testing.v1 import AppTest

from nutripulse import apis, lookup
from nutripulse.store import Store

RICE_CARROTS = {"path": "calorieninjas", "items": [
    {"name": "White Rice", "query_name": "white rice", "grams": 200.0, "source": "CalorieNinjas", "source_detail": "NLP-parsed",
     "confidence": "nlp", "fdc_id": None, "score": None,
     "per100": {"kcal": 130.0, "protein": 2.5, "carbs": 28.0, "fat": 0.3, "fiber": 0.4, "sugar": 0.0, "sodium": 1.0}},
    {"name": "Carrots", "query_name": "carrots", "grams": 100.0, "source": "CalorieNinjas", "source_detail": "NLP-parsed",
     "confidence": "nlp", "fdc_id": None, "score": None,
     "per100": {"kcal": 41.0, "protein": 0.9, "carbs": 9.6, "fat": 0.2, "fiber": 2.8, "sugar": 4.7, "sodium": 69.0}}]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRIPULSE_STATE_DB", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("NUTRIPULSE_DB", str(tmp_path / "fb.sqlite"))
    monkeypatch.setenv("USDA_API_KEY", "k-usda-test")
    monkeypatch.setattr(lookup, "lookup_meal", lambda q, parallel=True: RICE_CARROTS if "rice" in q else None)
    # st.cache_data keeps results between tests, so clear it
    import streamlit as st
    st.cache_data.clear()
    # Streamlit 1.48's AppTest cannot serialise a single-select segmented control whose value is None
    # (a real browser can). Normalise it here; this touches test tooling only.
    from streamlit.testing.v1.element_tree import ButtonGroup

    def indices(self):
        v = self.value
        vs = [] if v is None else v if isinstance(v, (list, tuple)) else [v]
        return [self.options.index(self.format_func(x)) for x in vs]
    monkeypatch.setattr(ButtonGroup, "indices", property(indices))


def app(uid="user-ui-test"):
    at = AppTest.from_file("nutrition_tracker.py", default_timeout=60)
    at.query_params["u"] = uid
    return at


def search(at, text):
    at.run()
    at.text_input(key="np_q").set_value(text)
    at.button[0].click()    # the form's Search button
    return at.run()


def test_first_load_is_clean_and_search_comes_first(env):
    at = app().run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Today", "Insights", "History", "Profile"]
    assert at.text_input(key="np_q") is not None
    assert Store("user-ui-test").profile() is None                  # nothing pre-filled


def test_multi_ingredient_search_shows_breakdown_and_adds_to_log(env):
    at = search(app(), "2 cups white rice and carrots")
    assert not at.exception
    html = "".join(m.value for m in at.markdown)
    assert "Ingredients found" in html and "White Rice" in html and "Carrots" in html and "416.00" not in html
    add = next(b for b in at.button if b.label.startswith("Add to "))
    add.click()
    at.run()
    assert not at.exception
    es = Store("user-ui-test").entries(__import__("datetime").date.today().isoformat())
    assert [e["name"] for e in es] == ["White Rice", "Carrots"] and round(sum(e["kcal"] for e in es)) == 301


def test_log_survives_a_fresh_session_with_same_link(env):
    at = search(app(), "rice")
    next(b for b in at.button if b.label.startswith("Add to ")).click()
    at.run()
    at2 = app().run()                                               # "refresh": brand new session, same ?u=
    assert any("White Rice" in m.value for m in at2.markdown)
    other = app("someone-else").run()
    assert not any("White Rice" in m.value for m in other.markdown)


def test_no_result_gives_friendly_message(env):
    at = search(app(), "zzzz")
    assert any("No match" in w.value for w in at.warning)


def test_rate_limit_gives_friendly_message(env, monkeypatch):
    def boom(q, parallel=True):
        raise apis.ServiceError("rate_limit")
    monkeypatch.setattr(lookup, "lookup_meal", boom)
    at = search(app(), "rice")
    assert not at.exception and any("busy" in w.value for w in at.warning)


def test_empty_search_is_rejected_politely(env):
    at = app().run()
    at.button[0].click()
    at.run()
    assert any("Type what you ate" in w.value for w in at.warning)


def test_sample_week_fills_insights_and_history(env):
    at = app().run()
    next(b for b in at.button if b.label == "Load a sample week").click()
    at.run()
    assert not at.exception
    assert Store("user-ui-test").has_sample() and len(Store("user-ui-test").history()) == 7
    html = "".join(m.value for m in at.markdown)
    assert "Nutrition grade" in html and "Calorie trend" in html


def test_skip_setup_leaves_no_goal(env):
    at = app().run()
    next(b for b in at.button if b.label == "Skip setup").click()
    at.run()
    s = Store("user-ui-test").settings()
    assert s["onboarded"] is True and s["calorie_goal"] is None and Store("user-ui-test").profile() is None


def test_unknown_weight_blocks_add_until_confirmed(env, monkeypatch):
    item = dict(RICE_CARROTS["items"][0], name="Bananas, Raw", query_name="banana", grams=100.0, amount_known=False, amount_hint="1 banana",
                source="USDA", source_detail="🔵 SR Legacy", confidence="high", fdc_id=9, score=12.0)
    monkeypatch.setattr(lookup, "lookup_meal", lambda q, parallel=True: {"path": "usda", "items": [dict(item)]})
    at = search(app(), "1 banana")
    assert not at.exception
    assert any("haven't guessed" in w.value for w in at.warning)
    add = next(b for b in at.button if b.label.startswith("Add to "))
    assert add.disabled
    next(b for b in at.button if b.label == "Keep 100 g").click()
    at.run()
    at.run()    # the app calls st.rerun(scope="fragment") after the click; AppTest does not replay that, a browser does (see e2e_smoke)
    assert not any("haven't guessed" in w.value for w in at.warning)
    assert not next(b for b in at.button if b.label.startswith("Add to ")).disabled


def test_typing_a_weight_also_confirms(env, monkeypatch):
    item = dict(RICE_CARROTS["items"][0], grams=100.0, amount_known=False, amount_hint="2 eggs")
    monkeypatch.setattr(lookup, "lookup_meal", lambda q, parallel=True: {"path": "usda", "items": [dict(item)]})
    at = search(app(), "2 eggs")
    assert next(b for b in at.button if b.label.startswith("Add to ")).disabled
    at.number_input[0].set_value(120.0)
    at.run()
    assert not next(b for b in at.button if b.label.startswith("Add to ")).disabled
