from __future__ import annotations

import logging
import os
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

_log = logging.getLogger(__name__)

API_KEYS: list[str] = []


def _load_keys() -> None:
    global API_KEYS
    raw = os.environ.get("API_KEY", "")
    multi = os.environ.get("API_KEYS", "")
    keys: list[str] = []
    if raw:
        keys.append(raw)
    if multi:
        keys.extend(k.strip() for k in multi.split(",") if k.strip())
    API_KEYS = keys
    if keys:
        _log.info("API key auth enabled (%d key(s))", len(keys))
    else:
        _log.info("API key auth disabled (set API_KEY or API_KEYS env var)")


_load_keys()


class AuthMiddleware(BaseHTTPMiddleware):
    """Require X-API-Key header on all endpoints except /health and /metrics.

    Reads valid keys from API_KEY (single) or API_KEYS (comma-separated) env vars.
    When neither is set, all requests pass through (auth disabled).
    """

    def __init__(self, app: ASGIApp, public_paths: set[str] | None = None) -> None:
        super().__init__(app)
        self.public_paths = public_paths or {"/health", "/metrics"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not API_KEYS:
            return await call_next(request)

        if request.url.path in self.public_paths:
            return await call_next(request)

        key = request.headers.get("X-API-Key", "")
        if not key:
            raise HTTPException(status_code=401, detail="Missing X-API-Key header")
        if key not in API_KEYS:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return await call_next(request)
