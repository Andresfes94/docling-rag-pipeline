from __future__ import annotations

import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.api.state import RateLimitStore
from src.api.metrics import rate_limit_hits

_log = logging.getLogger(__name__)


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
        self._store = RateLimitStore()

    @staticmethod
    def _endpoint_limits(path: str) -> tuple[float, int]:
        if path.startswith("/retrieve"):
            return 30.0, 60
        if path.startswith("/ingest"):
            return 2.0, 4
        if path.startswith("/documents"):
            return 60.0, 120
        return 60.0, 120

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        rate, burst = self._endpoint_limits(path)

        key = f"{client_ip}:{path}"
        if not self._store.consume(key, rate, burst):
            rate_limit_hits.labels(endpoint=path).inc()
            retry_after = int(max(1.0, 1.0 / rate))
            _log.warning("Rate limit hit: %s on %s (%.1f req/s)", client_ip, path, rate)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again shortly."},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
