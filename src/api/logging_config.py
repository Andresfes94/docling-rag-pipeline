from __future__ import annotations

import contextvars
import logging
import os
import sys
from typing import Any

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_elapsed_ms: contextvars.ContextVar[float] = contextvars.ContextVar("elapsed_ms", default=0.0)


def set_request_id(rid: str) -> None:
    _request_id.set(rid)


def get_request_id() -> str:
    return _request_id.get()


def set_elapsed_ms(ms: float) -> None:
    _elapsed_ms.set(ms)


def get_elapsed_ms() -> float:
    return _elapsed_ms.get()


LOG_FORMAT = os.environ.get("LOG_FORMAT", "text")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.elapsed_ms = get_elapsed_ms()
        return True


def setup_logging() -> None:
    fmt = os.environ.get("LOG_FORMAT", "text")
    level = os.environ.get("LOG_LEVEL", "INFO").upper()

    if fmt == "json":
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)

        try:
            from pythonjsonlogger import jsonlogger

            formatter = jsonlogger.JsonFormatter(
                fmt="%(timestamp)s %(levelname)s %(name)s %(message)s %(request_id)s %(elapsed_ms)s",
                timestamp=True,
            )
        except ImportError:
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            )

        handler.setFormatter(formatter)
        root = logging.getLogger()
        for h in root.handlers[:]:
            root.removeHandler(h)
        root.addHandler(handler)
        root.setLevel(level)
        root.addFilter(RequestIdFilter())

        uvicorn_access = logging.getLogger("uvicorn.access")
        uvicorn_access.handlers.clear()
        uvicorn_access.addHandler(handler)
        uvicorn_access.addFilter(RequestIdFilter())

    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stdout,
            force=True,
        )

    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("docling").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
