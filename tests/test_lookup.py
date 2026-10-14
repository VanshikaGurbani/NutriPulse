import pytest

from nutripulse import apis, lookup
from tests.conftest import food

CN = [{"name": "white rice", "serving_size_g": 200, "calories": 260, "protein_g": 5, "carbohydrates_total_g": 57,
       "fat_total_g": 1, "fiber_g": 1, "sugar_g": 0, "sodium_mg": 2},
      {"name": "carrots", "serving_size_g": 100, "calories": 41, "protein_g": 1, "carbohydrates_total_g": 10,
       "fat_total_g": 0.2, "fiber_g": 3, "sugar_g": 5, "sodium_mg": 70}]


def test_multi_ingredient_query_is_split_not_merged(monkeypatch):
    monkeypatch.setattr(apis, "nlp_items", lambda q: CN)
    r = lookup.lookup_meal("2 cups white rice and carrots")
    assert r["path"] == "calorieninjas" and [i["name"] for i in r["items"]] == ["White Rice", "Carrots"]
    assert lookup.totals(r["items"])["kcal"] == pytest.approx(301.0)
    assert r["items"][0]["per100"]["kcal"] == pytest.approx(130.0) and r["items"][0]["grams"] == 200


def test_falls_back_to_usda_with_parsed_quantity(monkeypatch):
    monkeypatch.setattr(apis, "nlp_items", lambda q: None)
    monkeypatch.setattr(apis, "usda_fetch", lambda q, dt, page_size=8: [food("Oatmeal, cooked", 71, fdc_id=7)] if dt == "SR Legacy" else [])
    r = lookup.lookup_meal("2 cups oatmeal")
    assert r["path"] == "usda" and r["items"][0]["grams"] == 480.0 and r["items"][0]["fdc_id"] == 7
    assert r["items"][0]["confidence"] in ("high", "medium", "low")


def test_nothing_found_returns_none(monkeypatch):
    monkeypatch.setattr(apis, "nlp_items", lambda q: None)
    monkeypatch.setattr(apis, "usda_fetch", lambda *a, **k: [])
    assert lookup.lookup_meal("zzz") is None


def test_service_error_propagates_from_fallback(monkeypatch):
    monkeypatch.setattr(apis, "nlp_items", lambda q: None)

    def boom(*a, **k):
        raise apis.ServiceError("rate_limit")
    monkeypatch.setattr(apis, "usda_fetch", boom)
    with pytest.raises(apis.ServiceError):
        lookup.lookup_meal("rice")


def test_alternatives_and_swap_keep_amount(monkeypatch):
    pool = [food("Bread, oatmeal", 280, fdc_id=1), food("Oatmeal, cooked", 71, fdc_id=2), food("Cookies, oatmeal", 430, fdc_id=3)]
    monkeypatch.setattr(apis, "usda_fetch", lambda q, dt, page_size=8: pool if dt == "SR Legacy" else [])
    alts = lookup.alternatives("oatmeal", k=3)
    assert [a["fdc_id"] for a in alts][0] == 2 and len(alts) == 3
    item = {"name": "Oatmeal", "grams": 200.0, "per100": {"kcal": 10, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0, "sugar": 0, "sodium": 0},
            "source": "CalorieNinjas", "confidence": "nlp", "fdc_id": None}
    swapped = lookup.swap_match(item, alts[2])
    assert swapped["grams"] == 200.0 and swapped["fdc_id"] == alts[2]["fdc_id"] and swapped["confidence"] == "chosen"
    assert lookup.nutrients_for(swapped)["kcal"] == pytest.approx(alts[2]["per100"]["kcal"] * 2)


def test_to_entry_and_amount_format():
    item = {"name": "Rice", "grams": 416.0, "per100": {k: 10.0 for k in lookup.NUTRIENTS}, "source": "USDA", "fdc_id": 3, "confidence": "high"}
    e = lookup.to_entry(item, "Lunch", "rice")
    assert e["kcal"] == pytest.approx(41.6) and e["meal"] == "Lunch"
    assert lookup.format_amount(416.0) == "416" and lookup.format_amount(0.5) == "0.5" and lookup.format_amount(1234.0) == "1,234"


def test_unstated_weight_is_flagged_not_guessed(monkeypatch):
    monkeypatch.setattr(apis, "nlp_items", lambda q: None)
    monkeypatch.setattr(apis, "usda_fetch", lambda q, dt, page_size=8: [food("Bananas, raw", 89, fdc_id=9)] if dt == "SR Legacy" else [])
    r = lookup.lookup_meal("1 banana")["items"][0]
    assert r["amount_known"] is False and r["grams"] == 100.0 and r["amount_hint"] == "1 banana"
    known = lookup.lookup_meal("150 g banana")["items"][0]
    assert known["amount_known"] is True and known["grams"] == 150.0
    cups = lookup.lookup_meal("2 cups banana")["items"][0]
    assert cups["amount_approx"] is True and cups["grams"] == 480.0
