from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from src.ingestion.engines.base import ExtractionEngine
from src.ingestion.loader import ConversionOutput

_log = logging.getLogger(__name__)


class PyMuPDF4LLMEngine(ExtractionEngine):
    name = "pymupdf4llm"
    supported_formats = [".pdf", ".xps", ".epub", ".mobi", ".fb2", ".cbz", ".svg"]
    requires_gpu = False
    requires_network = False

    def convert(
        self,
        source: str | Path,
        profile_name: str = "standard",
        output_dir: str | Path = "data/output",
        profiles_path: str | Path = "profiles.yaml",
        timeout_seconds: int = 0,
        **kwargs: Any,
    ) -> ConversionOutput:
        try:
            import pymupdf4llm
        except ImportError:
            return ConversionOutput(
                document=None,
                source=str(source),
                profile=profile_name,
                duration_seconds=0.0,
                error="pymupdf4llm not installed. Run: pip install pymupdf4llm",
            )

        _log.info("[PyMuPDF4LLM] Converting %s...", source)
        start = time.time()

        try:
            md_text = pymupdf4llm.to_markdown(str(source))
            duration = time.time() - start

            if not md_text or not md_text.strip():
                return ConversionOutput(
                    document=None,
                    source=str(source),
                    profile=profile_name,
                    duration_seconds=duration,
                    error="PyMuPDF4LLM returned empty output",
                )

            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            doc_filename = Path(source).stem
            md_path = output_dir / f"{doc_filename}_pymupdf.md"
            md_path.write_text(md_text, encoding="utf-8")

            pages = _split_markdown_pages(md_text)

            _log.info(
                "[PyMuPDF4LLM] Converted %s in %.2fs → %d pages, %d chars",
                source, duration, len(pages) or 1, len(md_text),
            )

            return ConversionOutput(
                document=None,
                source=str(source),
                profile=profile_name,
                duration_seconds=duration,
                md_path=md_path,
                page_count=len(pages) if pages else 1,
                markdown_text=md_text,
                pages=pages if pages else [{"text": md_text.strip()}],
            )

        except Exception as exc:
            duration = time.time() - start
            _log.exception("[PyMuPDF4LLM] Failed for %s", source)
            return ConversionOutput(
                document=None,
                source=str(source),
                profile=profile_name,
                duration_seconds=duration,
                error=str(exc),
            )

    def can_handle(self, source: str | Path) -> bool:
        ext = Path(source).suffix.lower()
        return ext in self.supported_formats

    def estimate_confidence(self, source: str | Path) -> float:
        return 0.85


def _split_markdown_pages(md_text: str) -> list[dict]:
    import re
    parts = re.split(r"(?<=\n)(?=#|\f)", md_text)
    pages = []
    for p in parts:
        p = p.strip()
        if p:
            pages.append({"text": p})
    return pages
