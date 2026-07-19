from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import requests

from src.ingestion.engines.base import ExtractionEngine
from src.ingestion.loader import ConversionOutput

_log = logging.getLogger(__name__)


class LlamaParseEngine(ExtractionEngine):
    name = "llamaparse"
    supported_formats = [".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg", ".csv", ".html", ".epub"]
    requires_gpu = False
    requires_network = True

    def __init__(self, tier: str = "cost_effective"):
        self.tier = tier
        self.api_key = os.environ.get("LLAMAPARSE_API_KEY", "")

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
                error="LLAMAPARSE_API_KEY not set",
            )

        _log.info("[LlamaParse] Converting %s (tier=%s)...", source, self.tier)
        start = time.time()

        try:
            source_path = Path(source)
            if not source_path.is_file():
                return ConversionOutput(
                    document=None, source=str(source), profile=profile_name,
                    duration_seconds=0.0, error=f"File not found: {source}",
                )

            url = "https://api.cloud.llamaindex.ai/api/v1/parsing/upload"
            headers = {"Authorization": f"Bearer {self.api_key}"}

            with open(source_path, "rb") as f:
                files = {"file": (source_path.name, f)}
                data = {"tier": self.tier}
                resp = requests.post(url, headers=headers, files=files, data=data, timeout=timeout_seconds)

            duration = time.time() - start
            if resp.status_code != 200:
                return ConversionOutput(
                    document=None, source=str(source), profile=profile_name,
                    duration_seconds=duration,
                    error=f"LlamaParse upload error {resp.status_code}: {resp.text[:500]}",
                )

            job_id = resp.json().get("id")
            if not job_id:
                return ConversionOutput(
                    document=None, source=str(source), profile=profile_name,
                    duration_seconds=duration, error="LlamaParse returned no job ID",
                )

            status_url = f"https://api.cloud.llamaindex.ai/api/v1/parsing/job/{job_id}"
            md_text = ""
            poll_start = time.time()
            while time.time() - poll_start < timeout_seconds:
                status_resp = requests.get(status_url, headers=headers, timeout=30)
                if status_resp.status_code == 200:
                    data = status_resp.json()
                    if data.get("status") == "completed":
                        result_url = f"https://api.cloud.llamaindex.ai/api/v1/parsing/job/{job_id}/result/markdown"
                        result_resp = requests.get(result_url, headers=headers, timeout=30)
                        if result_resp.status_code == 200:
                            md_text = result_resp.text
                        break
                time.sleep(3)

            duration = time.time() - start

            if not md_text:
                return ConversionOutput(
                    document=None, source=str(source), profile=profile_name,
                    duration_seconds=duration, error="LlamaParse returned empty or timed out",
                )

            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            md_path = output_dir / f"{source_path.stem}_llamaparse.md"
            md_path.write_text(md_text, encoding="utf-8")

            pages = _split_md_pages(md_text)
            _log.info("[LlamaParse] Converted %s in %.2fs → %d chars", source, duration, len(md_text))

            return ConversionOutput(
                document=None, source=str(source), profile=profile_name,
                duration_seconds=duration, md_path=md_path,
                page_count=len(pages) or 1, markdown_text=md_text,
                pages=pages if pages else [{"text": md_text.strip()}],
            )

        except Exception as exc:
            duration = time.time() - start
            _log.exception("[LlamaParse] Failed for %s", source)
            return ConversionOutput(
                document=None, source=str(source), profile=profile_name,
                duration_seconds=duration, error=str(exc),
            )

    def can_handle(self, source: str | Path) -> bool:
        ext = Path(source).suffix.lower()
        return ext in self.supported_formats

    def estimate_confidence(self, source: str | Path) -> float:
        return 0.96


def _split_md_pages(md_text: str) -> list[dict]:
    import re
    parts = re.split(r"(?<=\n)(?=#|\f)", md_text)
    return [{"text": p.strip()} for p in parts if p.strip()]
