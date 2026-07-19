from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

_log = logging.getLogger(__name__)

_RE_UNICODE_REPLACEMENT = re.compile(r"\ufffd+")
_RE_MULTI_SPACE = re.compile(r" {2,}")
_RE_MULTI_NEWLINE = re.compile(r"\n{3,}")
_RE_LEADING_TRAILING_WS = re.compile(r"^[ \t]+|[ \t]+$", re.MULTILINE)
_RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_RE_URL = re.compile(r"\bhttps?://[^\s<>\"']+|www\.[^\s<>\"']+\b")
_RE_PHONE = re.compile(r"\b\+?\d[\d\s\-().]{7,}\d\b")
_RE_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class TextCleaner:
    def __init__(
        self,
        fix_unicode: bool = True,
        normalize_whitespace: bool = True,
        strip_pii: bool = True,
        min_chunk_chars: int = 20,
        max_chunk_chars: int = 100_000,
        dedup_by_hash: bool = True,
    ):
        self.fix_unicode = fix_unicode
        self.normalize_whitespace = normalize_whitespace
        self.strip_pii = strip_pii
        self.min_chunk_chars = min_chunk_chars
        self.max_chunk_chars = max_chunk_chars
        self.dedup_by_hash = dedup_by_hash

    def clean_text(self, text: str) -> str:
        if not text:
            return text
        if self.fix_unicode:
            text = self._fix_unicode(text)
        if self.normalize_whitespace:
            text = self._normalize_whitespace(text)
        if self.strip_pii:
            text = self._strip_pii(text)
        return text.strip()

    def _fix_unicode(self, text: str) -> str:
        text = _RE_UNICODE_REPLACEMENT.sub("\uFFFD", text)
        text = _RE_CONTROL_CHARS.sub("", text)
        try:
            text = text.encode("utf-8", errors="replace").decode("utf-8")
        except Exception:
            pass
        return text

    def _normalize_whitespace(self, text: str) -> str:
        text = _RE_MULTI_NEWLINE.sub("\n\n", text)
        text = _RE_MULTI_SPACE.sub(" ", text)
        text = _RE_LEADING_TRAILING_WS.sub("", text)
        return text

    def _strip_pii(self, text: str) -> str:
        text = _RE_EMAIL.sub("[EMAIL]", text)
        text = _RE_URL.sub("[URL]", text)
        text = _RE_PHONE.sub("[PHONE]", text)
        return text

    def chunk_hash(self, chunk: Any) -> str:
        raw = (
            getattr(chunk, "contextualized_text", None)
            or getattr(chunk, "text", None)
            or str(chunk)
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def deduplicate(self, chunks: list[Any]) -> list[Any]:
        if not self.dedup_by_hash:
            return chunks
        seen: set[str] = set()
        kept: list[Any] = []
        for c in chunks:
            h = self.chunk_hash(c)
            if h not in seen:
                seen.add(h)
                kept.append(c)
        if len(kept) < len(chunks):
            _log.info("Dedup: removed %d/%d duplicate chunks", len(chunks) - len(kept), len(chunks))
        return kept

    def filter_by_length(self, chunks: list[Any]) -> list[Any]:
        filtered: list[Any] = []
        for c in chunks:
            text = getattr(c, "text", "") or ""
            if len(text) < self.min_chunk_chars and len(text) > 0:
                continue
            if len(text) > self.max_chunk_chars:
                continue
            filtered.append(c)
        removed = len(chunks) - len(filtered)
        if removed:
            _log.info("Length filter: removed %d chunks (min=%d, max=%d)", removed, self.min_chunk_chars, self.max_chunk_chars)
        return filtered

    def process_chunks(self, chunks: list[Any]) -> list[Any]:
        cleaned: list[Any] = []
        for c in chunks:
            text = getattr(c, "text", "") or ""
            ctx = getattr(c, "contextualized_text", "") or ""
            c.text = self.clean_text(text)
            c.contextualized_text = self.clean_text(ctx)
            cleaned.append(c)
        cleaned = self.filter_by_length(cleaned)
        cleaned = self.deduplicate(cleaned)
        if hasattr(cleaned, "_reindex"):
            pass
        for i, c in enumerate(cleaned):
            c.chunk_index = i
        return cleaned
