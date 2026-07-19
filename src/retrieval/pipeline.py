from __future__ import annotations

import contextlib
import gc
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opentelemetry import trace

from src.api.metrics import (
    engine_quality_score,
    pipeline_step_duration_seconds,
    profile_selected_total,
)
from src.ingestion.loader import ConversionOutput, convert as convert_doc
from src.ingestion.extractor import extract
from src.ingestion.chunker import ChunkingResult, chunk_document, chunk_markdown
from src.ingestion.quality import QualityReport, evaluate
from src.ingestion.detector import detect
from src.ingestion.cleaner import TextCleaner
from src.retrieval.reranker import CrossEncoderReranker
from src.retrieval.hybrid_search import BM25Retriever, HybridRetriever
from src.storage.vector_store import RetrievedChunk, VectorStore, RetrievalResult

_log = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)


@contextlib.contextmanager
def _record_step(step: str, profile: str, attrs: dict[str, Any] | None = None):
    start = time.monotonic()
    status = "ok"
    with _tracer.start_as_current_span(f"pipeline.{step}") as span:
        span.set_attribute("profile", profile)
        span.set_attribute("step", step)
        if attrs:
            for k, v in attrs.items():
                span.set_attribute(k, str(v) if not isinstance(v, (bool, int, float)) else v)
        try:
            yield
        except Exception as exc:
            status = "error"
            span.record_exception(exc)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
            raise
        finally:
            elapsed = time.monotonic() - start
            pipeline_step_duration_seconds.labels(step=step, profile=profile, status=status).observe(elapsed)


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
        cleaner: TextCleaner | None = None,
        reranker: CrossEncoderReranker | None = None,
        bm25_retriever: BM25Retriever | None = None,
        hybrid_retriever: HybridRetriever | None = None,
    ):
        self._embedding_model = embedding_model
        self._chunk_max_tokens = chunk_max_tokens
        self._profiles_path = Path(profiles_path)
        self._output_dir = Path(output_dir)
        self._evaluator_script = Path(evaluator_script)
        self._fail_on_warn = fail_on_warn
        self._auto_retry = auto_retry
        self._cleaner = cleaner or TextCleaner()
        self._reranker = reranker
        self._bm25 = bm25_retriever
        self._hybrid = hybrid_retriever
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
        deep: bool = False,
    ) -> IngestionResult:
        profile_selected_total.labels(profile=profile, reason="explicit").inc()

        if profile == "auto":
            return self._ingest_with_detection(source, skip_quality, deep=deep)

        if profile in ("hybrid", "hybrid_accuracy"):
            return self._ingest_hybrid(source, profile, skip_quality, deep=deep)

        result = self._try_ingest(source, profile, skip_quality, deep=deep)
        if result.success and result.chunking and not result.chunking.empty_document:
            return result

        if not self._auto_retry:
            return result

        return self._retry_chain(source, result, skip_quality, deep=deep)

    def _ingest_with_detection(
        self,
        source: str | Path,
        skip_quality: bool,
        deep: bool = False,
    ) -> IngestionResult:
        with _record_step("detect", "auto", {"source": str(source)}):
            doc_profile = detect(source)
            suggested = doc_profile.suggested_profile()
        _log.info("Auto-detected profile '%s' for %s", suggested, source)
        profile_selected_total.labels(profile=suggested, reason="auto").inc()

        result = self._try_ingest(source, suggested, skip_quality, deep=deep)
        result.detector_info = doc_profile.to_dict()

        if result.success and result.chunking and not result.chunking.empty_document:
            return result

        if not self._auto_retry:
            return result

        return self._retry_chain(source, result, skip_quality, deep=deep)

    def _try_ingest(
        self,
        source: str | Path,
        profile: str,
        skip_quality: bool,
        timeout: int = 0,
        deep: bool = False,
    ) -> IngestionResult:
        result = IngestionResult(source=str(source), profile=profile)
        _log.info("=== TRY: %s (profile=%s) ===", source, profile)

        if timeout == 0:
            has_ocr = profile.startswith("ocr_") or profile == "ocrmac"
            timeout = _OCR_TIMEOUT if has_ocr else _STANDARD_TIMEOUT

        try:
            with _record_step("convert", profile, {"source": str(source), "timeout": timeout}):
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

            with _record_step("extract", profile, {"source": str(source), "deep": deep}):
                extracted = extract(conversion.document, source=str(source), deep=deep)
                _log.info(
                    "Extracted: %d text items (%d empty), %d tables",
                    len(extracted.texts),
                    extracted.empty_text_items,
                    len(extracted.tables),
                )

            quality_status = None
            if not skip_quality and conversion.json_path:
                with _record_step("quality", profile, {"source": str(source)}):
                    quality = evaluate(
                        json_path=conversion.json_path,
                        markdown_path=conversion.md_path,
                        fail_on_warn=self._fail_on_warn,
                        evaluator_script=self._evaluator_script,
                    )
                    result.quality = quality
                    quality_status = quality.status
                    _log.info("Quality check: %s", quality.status)

            with _record_step("chunk", profile, {"source": str(source)}):
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

            with _record_step("clean", profile, {"source": str(source)}):
                if quality_status:
                    for c in chunking.chunks:
                        c.metadata["quality_status"] = quality_status
                cleaned = self._cleaner.process_chunks(chunking.chunks)
                if not cleaned:
                    result.success = False
                    result.error = "All chunks removed during cleaning (empty or duplicate)"
                    return result
                chunking.chunks = cleaned
                chunking.total_chunks = len(cleaned)

                if chunking.empty_document:
                    result.success = False
                    result.error = "No text content extracted (document may be scanned or formula-only)"
                    return result

            with _record_step("vectorize", profile, {"source": str(source)}):
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

    def _ingest_hybrid(
        self,
        source: str | Path,
        profile: str,
        skip_quality: bool,
        deep: bool = False,
    ) -> IngestionResult:
        result = IngestionResult(source=str(source), profile=profile)
        _log.info("=== HYBRID: %s (profile=%s) ===", source, profile)

        from src.ingestion.orchestrator import orchestrate

        threshold = 0.85 if profile == "hybrid_accuracy" else 0.8
        chain = ["pymupdf4llm", "docling", "marker", "landingai", "llamaparse"]

        with _record_step("orchestrate", profile, {"source": str(source), "threshold": threshold}):
            orc_result = orchestrate(
                source=source,
                profile_name=profile,
                output_dir=self._output_dir,
                profiles_path=self._profiles_path,
                confidence_threshold=threshold,
                escalation_chain=chain,
            )

            if orc_result.error or not orc_result.markdown_text:
                result.success = False
                result.error = orc_result.error or "Hybrid ingestion returned empty content"
                return result

            result.conversion = ConversionOutput(
                document=None,
                source=str(source),
                profile=profile,
                duration_seconds=orc_result.total_duration,
                markdown_text=orc_result.markdown_text,
            )

        page_quality = [
            {"page_confidence": pr.confidence, "extraction_engine": pr.engine}
            for pr in orc_result.pages
        ] if orc_result.pages else None

        with _record_step("chunk", profile, {"source": str(source)}):
            chunking = chunk_markdown(
                markdown_text=orc_result.markdown_text,
                source=str(source),
                page_quality=page_quality,
            )
            result.chunking = chunking
            _log.info(
                "Hybrid chunking: %d chunks (avg %d tokens, empty=%s)",
                chunking.total_chunks, chunking.avg_tokens, chunking.empty_document,
            )

        with _record_step("clean", profile, {"source": str(source)}):
            cleaned = self._cleaner.process_chunks(chunking.chunks)
            if not cleaned:
                result.success = False
                result.error = "All chunks removed during cleaning"
                return result
            chunking.chunks = cleaned
            chunking.total_chunks = len(cleaned)

            if chunking.empty_document:
                result.success = False
                result.error = "No text content extracted via hybrid pipeline"
                return result

        with _record_step("vectorize", profile, {"source": str(source)}):
            vector_count = self._store.add_document(
                chunks=chunking.chunks,
                source=str(source),
                model_name=self._embedding_model,
            )
            result.vector_count = vector_count
            result.success = True
        return result

    def _retry_chain(
        self,
        source: str | Path,
        first_result: IngestionResult,
        skip_quality: bool,
        deep: bool = False,
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

            profile_selected_total.labels(profile=fb, reason="fallback").inc()
            _log.warning("Retrying %s with profile '%s' (previous: %s)", source, fb, chain[-1])
            result = self._try_ingest(source, fb, skip_quality, deep=deep)
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
        rerank: bool = True,
        min_rerank_score: float | None = None,
        use_hybrid: bool = False,
    ) -> RetrievalResult:
        with _tracer.start_as_current_span("pipeline.retrieve") as span:
            span.set_attribute("query", query[:200])
            span.set_attribute("k", k)
            span.set_attribute("rerank", rerank)
            span.set_attribute("use_hybrid", use_hybrid)

            fetch_k = k * 3 if (rerank and self._reranker) else k

            if use_hybrid and self._bm25 and self._hybrid:
                return self._hybrid_retrieve(query, k, fetch_k, where, rerank, min_rerank_score)

            result = self._store.query(
                query_text=query,
                k=fetch_k,
                model_name=self._embedding_model,
                where=where,
            )

            if rerank and self._reranker and result.results:
                return self._apply_reranker(query, result.results, k, min_rerank_score)

            return result

    def _hybrid_retrieve(
        self,
        query: str,
        k: int,
        fetch_k: int,
        where: dict | None,
        rerank: bool,
        min_rerank_score: float | None,
    ) -> RetrievalResult:
        from src.embeddings.embedder import embed_text

        if self._bm25._bm25 is None:
            self.rebuild_bm25_index()

        with _tracer.start_as_current_span("pipeline.hybrid_retrieve.vector_query"):
            query_embedding = embed_text(query, model_name=self._embedding_model)
            vector_raw = self._store._collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=fetch_k,
                where=where,
            )

            vector_results: list[dict] = []
            if vector_raw["ids"] and vector_raw["ids"][0]:
                for i in range(len(vector_raw["ids"][0])):
                    vector_results.append({
                        "index": i,
                        "id": vector_raw["ids"][0][i] if vector_raw["ids"] else "",
                        "text": vector_raw["documents"][0][i] if vector_raw["documents"] else "",
                        "metadata": vector_raw["metadatas"][0][i] if vector_raw["metadatas"] else {},
                        "score": 1.0 - vector_raw["distances"][0][i] if vector_raw["distances"] else 0.0,
                    })

        with _tracer.start_as_current_span("pipeline.hybrid_retrieve.bm25"):
            bm25_results = self._bm25.search(query, k=fetch_k)

        with _tracer.start_as_current_span("pipeline.hybrid_retrieve.fuse"):
            fused = self._hybrid.fuse_reciprocal_rank(vector_results, bm25_results, k=fetch_k)

            hybrid_chunks: list[RetrievedChunk] = []
            for entry in fused:
                idx = entry["index"]
                if idx < len(vector_results):
                    r = vector_results[idx]
                    hybrid_chunks.append(RetrievedChunk(
                        text=r.get("text", ""),
                        contextualized_text=r.get("text", ""),
                        score=entry["rrf_score"],
                        metadata=r.get("metadata", {}),
                    ))

        if rerank and self._reranker and hybrid_chunks:
            return self._apply_reranker(query, hybrid_chunks, k, min_rerank_score)

        return RetrievalResult(
            query=query,
            results=hybrid_chunks[:k],
            total_results=len(hybrid_chunks[:k]),
        )

    def _apply_reranker(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        keep: int,
        min_score: float | None,
    ) -> RetrievalResult:
        reranked = self._reranker.rerank(
            query=query,
            chunks=chunks,
            keep=keep,
            min_score=min_score,
        )
        reranked_chunks = [
            RetrievedChunk(
                text=r["chunk"].text,
                contextualized_text=r["chunk"].contextualized_text,
                score=r["score"],
                metadata=r["chunk"].metadata if hasattr(r["chunk"], "metadata") else {},
            )
            for r in reranked
        ]
        return RetrievalResult(
            query=query,
            results=reranked_chunks,
            total_results=len(reranked_chunks),
        )

    def rebuild_bm25_index(self) -> None:
        if self._bm25 is None:
            return
        chunks = self._store.get_all_chunks()
        if chunks:
            self._bm25.build_index(chunks, text_key="text")
            _log.info("BM25 index rebuilt with %d chunks", len(chunks))
        else:
            _log.info("No chunks in store — BM25 index empty")

    def delete_source(self, source: str) -> int:
        return self._store.delete_source(source)

    def list_documents(self) -> list[dict]:
        return self._store.list_sources()

    def get_document_info(self, source: str) -> dict | None:
        return self._store.get_source_info(source)

    def count_by_source(self) -> dict[str, int]:
        return self._store.count_by_source()

    def status(self) -> dict:
        return {
            "document_count": self._store.document_count(),
            "sources": self._store.list_sources(),
            "embedding_model": self._embedding_model,
            "output_dir": str(self._output_dir),
            "auto_retry": self._auto_retry,
            "chunk_count_by_source": self._store.count_by_source(),
        }
