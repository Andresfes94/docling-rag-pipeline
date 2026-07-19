from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

_log = logging.getLogger(__name__)

_REDIS_URL = os.environ.get("REDIS_URL", None)


def _get_redis():
    if _REDIS_URL:
        import redis
        return redis.from_url(_REDIS_URL, decode_responses=True)
    return None


_redis = _get_redis()


class TaskStore:
    """Task state storage — Redis-backed when REDIS_URL is set, in-memory fallback."""

    def __init__(self) -> None:
        self._local: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, task_id: str, data: dict[str, Any]) -> None:
        if _redis:
            _redis.hset(f"tasks:{task_id}", mapping={k: json.dumps(v) if not isinstance(v, str) else v for k, v in data.items()})
            _redis.expire(f"tasks:{task_id}", 3600)
        else:
            with self._lock:
                self._local[task_id] = data

    def get(self, task_id: str) -> dict[str, Any] | None:
        if _redis:
            raw = _redis.hgetall(f"tasks:{task_id}")
            if not raw:
                return None
            return {
                k: json.loads(v) if isinstance(v, str) and (v.startswith("{") or v.startswith("[")) else v
                for k, v in raw.items()
            }
        with self._lock:
            return self._local.get(task_id)


class RateLimitStore:
    """Rate limiter state — Redis INCR+EXPIRE when REDIS_URL is set, in-memory fallback.

    Uses a fixed-window approach: INCR key, EXPIRE key on first increment.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def consume(self, key: str, rate: float, burst: int) -> bool:
        if _redis:
            window = int(max(1.0, burst / rate))
            redis_key = f"rate:{key}:{int(time.time()) // window}"
            count = _redis.incr(redis_key)
            if count == 1:
                _redis.expire(redis_key, window + 1)
            return count <= burst
        return self._consume_local(key, rate, burst)

    def _consume_local(self, key: str, rate: float, burst: int) -> bool:
        with self._lock:
            now = time.monotonic()
            tokens, last_refill = self._buckets.get(key, (float(burst), now))
            elapsed = now - last_refill
            tokens = min(float(burst), tokens + elapsed * rate)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                return True
            return False


class CacheStore:
    """Cache storage — Redis SET+EXPIRE when REDIS_URL is set, in-memory fallback."""

    def __init__(self) -> None:
        self._local: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        if _redis:
            val = _redis.get(f"cache:{key}")
            if val is None:
                return None
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return val
        with self._lock:
            entry = self._local.get(key)
            if entry is None:
                return None
            value, expires = entry
            if time.monotonic() > expires:
                del self._local[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        if _redis:
            raw = json.dumps(value, default=str)
            _redis.setex(f"cache:{key}", ttl, raw)
        else:
            with self._lock:
                self._local[key] = (value, time.monotonic() + ttl)

    def invalidate(self, source: str | None = None) -> None:
        if _redis:
            if source is None:
                for k in _redis.scan_iter("cache:*"):
                    _redis.delete(k)
            else:
                for k in _redis.scan_iter(f"cache:*{source}*"):
                    _redis.delete(k)
        else:
            with self._lock:
                if source is None:
                    self._local.clear()
                else:
                    self._local = {k: v for k, v in self._local.items() if source not in k}

    @property
    def size(self) -> int:
        if _redis:
            count = 0
            for _ in _redis.scan_iter("cache:*"):
                count += 1
                if count > 10000:
                    break
            return count
        with self._lock:
            return len(self._local)
