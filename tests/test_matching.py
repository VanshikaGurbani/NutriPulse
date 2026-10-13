import pytest

from nutripulse.matching import (
    MAX_SANE_CALORIES, _score, best_match, parse_serving, query_words, search_food, to_result,
)
from tests.conftest import food


def top(query, *descs_kcal):
    foods = [food(d, k) for d, k in descs_kcal]
    return best_match(foods, query)[0]["description"]


@pytest.mark.parametrize("query,candidates,expected", [
    ("oatmeal", [("Bread, oatmeal", 280), ("Oatmeal, cooked, with water", 71)], "Oatmeal, cooked, with water"),
    ("oatmeal", [("Cookies, oatmeal, with raisins", 430), ("Oatmeal, instant, plain", 68)], "Oatmeal, instant, plain"),
    ("rice", [("Rice, white, raw", 360), ("Rice, white, cooked", 130)], "Rice, white, cooked"),
    ("chicken breast", [("Soup, chicken broth", 10), ("Chicken, breast, cooked", 165)], "Chicken, breast, cooked"),
])
def test_scorer_prefers_expected(query, candidates, expected):
    assert top(query, *candidates) == expected


def test_user_specified_raw_disables_cooked_bonus():
    q = query_words("raw rice")
    cooked = _score(food("Rice, cooked"), q)
    raw = _score(food("Rice, raw"), q)
    # with "raw" in the query neither cooked_bonus nor raw_penalty applies, so only word hits/brevity differ
    assert raw > cooked


def test_raw_foods_get_no_cooked_bonus():
    q = query_words("apple")
    diff = _score(food("Apple, raw"), q) - _score(food("Apple, cooked"), q)
    # identical apart from brevity (len("apple, raw") < len("apple, cooked"))
    assert diff == pytest.approx((len("apple, cooked") - len("apple, raw")) / 200)


def test_calorie_sanity_cap_applies_penalty():
    q = query_words("butter")
    sane = _score(food("Butter, salted", MAX_SANE_CALORIES), q)
    insane = _score(food("Butter, salted", MAX_SANE_CALORIES + 1), q)
    assert sane - insane == pytest.approx(50)


def test_wrong_category_penalised_below_proper_match():
    assert top("chicken", ("Soup, noodle, chicken", 40), ("Chicken, roasted", 190)) == "Chicken, roasted"


def test_best_match_returns_score_tuple():
    f, s = best_match([food("Banana, raw")], "banana")
    assert f["description"] == "Banana, raw" and isinstance(s, float)


def test_to_result_flags_low_confidence_when_no_query_word_present():
    r = to_result(food("Completely unrelated"), 9.0, "oatmeal")
    assert r["low_confidence"] is True


def test_to_result_flags_suspicious_calories_and_keeps_fdc_id():
    r = to_result(food("Oil, olive", 884, fdc_id=42), 12.0, "olive oil")
    assert r["fdc_id"] == 42 and r["calories"] == 884.0 and r["suspicious_calories"] is False
    assert to_result(food("Oil", 999), 12.0, "oil")["suspicious_calories"] is True


def test_search_food_pipeline_with_fixture(monkeypatch):
    from nutripulse import apis
    pages = {"Foundation": [], "Survey (FNDDS)": [food("Bread, oatmeal", 280, fdc_id=1)],
             "SR Legacy": [food("Oatmeal, cooked", 71, fdc_id=2)]}
    monkeypatch.setattr(apis, "usda_fetch", lambda q, dt, page_size=8: pages.get(dt, []))
    assert search_food("oatmeal")["fdc_id"] == 2


def test_search_food_returns_none_when_nothing_found(monkeypatch):
    from nutripulse import apis
    monkeypatch.setattr(apis, "usda_fetch", lambda *a, **k: [])
    assert search_food("zzzz") is None


@pytest.mark.parametrize("text,expected", [
    ("2 cups oatmeal", (2.0, "cup", "oatmeal")),
    ("1.5 oz chicken", (1.5, "oz", "chicken")),
    ("1/2 cup of rice", (0.5, "cup", "rice")),
    ("3 tbsp peanut butter", (3.0, "tbsp", "peanut butter")),
    ("100g salmon", (100.0, "g", "salmon")),
    ("2 slices bread", (2.0, "slice", "bread")),
    ("banana", (100.0, "g", "banana")),
    ("4 lbs beef", (4.0, "lb", "beef")),
    ("pizza!!", (100.0, "g", "pizza")),
])
def test_parse_serving(text, expected):
    assert parse_serving(text) == expected


def test_weights_default_reproduces_score_and_zero_weight_disables_term():
    from nutripulse.matching import ABLATION_GROUPS, DEFAULT_WEIGHTS, score_terms
    f = food("Bread, oatmeal", 280)
    q = query_words("oatmeal")
    terms = score_terms(f, q)
    assert _score(f, q) == pytest.approx(sum(DEFAULT_WEIGHTS[k] * v for k, v in terms.items()))
    assert set(DEFAULT_WEIGHTS) >= {t for g in ABLATION_GROUPS.values() for t in g}
    off = dict(DEFAULT_WEIGHTS, first_mismatch=0.0)
    assert _score(f, q, off) - _score(f, q) == pytest.approx(8.0)


def test_parallel_candidate_lists_match_sequential(monkeypatch):
    from nutripulse import apis, matching
    data = {"Foundation": [food("A", 1, fdc_id=1)], "Survey (FNDDS)": [food("B", 2, fdc_id=2)], "SR Legacy": [food("C", 3, fdc_id=3)]}
    monkeypatch.setattr(apis, "usda_fetch", lambda q, dt, page_size=8: data[dt])
    assert matching.candidate_lists("x", parallel=True) == matching.candidate_lists("x", parallel=False)


def test_ranked_candidates_best_first_and_first_equals_best_match(monkeypatch):
    from nutripulse import apis, matching
    foods = [food("Bread, oatmeal", 280, fdc_id=1), food("Oatmeal, cooked", 71, fdc_id=2), food("Cookies, oatmeal", 430, fdc_id=3)]
    monkeypatch.setattr(apis, "usda_fetch", lambda q, dt, page_size=8: foods if dt == "SR Legacy" else [])
    ranked = matching.ranked_candidates("oatmeal", k=2)
    assert [f["fdcId"] for f, _ in ranked][0] == matching.best_match(foods, "oatmeal")[0]["fdcId"] == 2
    assert len(ranked) == 2 and ranked[0][1] >= ranked[1][1]
