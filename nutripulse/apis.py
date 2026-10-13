"""CalorieNinjas (primary) and USDA FoodData Central (fallback) clients."""
import os
import time

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .cache import DiskCache, stats

load_dotenv()

# Overridable so UI tests can point the app at a local mock server.
USDA_BASE = os.getenv("NUTRIPULSE_USDA_BASE", "https://api.nal.usda.gov/fdc/v1")
CALORIENINJAS_URL = os.getenv("NUTRIPULSE_CN_URL", "https://api.calorieninjas.com/v1/nutrition")
TIMEOUT_S = 10

NUTRIENT_IDS = {"calories": 1008, "protein": 1003, "fat": 1004, "carbs": 1005, "fiber": 1079}

_disk_cache: DiskCache | None = None
_call_budget: int | None = None


class BudgetExceeded(RuntimeError):
    """Raised before a live request would exceed the configured call budget."""


def set_call_budget(max_live_calls: int | None) -> None:
    """Cap live (uncached) requests for this process; None removes the cap."""
    global _call_budget
    _call_budget = max_live_calls


def configure_cache(cache: DiskCache | None) -> None:
    """Scripts call this to route every request through the JSON cache."""
    global _disk_cache
    _disk_cache = cache


def usda_key() -> str | None:
    key = os.getenv("USDA_API_KEY")
    return None if not key or key.startswith("your_") else key


def calorieninjas_key() -> str:
    return os.getenv("CALORIENINJAS_KEY", "")


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",), respect_retry_after_header=True)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


_http = _session()


USDA_400_RETRIES = 4   # USDA intermittently answers 400 (nginx HTML) to valid dataType searches, ~40% for "Survey (FNDDS)"


def _get_json(service: str, url: str, params: dict, headers: dict | None = None, retry_400: int = 0, transform=None):
    """GET with disk-cache lookup, timeout, retries and call accounting.
    retry_400: extra attempts when the server answers 400 (a known USDA flake, not a client error)."""
    if _disk_cache is not None:
        hit = _disk_cache.get(service, params)
        if hit is not None:
            stats.record_hit()
            return hit
    if _call_budget is not None and stats.api_calls >= _call_budget:
        raise BudgetExceeded(f"live API call budget of {_call_budget} reached; "
                             "re-run with a higher --max-calls only after confirming quota")
    for attempt in range(retry_400 + 1):
        if _call_budget is not None and stats.api_calls >= _call_budget:
            raise BudgetExceeded(f"live API call budget of {_call_budget} reached")
        t0 = time.perf_counter()
        resp = _http.get(url, params=params, headers=headers, timeout=TIMEOUT_S)
        stats.record_call((time.perf_counter() - t0) * 1000)
        if resp.status_code != 400 or attempt == retry_400:
            break
        stats.retries += 1
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        stats.errors += 1
        raise
    payload = resp.json()
    if transform:
        payload = transform(payload)
    if _disk_cache is not None:
        _disk_cache.put(service, params, payload)
    return payload


_KEEP_NUTRIENTS = {1008, 2047, 1003, 1004, 1005, 1079}   # kcal, kcal (Atwater), protein, fat, carbs, fiber


def slim_usda(payload: dict) -> dict:
    """Keep only the fields the app and benchmark read, so cached responses stay small."""
    foods = [{"fdcId": f.get("fdcId"), "description": f.get("description", ""), "dataType": f.get("dataType", ""),
              "foodNutrients": [{"nutrientId": n["nutrientId"], "value": n.get("value", 0)}
                                for n in f.get("foodNutrients", []) if n.get("nutrientId") in _KEEP_NUTRIENTS]}
             for f in payload.get("foods", [])]
    return {"foods": foods}


def usda_fetch(query: str, data_type, page_size: int = 8) -> list:
    """USDA /foods/search. HTTP errors yield [] (as the app always did);
    network errors propagate to the caller."""
    params = {"query": query, "api_key": usda_key(), "pageSize": page_size}
    if data_type:
        params["dataType"] = data_type
    try:
        return _get_json("usda", f"{USDA_BASE}/foods/search", params, retry_400=USDA_400_RETRIES,
                         transform=slim_usda).get("foods", [])
    except requests.HTTPError:
        return []


def nlp_items(query: str) -> list | None:
    """Raw CalorieNinjas items for a free-text query, or None if unavailable."""
    key = calorieninjas_key()
    if not key or key.startswith("your_"):
        return None
    try:
        data = _get_json("calorieninjas", CALORIENINJAS_URL, {"query": query},
                         headers={"X-Api-Key": key})
    except BudgetExceeded:
        raise
    except Exception:
        return None
    return data.get("items", []) or None


def search_food_nlp(query: str) -> dict | None:
    """Natural-language lookup. Returns per-100 g values plus serving_g so the
    existing quantity UI works."""
    items = nlp_items(query)
    if not items:
        return None
    try:
        return _summarise_items(items)
    except (KeyError, TypeError, ValueError):
        return None


def _summarise_items(items: list) -> dict:
    total_g = sum(i.get("serving_size_g", 100) for i in items) or 100
    f = 100 / total_g

    def s(field):
        return sum(i.get(field, 0) for i in items) * f

    return {
        "description":         " + ".join(i["name"].title() for i in items),
        "calories":            round(s("calories"), 1),
        "protein":             round(s("protein_g"), 1),
        "carbs":               round(s("carbohydrates_total_g"), 1),
        "fat":                 round(s("fat_total_g"), 1),
        "fiber":               round(s("fiber_g"), 1),
        "sugar":               round(s("sugar_g"), 1),
        "sodium":              round(s("sodium_mg"), 0),
        "serving_g":           round(total_g, 1),
        "source":              "🟢 CalorieNinjas NLP",
        "low_confidence":      False,
        "suspicious_calories": False,
    }
