from __future__ import annotations

import hashlib
import logging
from typing import Any

from src.api.metrics import cache_hits, cache_misses
from src.api.state import CacheStore

_log = logging.getLogger(__name__)


class RetrievalCache:
    def __init__(self, capacity: int = 512, ttl: int = 300) -> None:
        self.capacity = capacity
        self.ttl = ttl
        self._store = CacheStore()

    @staticmethod
    def _key(query: str, k: int, sources: tuple[str, ...] | None, model: str, fmt: str) -> str:
        raw = f"{query}|{k}|{sources or 'ALL'}|{model}|{fmt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, query: str, k: int, sources: tuple[str, ...] | None = None, model: str = "", fmt: str = "json") -> Any | None:
        key = self._key(query, k, sources, model, fmt)
        val = self._store.get(key)
        if val is not None:
            cache_hits.inc()
        else:
            cache_misses.inc()
        return val

    def set(self, query: str, k: int, value: Any, sources: tuple[str, ...] | None = None, model: str = "", fmt: str = "json") -> None:
        key = self._key(query, k, sources, model, fmt)
        self._store.set(key, value, ttl=self.ttl)

    def invalidate(self, source: str | None = None) -> None:
        if source is None:
            self._store.invalidate()
            _log.info("Cache fully invalidated")
        else:
            _log.info("Cache invalidated for source=%s", source)
            self._store.invalidate(source=source)

    @property
    def size(self) -> int:
        return self._store.size
