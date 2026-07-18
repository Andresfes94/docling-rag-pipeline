from __future__ import annotations

import hashlib
import threading
import time
import logging
from typing import Any

_log = logging.getLogger(__name__)


class RetrievalCache:
    def __init__(self, capacity: int = 512, ttl: int = 300) -> None:
        self.capacity = capacity
        self.ttl = ttl
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(query: str, k: int, sources: tuple[str, ...] | None, model: str, fmt: str) -> str:
        raw = f"{query}|{k}|{sources or 'ALL'}|{model}|{fmt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, query: str, k: int, sources: tuple[str, ...] | None = None, model: str = "", fmt: str = "json") -> Any | None:
        key = self._key(query, k, sources, model, fmt)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires = entry
            if time.monotonic() > expires:
                del self._store[key]
                return None
            return value

    def set(self, query: str, k: int, value: Any, sources: tuple[str, ...] | None = None, model: str = "", fmt: str = "json") -> None:
        key = self._key(query, k, sources, model, fmt)
        with self._lock:
            if len(self._store) >= self.capacity:
                self._evict_one()
            self._store[key] = (value, time.monotonic() + self.ttl)

    def _evict_one(self) -> None:
        oldest = min(self._store.items(), key=lambda x: x[1][1])
        del self._store[oldest[0]]

    def invalidate(self, source: str | None = None) -> None:
        with self._lock:
            if source is None:
                self._store.clear()
                _log.info("Cache fully invalidated")
            else:
                before = len(self._store)
                self._store = {k: v for k, v in self._store.items() if source not in k}
                _log.info("Cache invalidated for source=%s: %d → %d entries", source, before, len(self._store))

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)
