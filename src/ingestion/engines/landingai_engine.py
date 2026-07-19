from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import requests

from src.ingestion.engines.base import ExtractionEngine
from src.ingestion.loader import ConversionOutput

_log = logging.getLogger(__name__)


class LandingAIEngine(ExtractionEngine):
    name = "landingai"
    supported_formats = [".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".csv"]
    requires_gpu = False
    requires_network = True

    def __init__(self, model: str = "dpt-3-pro-latest"):
        self.model = model
        self.api_key = os.environ.get("LANDINGAI_API_KEY", "")

    def convert(
        self,
        source: str | Path,
        profile_name: str = "standard",
        output_dir: str | Path = "data/output",
        profiles_path: str | Path = "profiles.yaml",
        timeout_seconds: int = 120,
        **kwargs: Any,
    ) -> ConversionOutput:
        if not self.api_key:
            return ConversionOutput(
                document=None,
                source=str(source),
                profile=profile_name,
                duration_seconds=0.0,
                error="LANDINGAI_API_KEY not set",
            )

        _log.info("[LandingAI] Converting %s (model=%s)...", source, self.model)
        start = time.time()

        try:
            source_path = Path(source)
            if not source_path.is_file():
                return ConversionOutput(
                    document=None,
                    source=str(source),
                    profile=profile_name,
                    duration_seconds=0.0,
                    error=f"File not found: {source}",
                )

            url = "https://api.ade.landing.ai/v2/parse"
            headers = {"Authorization": f"Bearer {self.api_key}"}

            with open(source_path, "rb") as f:
                files = {"document": (source_path.name, f, "application/pdf")}
                data = {"model": self.model}

                resp = requests.post(
                    url,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=timeout_seconds,
                )

            duration = time.time() - start

            if resp.status_code == 401:
                return ConversionOutput(
                    document=None,
                    source=str(source),
                    profile=profile_name,
                    duration_seconds=duration,
                    error="Landing AI API returned 401 — check your LANDINGAI_API_KEY",
                )

            if resp.status_code == 429:
                return ConversionOutput(
                    document=None,
                    source=str(source),
                    profile=profile_name,
                    duration_seconds=duration,
                    error="Landing AI rate limit exceeded",
                )

            if resp.status_code >= 400:
                return ConversionOutput(
                    document=None,
                    source=str(source),
                    profile=profile_name,
                    duration_seconds=duration,
                    error=f"Landing AI API error {resp.status_code}: {resp.text[:500]}",
                )

            result = resp.json()
            md_text = result.get("markdown", "")

            if not md_text:
                return ConversionOutput(
                    document=None,
                    source=str(source),
                    profile=profile_name,
                    duration_seconds=duration,
                    error="Landing AI returned empty markdown",
                )

            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            doc_filename = source_path.stem
            md_path = output_dir / f"{doc_filename}_landingai.md"
            md_path.write_text(md_text, encoding="utf-8")

            pages = _split_markdown_pages(md_text)
            structure = result.get("structure", {})
            page_count = len(structure) if structure else len(pages) or 1

            _log.info(
                "[LandingAI] Converted %s in %.2fs → %d pages",
                source, duration, page_count,
            )

            return ConversionOutput(
                document=None,
                source=str(source),
                profile=profile_name,
                duration_seconds=duration,
                md_path=md_path,
                page_count=page_count,
                markdown_text=md_text,
                pages=pages if pages else [{"text": md_text.strip()}],
            )

        except requests.Timeout:
            duration = time.time() - start
            return ConversionOutput(
                document=None,
                source=str(source),
                profile=profile_name,
                duration_seconds=duration,
                error=f"Landing AI request timed out after {timeout_seconds}s",
            )
        except Exception as exc:
            duration = time.time() - start
            _log.exception("[LandingAI] Failed for %s", source)
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
        return 0.97


def _split_markdown_pages(md_text: str) -> list[dict]:
    import re
    parts = re.split(r"(?<=\n)(?=#|\f)", md_text)
    pages = []
    for p in parts:
        p = p.strip()
        if p:
            pages.append({"text": p})
    return pages
