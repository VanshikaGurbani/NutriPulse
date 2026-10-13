import pytest

from nutripulse.store import Store


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRIPULSE_STATE_DB", str(tmp_path / "state.sqlite"))


def row(name="Rice", kcal=200.0, meal="Lunch", **kw):
    return dict(meal=meal, name=name, query=name, grams=100.0, kcal=kcal, protein=4.0, carbs=40.0, fat=1.0, fiber=1.0,
                sugar=0.0, sodium=0.0, source="USDA", fdc_id=1, confidence="high", **kw)


def test_no_profile_and_no_defaults_on_first_run():
    s = Store("u1")
    assert s.profile() is None and s.settings() == {}


def test_profile_and_settings_roundtrip():
    s = Store("u1")
    s.set_profile({"age": 31, "sex": "Female"})
    s.update_settings(calorie_goal=1800)
    s.update_settings(units="imperial")
    assert s.profile()["age"] == 31 and s.settings() == {"calorie_goal": 1800, "units": "imperial"}


def test_users_are_isolated():
    a, b = Store("a"), Store("b")
    a.add_entries("2026-01-01", [row()])
    assert len(a.entries("2026-01-01")) == 1 and b.entries("2026-01-01") == []


def test_add_delete_restore_and_autosnapshot():
    s = Store("u")
    ids = s.add_entries("2026-01-01", [row(kcal=200), row("Beans", 150)])
    assert s.history_for_day("2026-01-01")["kcal"] == 350          # snapshot saved with no manual step
    removed = s.delete_entries([ids[0]])
    assert len(removed) == 1 and s.history_for_day("2026-01-01")["kcal"] == 150
    s.restore_entries(removed)
    assert s.history_for_day("2026-01-01")["kcal"] == 350
    s.delete_entries([e["id"] for e in s.entries("2026-01-01")])
    assert s.history_for_day("2026-01-01") is None                 # empty day leaves no snapshot


def test_update_grams_scales_nutrition():
    s = Store("u")
    [i] = s.add_entries("2026-01-01", [row(kcal=200)])
    s.update_entry_grams(i, 50.0)
    e = s.entries("2026-01-01")[0]
    assert e["grams"] == 50.0 and e["kcal"] == pytest.approx(100.0) and e["protein"] == pytest.approx(2.0)


def test_water_exercise_in_snapshot_and_net():
    s = Store("u")
    s.add_entries("2026-01-02", [row(kcal=500)])
    s.add_water("2026-01-02", 250)
    s.add_water("2026-01-02", 500)
    s.add_exercise("2026-01-02", "Walking", 30, 120)
    h = s.history_for_day("2026-01-02")
    assert h["water_ml"] == 750 and h["burned"] == 120 and h["net"] == 380
    assert s.add_water("2026-01-02", -10_000) == 0.0                # never negative


def test_favorites_and_recents():
    s = Store("u")
    assert s.toggle_favorite("oatmeal") is True and s.favorites() == ["oatmeal"]
    assert s.toggle_favorite("oatmeal") is False and s.favorites() == []
    for q in ["a", "b", "c", "a"]:
        s.push_recent(q)
    assert s.recents(3)[0] == "a" and len(s.recents(3)) == 3 and len(s.recents(10)) == 3


def test_sample_days_load_and_clear_without_touching_real_data():
    s = Store("u")
    s.add_entries("2026-01-15", [row("Real", 111)])
    s.load_sample_days("2026-02-07", days=7)
    assert s.has_sample() and len(s.history()) == 8
    assert all(h["sample"] for h in s.history() if h["day"] != "2026-01-15")
    s.clear_sample()
    assert not s.has_sample() and [h["day"] for h in s.history()] == ["2026-01-15"]
    assert s.entries("2026-01-15")[0]["name"] == "Real"


def test_empty_uid_rejected():
    with pytest.raises(ValueError):
        Store("")
