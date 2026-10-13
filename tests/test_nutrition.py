import pytest

from nutripulse.nutrition import calc_tdee, nutrition_grade, smart_tips

SED = "Sedentary (desk job)"
MOD = "Moderately active (3-5x/week)"


def test_calc_tdee_hand_checked():
    assert calc_tdee("Male", 30, 80, 180, SED) == 2136
    assert calc_tdee("Female", 25, 65, 165, MOD) == 2163


def test_calc_tdee_unknown_activity_defaults_to_moderate():
    assert calc_tdee("Female", 25, 65, 165, "???") == 2163


# macros chosen to score the full 60 pts of protein/fiber/balance, so calories decide the rest
BAL = dict(protein=100, fiber=25, carbs=200, fat=55)


@pytest.mark.parametrize("consumed,grade", [
    (2000, "A"), (2100, "A"), (2200, "A"),     # <=10% off -> 40/32 pts -> >=92
    (2201, "B"), (2400, "B"),                   # <=20% -> 22 pts -> 82
    (2401, "B"), (2700, "B"),                   # <=35% -> 12 pts -> 72
    (2701, "C"),                                # >35% -> 4 pts -> 64
])
def test_grade_calorie_adherence_boundaries(consumed, grade):
    assert nutrition_grade(consumed, 2000, **BAL)[0] == grade


def test_grade_none_when_nothing_logged():
    assert nutrition_grade(0, 2000, 0, 0, 0, 0) == (None, None, None)


def test_grade_d_and_f():
    assert nutrition_grade(1000, 2000, protein=50, fiber=25, carbs=300, fat=10)[0] == "D"   # 4+20+20+5
    assert nutrition_grade(500, 2000, protein=5, fiber=0, carbs=100, fat=10)[0] == "F"


def test_smart_tips_default_and_overage():
    assert smart_tips(0, 0, 0, 2000, 2000, set())[0][1] == "Start logging"
    titles = [t[1] for t in smart_tips(60, 30, 2500, 2000, 2000, {"b", "l"})]
    assert any("over goal" in t for t in titles)
