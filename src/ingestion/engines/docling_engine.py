from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from typing import Any

from docling.document_converter import ConversionResult, DocumentConverter

from src.ingestion.engines.base import ExtractionEngine
from src.ingestion.loader import ConversionOutput
from src.ingestion.profiles import create_converter, load_profiles

_log = logging.getLogger(__name__)


class DoclingEngine(ExtractionEngine):
    name = "docling"
    supported_formats = [".pdf", ".xlsx", ".docx", ".pptx", ".csv", ".html", ".png", ".jpg", ".jpeg"]
    requires_gpu = False
    requires_network = False

    def __init__(self) -> None:
        self._converter: DocumentConverter | None = None

    def convert(
        self,
        source: str | Path,
        profile_name: str = "standard",
        output_dir: str | Path = "data/output",
        profiles_path: str | Path = "profiles.yaml",
        timeout_seconds: int = 0,
        **kwargs: Any,
    ) -> ConversionOutput:
        profiles = load_profiles(profiles_path)
        converter = create_converter(profile_name, profiles=profiles)
        self._converter = converter

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        _log.info("[DoclingEngine] Converting %s with profile '%s'...", source, profile_name)
        start = time.time()

        if timeout_seconds > 0:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(converter.convert, source)
                try:
                    result: ConversionResult = future.result(timeout=timeout_seconds)
                except TimeoutError:
                    duration = time.time() - start
                    _log.warning("[DoclingEngine] Timed out after %ds", timeout_seconds)
                    return ConversionOutput(
                        document=None,
                        source=str(source),
                        profile=profile_name,
                        duration_seconds=duration,
                        timed_out=True,
                        error=f"Timed out after {timeout_seconds}s",
                    )
        else:
            result: ConversionResult = converter.convert(source)

        duration = time.time() - start
        doc = result.document

        if doc is None:
            return ConversionOutput(
                document=None,
                source=str(source),
                profile=profile_name,
                duration_seconds=duration,
                error="Conversion returned no document",
            )

        doc_filename = Path(source).stem
        page_count = 0
        try:
            page_count = len(set(
                int(prov.page_no)
                for item, _ in doc.iterate_items()
                for prov in (getattr(item, "prov", None) or [])
                if prov is not None and prov.page_no is not None
            ))
        except Exception:
            _log.warning("[DoclingEngine] Could not determine page count")

        json_path = output_dir / f"{doc_filename}.json"
        json_path.write_text(
            json.dumps(doc.export_to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        md_path = output_dir / f"{doc_filename}.md"
        md_path.write_text(doc.export_to_markdown(), encoding="utf-8")
        txt_path = output_dir / f"{doc_filename}.txt"
        txt_path.write_text(doc.export_to_markdown(strict_text=True), encoding="utf-8")
        doctags_path = output_dir / f"{doc_filename}.doctags"
        doctags_path.write_text(doc.export_to_doctags(), encoding="utf-8")

        _log.info(
            "[DoclingEngine] Converted %s in %.2fs → JSON/MD/TXT/doctags",
            source, duration,
        )

        return ConversionOutput(
            document=doc,
            source=str(source),
            profile=profile_name,
            duration_seconds=duration,
            json_path=json_path,
            md_path=md_path,
            txt_path=txt_path,
            doctags_path=doctags_path,
            page_count=page_count,
        )

    def can_handle(self, source: str | Path) -> bool:
        ext = Path(source).suffix.lower()
        return ext in self.supported_formats

    def estimate_confidence(self, source: str | Path) -> float:
        from src.ingestion.detector import detect
        try:
            profile = detect(source)
            if profile.is_scanned:
                return 0.6
            if profile.is_born_digital:
                return 0.9
            return 0.7
        except Exception:
            return 0.5
