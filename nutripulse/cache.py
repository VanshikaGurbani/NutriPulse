"""Disk JSON cache with TTL, plus counters for API calls made vs served from cache."""
import hashlib
import json
import time
from pathlib import Path


class CallStats:
    """Counts live API calls against cache hits. Never records keys or params."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.api_calls = 0
        self.cache_hits = 0
        self.latencies_ms = []

    def record_call(self, elapsed_ms: float | None = None):
        self.api_calls += 1
        if elapsed_ms is not None:
            self.latencies_ms.append(elapsed_ms)

    def record_hit(self):
        self.cache_hits += 1

    @property
    def lookups(self) -> int:
        return self.api_calls + self.cache_hits

    @property
    def hit_rate(self) -> float:
        return self.cache_hits / self.lookups if self.lookups else 0.0

    def as_dict(self) -> dict:
        return {"api_calls": self.api_calls, "cache_hits": self.cache_hits,
                "lookups": self.lookups, "hit_rate": round(self.hit_rate, 4)}


stats = CallStats()


class DiskCache:
    """One JSON file per request. The key hashes the service and params but
    never the API key, so cache files are safe to commit and share."""

    def __init__(self, directory, ttl_seconds: float | None = None):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds

    @staticmethod
    def key(service: str, params: dict) -> str:
        clean = {k: v for k, v in sorted(params.items()) if k.lower() not in ("api_key", "x-api-key")}
        blob = json.dumps([service, clean], sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:32]

    def _path(self, service: str, params: dict) -> Path:
        return self.dir / f"{service}_{self.key(service, params)}.json"

    def get(self, service: str, params: dict):
        path = self._path(service, params)
        if not path.exists():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if self.ttl is not None and time.time() - entry.get("saved_at", 0) > self.ttl:
            return None
        return entry["payload"]

    def put(self, service: str, params: dict, payload) -> None:
        clean = {k: v for k, v in params.items() if k.lower() not in ("api_key", "x-api-key")}
        entry = {"service": service, "params": clean, "saved_at": time.time(), "payload": payload}
        self._path(service, params).write_text(json.dumps(entry), encoding="utf-8")
