"""Minimal in-process TTL cache for read-heavy lookup endpoints.

Not a distributed cache — a single dict per process is the right amount of
complexity for a read-only API backed by a file that only changes when
`dbt build` reruns.
"""

from __future__ import annotations

import time
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: float = 60.0, max_entries: int = 512):
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._store) >= self._max_entries:
            oldest_key = min(self._store, key=lambda k: self._store[k][0])
            self._store.pop(oldest_key, None)
        self._store[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._store.clear()


hospital_cache = TTLCache(ttl_seconds=60.0)
list_cache = TTLCache(ttl_seconds=30.0)
