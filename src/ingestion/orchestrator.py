from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.api.metrics import engine_quality_score, profile_selected_total
from src.ingestion.engines import get_engines_for
from src.ingestion.engines.base import ExtractionEngine
from src.ingestion.loader import ConversionOutput
from src.ingestion.quality_scorer import score_page

_log = logging.getLogger(__name__)

_ESCALATION_CHAIN = ["pymupdf4llm", "docling", "marker", "landingai", "llamaparse"]


@dataclass
class PageResult:
    index: int
    text: str
    engine: str
    confidence: float
    duration_seconds: float = 0.0


@dataclass
class OrchestratorResult:
    source: str
    profile: str
    pages: list[PageResult] = field(default_factory=list)
    total_duration: float = 0.0
    markdown_text: str = ""
    success: bool = False
    error: str | None = None


def orchestrate(
    source: str | Path,
    profile_name: str = "hybrid",
    output_dir: str | Path = "data/output",
    profiles_path: str | Path = "profiles.yaml",
    timeout_seconds: int = 300,
    confidence_threshold: float = 0.8,
    escalation_chain: list[str] | None = None,
) -> OrchestratorResult:
    source = str(source)
    start = time.time()
    result = OrchestratorResult(source=source, profile=profile_name)

    chain = escalation_chain or _ESCALATION_CHAIN
    engines_map: dict[str, ExtractionEngine | None] = {}
    for name in chain:
        engines_map[name] = _resolve_engine(name)

    available = [(n, e) for n, e in engines_map.items() if e is not None]
    if not available:
        result.error = "No extraction engines available"
        return result

    _log.info("[Orchestrator] %s: chain=%s threshold=%.2f", source, [n for n, _ in available], confidence_threshold)

    first_name, first_engine = available[0]
    conv = first_engine.convert(
        source=source, profile_name=profile_name,
        output_dir=output_dir, profiles_path=profiles_path,
        timeout_seconds=timeout_seconds,
    )

    if conv.error or not conv.pages:
        result.error = conv.error or "First engine returned no pages"
        return result

    pages_data: list[dict[str, Any]] = list(conv.pages)

    page_results: list[PageResult | None] = [None] * len(pages_data)

    for i, page in enumerate(pages_data):
        text = page.get("text", "")
        confidence = score_page(text)
        page_results[i] = PageResult(
            index=i, text=text, engine=first_name,
            confidence=confidence, duration_seconds=conv.duration_seconds / max(len(pages_data), 1),
        )

    if confidence_threshold < 1.0:
        for i, pr in enumerate(page_results):
            if pr is not None and pr.confidence < confidence_threshold:
                for eng_name, engine in available[1:]:
                    _log.info(
                        "[Orchestrator] Page %d: confidence=%.2f < %.2f, escalating to '%s'",
                        i, pr.confidence, confidence_threshold, eng_name,
                    )
                    page_conv = engine.convert(
                        source=source, profile_name=profile_name,
                        output_dir=output_dir, profiles_path=profiles_path,
                        timeout_seconds=timeout_seconds,
                    )
                    if page_conv.error:
                        _log.warning("[Orchestrator] Engine '%s' failed for page %d: %s", eng_name, i, page_conv.error)
                        continue

                    if page_conv.pages and i < len(page_conv.pages):
                        new_text = page_conv.pages[i].get("text", "")
                        if new_text:
                            new_conf = score_page(new_text)
                            if new_conf > pr.confidence:
                                page_results[i] = PageResult(
                                    index=i, text=new_text, engine=eng_name,
                                    confidence=new_conf,
                                    duration_seconds=page_conv.duration_seconds / max(len(page_conv.pages), 1),
                                )
                                _log.info(
                                    "[Orchestrator] Page %d: improved to confidence=%.2f with '%s'",
                                    i, new_conf, eng_name,
                                )
                                break

    result.pages = [pr for pr in page_results if pr is not None]

    for pr in result.pages:
        engine_quality_score.labels(engine=pr.engine).observe(pr.confidence)
    profile_selected_total.labels(profile=profile_name, reason="hybrid").inc()

    md_parts: list[str] = []
    for pr in result.pages:
        if pr.text.strip():
            md_parts.append(pr.text.strip())
    result.markdown_text = "\n\n".join(md_parts)
    result.total_duration = time.time() - start
    result.success = len(result.pages) > 0

    _log.info(
        "[Orchestrator] %s: %d pages in %.2fs (confidences: %s)",
        source, len(result.pages), result.total_duration,
        [round(pr.confidence, 2) for pr in result.pages],
    )

    return result


def _resolve_engine(name: str) -> ExtractionEngine | None:
    from src.ingestion.engines import get_engine
    return get_engine(name)
