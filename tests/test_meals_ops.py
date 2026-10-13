"""Synthetic checks of the meal and ops scripts. No reported numbers come from here."""
import pytest

from benchmark import ops_metrics, run_meals
from nutripulse.cache import stats


def test_percentile():
    assert ops_metrics.percentile([1, 2, 3, 4, 5], 50) == 3
    assert ops_metrics.percentile([10, 20], 95) == pytest.approx(19.5)


def test_replay_counts_live_vs_cached(monkeypatch):
    seen = set()

    def fake_lookup(q):
        if q not in seen:
            seen.add(q)
            stats.record_call(5.0)
        else:
            stats.record_hit()
        return "calorieninjas" if q != "b" else "usda_fallback"

    monkeypatch.setattr(ops_metrics, "lookup", fake_lookup)
    stats.reset()
    recs = ops_metrics.replay(["a", "b", "c"], 30)
    live = [r for r in recs if r["live"]]
    assert len(live) == len({r["query"] for r in recs}) and stats.cache_hits == 30 - len(live)
    assert "Operational metrics" in ops_metrics.summarize(recs)


def test_meal_evaluation_and_mape(monkeypatch):
    monkeypatch.setattr(run_meals.apis, "nlp_items", lambda q: [
        {"name": "rice", "serving_size_g": 200, "calories": 260, "protein_g": 5, "carbohydrates_total_g": 57, "fat_total_g": 1}])
    monkeypatch.setattr(run_meals.matching, "search_food", lambda n: {
        "description": "Rice, cooked", "calories": 130, "protein": 2.5, "carbs": 28, "fat": 0.3})
    meal = {"meal_text": "200 g rice", "ingredients": "200 g rice", "ref_kcal": "260", "ref_protein_g": "5",
            "ref_carbs_g": "57", "ref_fat_g": "1", "ref_source": "test"}
    res = run_meals.evaluate([meal])
    cn, us = run_meals.summarize(res, "cn"), run_meals.summarize(res, "usda")
    assert cn["kcal"][0] == pytest.approx(0.0) and us["kcal"][0] == pytest.approx(0.0)
    assert run_meals.worst(res, "cn")[0][0] == pytest.approx(0.0)
