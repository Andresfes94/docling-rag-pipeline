from __future__ import annotations

import gc
import json
import logging
import os
import pickle
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.ingestion.loader import convert as convert_doc
from src.ingestion.extractor import extract
from src.ingestion.chunker import ChunkingResult, chunk_document
from src.ingestion.detector import detect
from src.retrieval.pipeline import RAGPipeline

_log = logging.getLogger(__name__)


@dataclass
class BatchItemResult:
    source: str
    profile: str
    success: bool
    duration_seconds: float
    page_count: int = 0
    chunks: int = 0
    error: str | None = None
    staging_path: str | None = None


@dataclass
class BatchResult:
    total: int
    succeeded: int
    failed: int
    total_duration: float
    results: list[BatchItemResult] = field(default_factory=list)


def _worker_staging_dir() -> Path:
    path = Path("data/staging")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _process_one(args: tuple) -> BatchItemResult:
    source, profile, output_dir, profiles_path, chunk_max_tokens, embedding_model = args
    start = time.time()

    try:
        if profile == "auto":
            doc_profile = detect(source)
            profile = doc_profile.suggested_profile()

        conversion = convert_doc(
            source=source,
            profile_name=profile,
            output_dir=output_dir,
            profiles_path=profiles_path,
            timeout_seconds=600 if profile.startswith("ocr_") or profile == "ocrmac" else 120,
        )

        if conversion.timed_out or conversion.error or conversion.document is None:
            return BatchItemResult(
                source=str(source),
                profile=profile,
                success=False,
                duration_seconds=time.time() - start,
                error=conversion.error or "Timed out or no document",
            )

        extracted = extract(conversion.document, source=str(source))

        if not extracted.has_text_content:
            return BatchItemResult(
                source=str(source),
                profile=profile,
                success=False,
                duration_seconds=time.time() - start,
                error="No text content extracted",
                page_count=conversion.page_count,
            )

        chunking = chunk_document(
            document=conversion.document,
            source=str(source),
            max_tokens=chunk_max_tokens,
        )

        if chunking.empty_document:
            return BatchItemResult(
                source=str(source),
                profile=profile,
                success=False,
                duration_seconds=time.time() - start,
                error="No chunks produced",
                page_count=conversion.page_count,
            )

        staging = _worker_staging_dir() / f"{Path(source).stem}_{int(time.time() * 1000)}.pkl"
        staging_data = {
            "source": str(source),
            "profile": profile,
            "page_count": conversion.page_count,
            "chunks": [
                {
                    "text": c.text,
                    "contextualized_text": c.contextualized_text,
                    "headings": c.headings or [],
                    "page": c.page,
                    "source": c.source,
                    "chunk_index": c.chunk_index,
                    "token_count": c.token_count,
                }
                for c in chunking.chunks
            ],
        }
        staging.write_bytes(pickle.dumps(staging_data))

        del conversion.document
        del extracted
        del chunking
        gc.collect()

        return BatchItemResult(
            source=str(source),
            profile=profile,
            success=True,
            duration_seconds=time.time() - start,
            page_count=conversion.page_count,
            chunks=len(staging_data["chunks"]),
            staging_path=str(staging),
        )

    except Exception as exc:
        _log.exception("Worker failed for %s", source)
        return BatchItemResult(
            source=str(source),
            profile=profile,
            success=False,
            duration_seconds=time.time() - start,
            error=str(exc),
        )


def ingest_batch(
    sources: list[str | Path],
    profile: str = "auto",
    workers: int = 0,
    output_dir: str | Path = "data/output",
    profiles_path: str | Path = "profiles.yaml",
    chunk_max_tokens: int = 512,
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> BatchResult:
    if workers <= 0:
        workers = max(1, os.cpu_count() - 1)

    _log.info("Batch ingest: %d documents, %d workers, profile='%s'", len(sources), workers, profile)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    args_list = [
        (str(s), profile, str(output_dir), str(profiles_path), chunk_max_tokens, embedding_model)
        for s in sources
    ]

    start = time.time()
    results: list[BatchItemResult] = []

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_process_one, a): a[0] for a in args_list}
        for future in as_completed(futures):
            src = futures[future]
            try:
                result = future.result()
                results.append(result)
                status = "OK" if result.success else "FAIL"
                _log.info("%s: %s (%.1fs, %d pages, %d chunks)", status, src, result.duration_seconds, result.page_count, result.chunks)
            except Exception as exc:
                _log.error("Worker crashed for %s: %s", src, exc)
                results.append(BatchItemResult(
                    source=str(src),
                    profile=profile,
                    success=False,
                    duration_seconds=time.time() - start,
                    error=str(exc),
                ))

    total_duration = time.time() - start

    # Phase 2: batch-import all staging files to Chroma (single process)
    pipeline = RAGPipeline(
        output_dir=output_dir,
        profiles_path=profiles_path,
        chunk_max_tokens=chunk_max_tokens,
        embedding_model=embedding_model,
    )

    staging_dir = _worker_staging_dir()
    imported = 0
    for r in results:
        if r.success and r.staging_path:
            staging_path = Path(r.staging_path)
            if staging_path.is_file():
                try:
                    data = pickle.loads(staging_path.read_bytes())
                    from types import SimpleNamespace
                    chunk_objs = []
                    for c in data["chunks"]:
                        obj = SimpleNamespace()
                        obj.contextualized_text = c.get("contextualized_text", c.get("text", ""))
                        obj.text = c.get("text", "")
                        obj.chunk_index = c.get("chunk_index", 0)
                        obj.page = c.get("page")
                        obj.token_count = c.get("token_count", 0)
                        obj.headings = c.get("headings", [])
                        obj.source = c.get("source", data["source"])
                        obj.metadata = {}
                        chunk_objs.append(obj)
                    pipeline.store.add_document(
                        chunks=chunk_objs,
                        source=data["source"],
                        model_name=embedding_model,
                    )
                    imported += 1
                    staging_path.unlink()
                except Exception as exc:
                    _log.error("Failed to import staging for %s: %s", r.source, exc)

    _log.info("Batch complete: %d/%d succeeded, %d imported to Chroma in %.1fs",
              sum(1 for r in results if r.success), len(results), imported, total_duration)

    return BatchResult(
        total=len(sources),
        succeeded=sum(1 for r in results if r.success),
        failed=sum(1 for r in results if not r.success),
        total_duration=total_duration,
        results=results,
    )
