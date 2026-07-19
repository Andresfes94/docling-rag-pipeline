from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

_log = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS: set[str] = {
    ".pdf", ".xlsx", ".docx", ".pptx", ".csv", ".html", ".png", ".jpg", ".jpeg",
}


def validate_source(source: str, check_reachable: bool = False) -> str | None:
    """Validate an ingest source path or URL.

    Returns an error message string if invalid, or None if valid.
    """
    if not source or not source.strip():
        return "Source cannot be empty"

    if _looks_like_url(source):
        return _validate_url(source, check_reachable)

    return _validate_local_path(source)


def _looks_like_url(source: str) -> bool:
    return bool(re.match(r"^https?://", source.strip()))


def _validate_url(source: str, check_reachable: bool) -> str | None:
    parsed = urlparse(source)
    if not parsed.netloc:
        return f"Invalid URL: '{source}' — missing hostname"

    ext = Path(parsed.path).suffix.lower()
    if ext and re.match(r"^\.[a-z]{2,5}$", ext) and ext not in _SUPPORTED_EXTENSIONS:
        return f"Unsupported file extension '{ext}' in URL. Supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"

    if check_reachable:
        try:
            resp = httpx.head(source, timeout=5.0, follow_redirects=True)
            if resp.status_code >= 400:
                return f"URL returned HTTP {resp.status_code}: '{source}'"
        except httpx.RequestError as e:
            return f"URL not reachable: '{source}' — {e}"

    return None


def _validate_local_path(source: str) -> str | None:
    path = Path(source)

    ext = path.suffix.lower()
    if ext not in _SUPPORTED_EXTENSIONS:
        return f"Unsupported file extension '{ext}'. Supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"

    if not path.exists():
        return f"File not found: '{source}'"

    if not os.access(str(path), os.R_OK):
        return f"File not readable: '{source}'"

    return None
