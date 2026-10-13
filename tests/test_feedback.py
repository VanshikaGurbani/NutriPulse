import pytest

from nutripulse import feedback


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRIPULSE_DB", str(tmp_path / "fb.sqlite"))


def test_empty_summary_has_no_rate():
    s = feedback.summary()
    assert s["total"] == 0 and s["confirmed_rate"] is None


def test_log_and_rate():
    feedback.log_feedback("oatmeal", "usda", 123, 14.2, 1)
    feedback.log_feedback("oatmeal", "usda", 124, 3.0, -1)
    feedback.log_feedback("rice", "calorieninjas", None, None, 1)
    s = feedback.summary()
    assert (s["up"], s["down"], s["total"]) == (2, 1, 3)
    assert s["confirmed_rate"] == pytest.approx(2 / 3)
    assert s["by_source"]["usda"] == {"up": 1, "total": 2}
    assert s["recent_down"][0][1] == "oatmeal"


def test_rejects_bad_value():
    with pytest.raises(ValueError):
        feedback.log_feedback("x", "usda", 1, 1.0, 0)
