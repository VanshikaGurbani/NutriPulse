import pytest

from nutripulse import apis
from nutripulse.cache import stats


def food(description, kcal=100.0, data_type="SR Legacy", fdc_id=1):
    return {
        "fdcId": fdc_id, "description": description, "dataType": data_type,
        "foodNutrients": [
            {"nutrientId": 1008, "value": kcal}, {"nutrientId": 1003, "value": 5.0},
            {"nutrientId": 1004, "value": 2.0}, {"nutrientId": 1005, "value": 20.0},
            {"nutrientId": 1079, "value": 1.5},
        ],
    }


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    """No test may touch the network, a real key, or a leftover disk cache."""
    stats.reset()
    apis.configure_cache(None)
    monkeypatch.setenv("USDA_API_KEY", "test-usda-key")
    monkeypatch.setenv("CALORIENINJAS_KEY", "test-cn-key")

    def no_network(*a, **k):
        raise AssertionError("live HTTP call attempted in a test")

    monkeypatch.setattr(apis._http, "get", no_network)
    yield
    apis.configure_cache(None)


def fake_usda(monkeypatch, fn, portions=None):
    """Replace USDA searches (and optionally portion lookups) with fixtures. fn(query, data_type, page_size) -> list of foods."""
    from nutripulse import apis
    monkeypatch.setattr(apis, "usda_fetch_checked", lambda q, dt, page_size=8: (fn(q, dt, page_size), False))
    monkeypatch.setattr(apis, "usda_fetch", lambda q, dt, page_size=8: fn(q, dt, page_size))
    monkeypatch.setattr(apis, "usda_portions", lambda fdc_id: (portions or {}).get(fdc_id, []))
