from __future__ import annotations

import gc
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.ingestion.loader import ConversionOutput, convert as convert_doc
from src.ingestion.extractor import extract
from src.ingestion.chunker import ChunkingResult, chunk_document
from src.ingestion.quality import QualityReport, evaluate
from src.ingestion.detector import detect
from src.storage.vector_store import VectorStore, RetrievalResult

_log = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    source: str
    profile: str
    conversion: ConversionOutput | None = None
    chunking: ChunkingResult | None = None
    quality: QualityReport | None = None
    vector_count: int = 0
    success: bool = False
    error: str | None = None
    retry_chain: list[str] = field(default_factory=list)
    detector_info: dict[str, Any] | None = None


_OCR_TIMEOUT = 1200
_STANDARD_TIMEOUT = 120


class RAGPipeline:
    def __init__(
        self,
        persist_directory: str | Path = "data/chroma",
        collection_name: str = "documents",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        chunk_max_tokens: int = 512,
        profiles_path: str | Path = "profiles.yaml",
        output_dir: str | Path = "data/output",
        evaluator_script: str | Path = "scripts/docling-evaluate.py",
        fail_on_warn: bool = False,
        auto_retry: bool = True,
    ):
        self._embedding_model = embedding_model
        self._chunk_max_tokens = chunk_max_tokens
        self._profiles_path = Path(profiles_path)
        self._output_dir = Path(output_dir)
        self._evaluator_script = Path(evaluator_script)
        self._fail_on_warn = fail_on_warn
        self._auto_retry = auto_retry
        self._store = VectorStore(
            persist_directory=persist_directory,
            collection_name=collection_name,
        )

    @property
    def store(self) -> VectorStore:
        return self._store

    def ingest(
        self,
        source: str | Path,
        profile: str = "standard",
        skip_quality: bool = False,
    ) -> IngestionResult:
        if profile == "auto":
            return self._ingest_with_detection(source, skip_quality)

        result = self._try_ingest(source, profile, skip_quality)
        if result.success and result.chunking and not result.chunking.empty_document:
            return result

        if not self._auto_retry:
            return result

        return self._retry_chain(source, result, skip_quality)

    def _ingest_with_detection(
        self,
        source: str | Path,
        skip_quality: bool,
    ) -> IngestionResult:
        doc_profile = detect(source)
        suggested = doc_profile.suggested_profile()
        _log.info("Auto-detected profile '%s' for %s", suggested, source)

        result = self._try_ingest(source, suggested, skip_quality)
        result.detector_info = doc_profile.to_dict()

        if result.success and result.chunking and not result.chunking.empty_document:
            return result

        if not self._auto_retry:
            return result

        return self._retry_chain(source, result, skip_quality)

    def _try_ingest(
        self,
        source: str | Path,
        profile: str,
        skip_quality: bool,
        timeout: int = 0,
    ) -> IngestionResult:
        result = IngestionResult(source=str(source), profile=profile)
        _log.info("=== TRY: %s (profile=%s) ===", source, profile)

        if timeout == 0:
            has_ocr = profile.startswith("ocr_") or profile == "ocrmac"
            timeout = _OCR_TIMEOUT if has_ocr else _STANDARD_TIMEOUT

        try:
            conversion = convert_doc(
                source=source,
                profile_name=profile,
                output_dir=self._output_dir,
                profiles_path=self._profiles_path,
                timeout_seconds=timeout,
            )
            result.conversion = conversion

            if conversion.timed_out or conversion.error:
                result.success = False
                result.error = conversion.error or "Timed out"
                return result

            _log.info("Conversion done: %d pages in %.2fs", conversion.page_count, conversion.duration_seconds)

            extracted = extract(conversion.document, source=str(source))
            _log.info(
                "Extracted: %d text items (%d empty), %d tables",
                len(extracted.texts),
                extracted.empty_text_items,
                len(extracted.tables),
            )

            if not skip_quality and conversion.json_path:
                quality = evaluate(
                    json_path=conversion.json_path,
                    markdown_path=conversion.md_path,
                    fail_on_warn=self._fail_on_warn,
                    evaluator_script=self._evaluator_script,
                )
                result.quality = quality
                _log.info("Quality check: %s", quality.status)

            chunking = chunk_document(
                document=conversion.document,
                source=str(source),
                max_tokens=self._chunk_max_tokens,
            )
            result.chunking = chunking
            _log.info(
                "Chunking: %d chunks (avg %d tokens, empty=%s)",
                chunking.total_chunks,
                chunking.avg_tokens,
                chunking.empty_document,
            )

            if chunking.empty_document:
                result.success = False
                result.error = "No text content extracted (document may be scanned or formula-only)"
                return result

            vector_count = self._store.add_document(
                chunks=chunking.chunks,
                source=str(source),
                model_name=self._embedding_model,
            )
            result.vector_count = vector_count
            result.success = True

        except MemoryError:
            _log.exception("Memory error during ingestion")
            gc.collect()
            result.success = False
            result.error = "Out of memory"
        except Exception as exc:
            _log.exception("Ingestion failed for %s", source)
            result.success = False
            result.error = str(exc)

        return result

    def _retry_chain(
        self,
        source: str | Path,
        first_result: IngestionResult,
        skip_quality: bool,
    ) -> IngestionResult:
        chain = [first_result.profile]

        if first_result.conversion and first_result.conversion.timed_out:
            fallbacks = ["large_document", "fast"]
        else:
            fallbacks = ["ocrmac", "ocr_easyocr", "vlm_granite"]

        _log.info("Retry chain: %s -> %s", chain, fallbacks)

        for fb in fallbacks:
            if fb in chain:
                continue

            _log.warning("Retrying %s with profile '%s' (previous: %s)", source, fb, chain[-1])
            result = self._try_ingest(source, fb, skip_quality)
            result.retry_chain = chain + [fb]

            if result.success and result.chunking and not result.chunking.empty_document:
                return result

        _log.error("All retry attempts exhausted for %s", source)
        return first_result

    def retrieve(
        self,
        query: str,
        k: int = 5,
        where: dict | None = None,
    ) -> RetrievalResult:
        return self._store.query(
            query_text=query,
            k=k,
            model_name=self._embedding_model,
            where=where,
        )

    def status(self) -> dict:
        return {
            "document_count": self._store.document_count(),
            "sources": self._store.list_sources(),
            "embedding_model": self._embedding_model,
            "output_dir": str(self._output_dir),
            "auto_retry": self._auto_retry,
        }
