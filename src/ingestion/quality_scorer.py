from __future__ import annotations

import logging
import re
from typing import Any

_log = logging.getLogger(__name__)

_RE_GARBAGE_RUN = re.compile(r"(.)\1{10,}")
_RE_UNICODE_REPLACEMENT = re.compile(r"\ufffd+")
_RE_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RE_NO_WS = re.compile(r"\S{80,}")


def score_page(
    text: str,
    metadata: dict[str, Any] | None = None,
    expected_chars_per_page: int = 500,
) -> float:
    if not text or not text.strip():
        return 0.0

    text_len = len(text)
    density_ratio = min(text_len / max(expected_chars_per_page, 1), 1.5) / 1.5

    garbage_penalty = 0.0

    replacement_matches = _RE_UNICODE_REPLACEMENT.findall(text)
    garbage_penalty += len(replacement_matches) * 10

    for run in _RE_GARBAGE_RUN.findall(text):
        garbage_penalty += len(run) * 0.5

    control_count = len(_RE_CONTROL_CHARS.findall(text))
    garbage_penalty += control_count * 5

    long_no_ws = len(_RE_NO_WS.findall(text))
    garbage_penalty += long_no_ws * 3

    if text_len > 0:
        garbage_ratio = min(garbage_penalty / text_len, 1.0)
    else:
        garbage_ratio = 1.0

    words = text.split()
    if words:
        avg_word_len = sum(len(w) for w in words) / len(words)
        if avg_word_len > 30 or avg_word_len < 1.5:
            garbage_ratio = min(garbage_ratio + 0.2, 1.0)

    score = density_ratio * (1.0 - garbage_ratio)
    return max(0.0, min(round(score, 4), 1.0))


def score_document(
    pages: list[dict[str, Any]],
    expected_chars_per_page: int = 500,
) -> list[float]:
    return [
        score_page(p.get("text", ""), p, expected_chars_per_page)
        for p in pages
    ]


def extract_pages_from_markdown(markdown_text: str) -> list[dict[str, Any]]:
    page_seps = re.split(r"(?<=\n)(?=#|\f)", markdown_text)
    pages: list[dict[str, Any]] = []
    for chunk in page_seps:
        chunk = chunk.strip()
        if chunk:
            pages.append({"text": chunk})
    if not pages and markdown_text.strip():
        pages.append({"text": markdown_text.strip()})
    return pages
