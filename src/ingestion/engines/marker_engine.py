from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from src.ingestion.engines.base import ExtractionEngine
from src.ingestion.loader import ConversionOutput

_log = logging.getLogger(__name__)


class MarkerEngine(ExtractionEngine):
    name = "marker"
    supported_formats = [".pdf", ".png", ".jpg", ".jpeg", ".pptx", ".docx", ".xlsx", ".html", ".epub"]
    requires_gpu = False
    requires_network = False

    def __init__(self, use_llm: bool = False, llm_backend: str | None = None):
        self.use_llm = use_llm
        self.llm_backend = llm_backend

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
            from marker.convert import convert_single_pdf
            from marker.models import load_all_models
        except ImportError:
            return ConversionOutput(
                document=None,
                source=str(source),
                profile=profile_name,
                duration_seconds=0.0,
                error="marker-pdf not installed. Run: pip install marker-pdf[full]",
            )

        _log.info("[MarkerEngine] Converting %s (use_llm=%s)...", source, self.use_llm)
        start = time.time()

        try:
            model_lst = load_all_models()
            duration = time.time() - start
            _log.info("[MarkerEngine] Models loaded in %.2fs", duration)
            start = time.time()

            md_text, images, metadata = convert_single_pdf(
                str(source),
                model_lst,
                force_ocr=False,
            )
            duration = time.time() - start

            if not md_text or not md_text.strip():
                return ConversionOutput(
                    document=None,
                    source=str(source),
                    profile=profile_name,
                    duration_seconds=duration,
                    error="Marker returned empty output",
                )

            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            doc_filename = Path(source).stem
            md_path = output_dir / f"{doc_filename}_marker.md"
            md_path.write_text(md_text, encoding="utf-8")

            if images:
                img_dir = output_dir / f"{doc_filename}_marker_images"
                img_dir.mkdir(exist_ok=True)
                for fname, img_data in images.items():
                    (img_dir / fname).write_bytes(img_data)

            pages_raw = _split_markdown_pages(md_text)
            page_count = metadata.get("pages", metadata.get("page_count", len(pages_raw) or 1))

            _log.info(
                "[MarkerEngine] Converted %s in %.2fs → %d pages, %d chars",
                source, duration, page_count, len(md_text),
            )

            return ConversionOutput(
                document=None,
                source=str(source),
                profile=profile_name,
                duration_seconds=duration,
                md_path=md_path,
                page_count=page_count,
                markdown_text=md_text,
                pages=pages_raw if pages_raw else [{"text": md_text.strip()}],
            )

        except Exception as exc:
            duration = time.time() - start
            _log.exception("[MarkerEngine] Failed for %s", source)
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
        return 0.95

    @property
    def requires_gpu(self) -> bool:
        return "TORCH_DEVICE" not in os.environ


def _split_markdown_pages(md_text: str) -> list[dict]:
    import re
    parts = re.split(r"(?<=\n)(?=#|\f)", md_text)
    pages = []
    for p in parts:
        p = p.strip()
        if p:
            pages.append({"text": p})
    return pages
