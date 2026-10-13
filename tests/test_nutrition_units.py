import pytest

from nutripulse import nutrition as n


def test_unit_conversions_roundtrip_and_known_values():
    assert n.lb_to_kg(154.324) == pytest.approx(70.0, abs=0.01)
    assert n.kg_to_lb(70) == pytest.approx(154.32, abs=0.01)
    assert n.ftin_to_cm(5, 7) == pytest.approx(170.18)
    assert n.cm_to_ftin(170.18) == (5, 7)


def test_suggest_goal_adjusts_rounds_and_floors():
    assert n.suggest_goal(2136, "maintain") == 2140
    assert n.suggest_goal(2136, "lose") == 1640
    assert n.suggest_goal(2136, "gain") == 2440
    assert n.suggest_goal(1300, "lose") == 1200            # floor


def test_suggest_macros_sums_back_to_calories():
    m = n.suggest_macros(2000)
    assert m["protein"] == 100 and m["carbs"] == 250 and m["fat"] == 67
    assert m["protein"] * 4 + m["carbs"] * 4 + m["fat"] * 9 == pytest.approx(2000, abs=10)
