import json

import pytest
import requests

from nutripulse import apis
from nutripulse.cache import DiskCache, stats


class FakeResp:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status}")

    def json(self):
        return self.payload


def fake_get(monkeypatch, payload, status=200):
    calls = []

    def _get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResp(payload, status)

    monkeypatch.setattr(apis._http, "get", _get)
    return calls


def test_usda_fetch_returns_foods_and_sets_timeout(monkeypatch):
    calls = fake_get(monkeypatch, {"foods": [{"fdcId": 1}]})
    assert apis.usda_fetch("rice", "SR Legacy") == [{"fdcId": 1}]
    assert calls[0]["timeout"] == apis.TIMEOUT_S and calls[0]["params"]["dataType"] == "SR Legacy"
    assert stats.api_calls == 1


def test_usda_http_error_yields_empty_list(monkeypatch):
    fake_get(monkeypatch, {}, status=500)
    assert apis.usda_fetch("rice", None) == []


def test_disk_cache_serves_second_call_and_counts(monkeypatch, tmp_path):
    calls = fake_get(monkeypatch, {"foods": [{"fdcId": 7}]})
    apis.configure_cache(DiskCache(tmp_path))
    assert apis.usda_fetch("rice", "SR Legacy") == apis.usda_fetch("rice", "SR Legacy")
    assert len(calls) == 1
    assert (stats.api_calls, stats.cache_hits, stats.hit_rate) == (1, 1, 0.5)


def test_cache_files_never_contain_api_keys(monkeypatch, tmp_path):
    fake_get(monkeypatch, {"foods": []})
    apis.configure_cache(DiskCache(tmp_path))
    apis.usda_fetch("rice", None)
    blob = "".join(p.read_text(encoding="utf-8") for p in tmp_path.iterdir())
    assert "test-usda-key" not in blob and "api_key" not in blob


def test_cache_key_ignores_api_key():
    a = DiskCache.key("usda", {"query": "x", "api_key": "AAA"})
    b = DiskCache.key("usda", {"query": "x", "api_key": "BBB"})
    assert a == b


def test_disk_cache_ttl_expiry(tmp_path):
    c = DiskCache(tmp_path, ttl_seconds=60)
    c.put("usda", {"query": "x"}, {"v": 1})
    assert c.get("usda", {"query": "x"}) == {"v": 1}
    path = next(tmp_path.iterdir())
    entry = json.loads(path.read_text(encoding="utf-8"))
    entry["saved_at"] -= 120
    path.write_text(json.dumps(entry), encoding="utf-8")
    assert c.get("usda", {"query": "x"}) is None


NINJAS = {"items": [
    {"name": "white rice", "serving_size_g": 200, "calories": 260, "protein_g": 5, "carbohydrates_total_g": 57,
     "fat_total_g": 0.5, "fiber_g": 1, "sugar_g": 0, "sodium_mg": 2},
    {"name": "carrots", "serving_size_g": 100, "calories": 41, "protein_g": 1, "carbohydrates_total_g": 10,
     "fat_total_g": 0.2, "fiber_g": 3, "sugar_g": 5, "sodium_mg": 70},
]}


def test_calorieninjas_normalises_to_per_100g(monkeypatch):
    fake_get(monkeypatch, NINJAS)
    r = apis.search_food_nlp("2 cups white rice and carrots")
    assert r["description"] == "White Rice + Carrots"
    assert r["serving_g"] == 300.0
    assert r["calories"] == pytest.approx((260 + 41) / 3, abs=0.1)


def test_calorieninjas_without_key_returns_none(monkeypatch):
    monkeypatch.setenv("CALORIENINJAS_KEY", "")
    assert apis.search_food_nlp("rice") is None


def test_calorieninjas_errors_return_none(monkeypatch):
    fake_get(monkeypatch, {}, status=429)
    assert apis.search_food_nlp("rice") is None
    fake_get(monkeypatch, {"items": []})
    assert apis.search_food_nlp("rice") is None
    fake_get(monkeypatch, {"items": [{"serving_size_g": 100}]})   # missing "name"
    assert apis.search_food_nlp("rice") is None


def test_call_budget_blocks_live_calls_but_not_cache_hits(monkeypatch, tmp_path):
    fake_get(monkeypatch, {"foods": []})
    apis.configure_cache(DiskCache(tmp_path))
    apis.set_call_budget(1)
    try:
        apis.usda_fetch("rice", None)
        apis.usda_fetch("rice", None)                    # cached: allowed
        with pytest.raises(apis.BudgetExceeded):
            apis.usda_fetch("beans", None)               # would be 2nd live call
        with pytest.raises(apis.BudgetExceeded):
            apis.nlp_items("beans")                      # must not be swallowed as "no result"
    finally:
        apis.set_call_budget(None)


def test_template_placeholder_keys_count_as_missing(monkeypatch):
    monkeypatch.setenv("USDA_API_KEY", "your_usda_api_key_here")
    assert apis.usda_key() is None
