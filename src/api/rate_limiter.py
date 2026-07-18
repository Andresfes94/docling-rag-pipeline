from __future__ import annotations

import time
import threading
import logging
from collections import defaultdict
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

_log = logging.getLogger(__name__)


class TokenBucket:
    __slots__ = ("rate", "burst", "tokens", "last_refill", "lock")

    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(float(self.burst), self.tokens + elapsed * self.rate)
            self.last_refill = now
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        default_rate: float = 10.0,
        default_burst: int = 20,
    ) -> None:
        super().__init__(app)
        self.default_rate = default_rate
        self.default_burst = default_burst
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _endpoint_limits(path: str) -> tuple[float, int]:
        if path.startswith("/retrieve"):
            return 30.0, 60
        if path.startswith("/ingest"):
            return 2.0, 4
        if path.startswith("/documents"):
            return 60.0, 120
        return 60.0, 120

    def _get_bucket(self, key: str, rate: float, burst: int) -> TokenBucket:
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = TokenBucket(rate, burst)
            return self._buckets[key]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        rate, burst = self._endpoint_limits(path)

        bucket = self._get_bucket(f"{client_ip}:{path}", rate, burst)
        if not bucket.consume():
            retry_after = int(max(1.0, 1.0 / rate))
            _log.warning("Rate limit hit: %s on %s (%.1f req/s)", client_ip, path, rate)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again shortly."},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
