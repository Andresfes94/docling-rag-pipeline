from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docling.document_converter import ConversionResult

from src.ingestion.profiles import create_converter, load_profiles

_log = logging.getLogger(__name__)


@dataclass
class ConversionOutput:
    document: Any
    source: str
    profile: str
    duration_seconds: float
    json_path: Path | None = None
    md_path: Path | None = None
    txt_path: Path | None = None
    doctags_path: Path | None = None
    page_count: int = 0
    timed_out: bool = False
    error: str | None = None


def convert(
    source: str | Path,
    profile_name: str = "standard",
    output_dir: str | Path = "data/output",
    profiles_path: str | Path = "profiles.yaml",
    timeout_seconds: int = 0,
) -> ConversionOutput:
    profiles = load_profiles(profiles_path)
    converter = create_converter(profile_name, profiles=profiles)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _log.info("Converting %s with profile '%s'...", source, profile_name)
    start = time.time()

    if timeout_seconds > 0:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(converter.convert, source)
            try:
                result: ConversionResult = future.result(timeout=timeout_seconds)
            except TimeoutError:
                duration = time.time() - start
                _log.warning("Conversion timed out after %ds", timeout_seconds)
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

    doc_filename = result.input.file.stem
    page_count = 0

    try:
        page_count = len(set(
            int(prov.page_no)
            for item, _ in doc.iterate_items()
            for prov in (getattr(item, "prov", None) or [])
            if prov is not None and prov.page_no is not None
        ))
    except Exception:
        _log.warning("Could not determine page count")

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
        "Converted %s in %.2fs → JSON/MD/TXT/doctags in %s",
        source, duration, output_dir,
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
