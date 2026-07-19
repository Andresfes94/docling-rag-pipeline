from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from src.api import auth
from src.api.auth import AuthMiddleware, _load_keys
from src.api.tracing import setup_tracing
from src.api.validation import validate_source
from src.api.cache import RetrievalCache
from src.api.logging_config import setup_logging, set_elapsed_ms, set_request_id
from src.api.metrics import (
    ingest_documents_total,
    retrieve_chunks_total,
    retrieve_requests_total,
    setup_metrics,
)
from src.api.models import (
    DeleteResponse,
    DocumentInfoResponse,
    DocumentListResponse,
    ErrorResponse,
    IngestRequest,
    IngestTaskResponse,
    RetrieveRequest,
    RetrieveResponse,
    RetrievedChunkResponse,
    StatusResponse,
)
from src.api.rate_limiter import RateLimiterMiddleware
from src.retrieval.pipeline import RAGPipeline
from src.retrieval.reranker import CrossEncoderReranker
from src.retrieval.hybrid_search import BM25Retriever, HybridRetriever

from dotenv import load_dotenv

from src.config import Settings

load_dotenv()

settings = Settings.from_env()
setup_logging()

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    errors = settings.validate()
    if errors:
        msg = "Configuration errors:\n  " + "\n  ".join(errors)
        _log.error(msg)
        raise RuntimeError(msg)
    setup_tracing()
    _log.info("RAG Pipeline API starting...")
    reranker = CrossEncoderReranker()
    bm25 = BM25Retriever()
    hybrid = HybridRetriever()
    app.state.pipeline = RAGPipeline(
        persist_directory=settings.chroma_persist_dir,
        embedding_model=settings.embedding_model,
        chunk_max_tokens=settings.chunk_max_tokens,
        profiles_path=settings.profiles_path,
        output_dir=settings.output_dir,
        evaluator_script=settings.evaluator_script,
        reranker=reranker,
        bm25_retriever=bm25,
        hybrid_retriever=hybrid,
    )
    app.state.pipeline.rebuild_bm25_index()
    app.state.cache = RetrievalCache(capacity=settings.cache_capacity, ttl=settings.cache_ttl)
    app.state.tasks: dict[str, dict[str, Any]] = {}
    _log.info("Vector store: %d documents", app.state.pipeline.store.document_count())
    yield
    _log.info("RAG Pipeline API shutting down...")


app = FastAPI(
    title="Docling RAG Pipeline API",
    description="""
    Production-grade retrieval API for LLM consumption.

    **Features:**
    - Ingest documents (PDF, Excel, images) via Docling with configurable profiles
    - Retrieve relevant chunks with semantic search (cosine similarity)
    - LLM-friendly context assembly (`format=llm`) — chunks formatted as ready-to-inject prompt context
    - SSE streaming (`/retrieve/stream`) — progressive delivery for real-time LLM consumption
    - Async ingestion — `POST /ingest` returns immediately with a `task_id` to poll
    - Rate limiting — token bucket per IP per endpoint (retrieve=30/s, ingest=2/s)
    - Response caching — LRU with 5-minute TTL, automatic invalidation on re-ingest/delete
    - Document management — list, inspect, and delete ingested documents
    - Observability — `X-Request-ID` and `X-Response-Time-Ms` headers on every response

    **Usage with LLMs:**
    ```python
    # 1. Retrieve context for an LLM prompt
    response = requests.post("http://localhost:8000/retrieve", json={
        "query": "option pricing greeks",
        "k": 5,
        "format": "llm",
    })
    context = response.json()["context"]
    prompt = f"Answer using this context:\\n{context}\\n\\nQuestion: ..."
    ```
    """,
    version="0.2.0",
    lifespan=lifespan,
)

cors_origins = settings.cors_origins.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(AuthMiddleware)
app.add_middleware(RateLimiterMiddleware, default_rate=10.0, default_burst=20)
setup_metrics(app)

_load_keys()


# --- Dependencies ---


def get_pipeline(request: Request) -> RAGPipeline:
    return request.app.state.pipeline


def get_cache(request: Request) -> RetrievalCache:
    return request.app.state.cache


def get_tasks(request: Request) -> dict[str, dict[str, Any]]:
    return request.app.state.tasks


# --- Auth reload ---


@app.post("/auth/reload", summary="Reload API keys from environment", include_in_schema=False)
async def auth_reload() -> dict[str, str]:
    _load_keys()
    count = len(auth.API_KEYS) if hasattr(auth, "API_KEYS") else 0
    _log.info("API keys reloaded (%d key(s))", count)
    return {"status": "ok", "keys_loaded": count}


# --- Exception handler ---


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    _log.exception("Unhandled exception [%s] on %s %s", rid, request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            detail="Internal server error",
            request_id=rid,
        ).model_dump(),
    )


@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Any) -> Any:
    rid = str(uuid.uuid4())[:8]
    request.state.request_id = rid
    set_request_id(rid)
    start = time.monotonic()
    response: Any = await call_next(request)
    elapsed = time.monotonic() - start
    elapsed_ms = round(elapsed * 1000, 1)
    set_elapsed_ms(elapsed_ms)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Response-Time-Ms"] = str(int(elapsed_ms))
    return response


# --- Health ---


@app.get("/health", summary="Health check", response_description="Returns ok if the service is running")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# --- Ingest ---


def _run_ingest(
    task_id: str,
    source: str,
    profile: str,
    skip_quality: bool,
    deep: bool,
    tasks: dict[str, dict[str, Any]],
    pipeline: RAGPipeline,
    cache: RetrievalCache,
) -> None:
    tasks[task_id]["status"] = "running"
    try:
        result = pipeline.ingest(
            source=source,
            profile=profile,
            skip_quality=skip_quality,
            deep=deep,
        )
        status = "done" if result.success else "failed"
        tasks[task_id].update(
            status=status,
            pages=result.conversion.page_count if result.conversion else 0,
            duration_seconds=result.conversion.duration_seconds if result.conversion else 0.0,
            chunks=result.chunking.total_chunks if result.chunking else 0,
            error=result.error,
        )
        ingest_documents_total.labels(profile=result.profile, status=status).inc()
        if result.success:
            cache.invalidate(source=source)
            pipeline.rebuild_bm25_index()
    except Exception as exc:
        _log.exception("Background ingest failed for %s", source)
        tasks[task_id].update(status="failed", error=str(exc))
        ingest_documents_total.labels(profile=profile, status="failed").inc()


@app.post(
    "/ingest",
    summary="Ingest a document (async)",
    response_description="Returns a task ID immediately; poll GET /ingest/{task_id} for status",
)
async def ingest(
    req: IngestRequest,
    background_tasks: BackgroundTasks,
    pipeline: RAGPipeline = Depends(get_pipeline),
    cache: RetrievalCache = Depends(get_cache),
    tasks: dict[str, dict[str, Any]] = Depends(get_tasks),
) -> IngestTaskResponse:
    err = validate_source(req.source)
    if err:
        raise HTTPException(status_code=400, detail=err)
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "task_id": task_id,
        "source": req.source,
        "status": "pending",
        "profile": req.profile,
        "pages": 0,
        "duration_seconds": 0.0,
        "chunks": 0,
        "error": None,
    }
    background_tasks.add_task(
        _run_ingest, task_id, req.source, req.profile, req.skip_quality, req.deep,
        tasks, pipeline, cache,
    )
    _log.info("Ingest task %s enqueued for %s", task_id, req.source)
    return IngestTaskResponse(
        task_id=task_id,
        source=req.source,
        status="pending",
        profile=req.profile,
    )


@app.get(
    "/ingest/{task_id}",
    summary="Poll ingest task status",
    response_description="Current status of the async ingest task (pending/running/done/failed)",
)
async def ingest_status(
    task_id: str,
    tasks: dict[str, dict[str, Any]] = Depends(get_tasks),
) -> IngestTaskResponse:
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return IngestTaskResponse(**task)


# --- Retrieve ---


def _build_llm_context(results: list[RetrievedChunkResponse]) -> str:
    parts: list[str] = []
    for i, r in enumerate(results, 1):
        header_parts = []
        if r.source:
            header_parts.append(f"Source: {r.source}")
        if r.page:
            header_parts.append(f"Page: {r.page}")
        if r.headings:
            header_parts.append(f"Section: {r.headings}")
        header = " | ".join(header_parts)
        parts.append(f"[{i}] {header}\n{r.text}")
    return "\n\n---\n\n".join(parts)


def _where_from_filters(sources: list[str] | None, page_range: list[int] | None) -> dict[str, Any] | None:
    clauses: list[dict[str, Any]] = []
    if sources:
        clauses.append({"source": {"$in": sources}})
    if page_range:
        clauses.append({"page": {"$gte": int(page_range[0])}})
        clauses.append({"page": {"$lte": int(page_range[1])}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


@app.post(
    "/retrieve",
    summary="Retrieve relevant chunks",
    response_description="Returns ranked chunks matching the query, optionally as assembled LLM context",
)
async def retrieve(
    req: RetrieveRequest,
    pipeline: RAGPipeline = Depends(get_pipeline),
    cache: RetrievalCache = Depends(get_cache),
) -> RetrieveResponse:
    if req.sources:
        src_filter = tuple(sorted(req.sources))
    else:
        src_filter = None

    cached = cache.get(req.query, req.k, sources=src_filter, fmt=req.format)
    if cached is not None:
        _log.info("Cache hit for query='%s' k=%d fmt=%s", req.query[:60], req.k, req.format)
        return RetrieveResponse(**cached)

    loop = asyncio.get_running_loop()
    where = _where_from_filters(req.sources, req.page_range)
    result = await loop.run_in_executor(
        None, pipeline.retrieve, req.query, req.k, where,
        req.rerank, req.min_rerank_score, req.use_hybrid,
    )

    chunks = [
        RetrievedChunkResponse(
            text=r.contextualized_text,
            score=round(r.score, 4),
            source=r.metadata.get("source", ""),
            page=r.metadata.get("page", 0),
            headings=r.metadata.get("headings", ""),
        )
        for r in result.results
    ]

    if req.min_score is not None:
        chunks = [c for c in chunks if c.score >= req.min_score]

    retrieve_requests_total.labels(cache_hit="false").inc()
    retrieve_chunks_total.inc(len(chunks))

    context_str = _build_llm_context(chunks) if req.format == "llm" else None

    response_data = RetrieveResponse(
        query=req.query,
        total_results=len(chunks),
        format=req.format,
        context=context_str,
        results=chunks,
    )

    cache.set(req.query, req.k, response_data.model_dump(), sources=src_filter, fmt=req.format)

    return response_data


@app.get(
    "/retrieve/stream",
    summary="Stream retrieve results via SSE",
    response_description="Server-Sent Events stream: meta -> chunk (xN) -> done",
)
async def retrieve_stream(
    query: str = Query(..., description="Search query"),
    k: int = Query(5, ge=1, le=100, description="Number of results (max 100)"),
    sources: str | None = Query(None, description="Comma-separated source filter, e.g. 'doc1.pdf,doc2.pdf'"),
    format: str = Query("json", description='Output format per chunk: "json" or "llm"'),
    min_score: float | None = Query(None, ge=0.0, le=1.0, description="Minimum similarity score threshold"),
    rerank: bool = Query(True, description="Enable cross-encoder reranking"),
    min_rerank_score: float | None = Query(None, ge=0.0, le=1.0, description="Minimum reranker score"),
    use_hybrid: bool = Query(False, description="Enable BM25 + vector hybrid search with RRF fusion"),
    pipeline: RAGPipeline = Depends(get_pipeline),
) -> StreamingResponse:
    loop = asyncio.get_running_loop()
    src_list = sources.split(",") if sources else None
    where = _where_from_filters(src_list, None)
    result = await loop.run_in_executor(
        None, pipeline.retrieve, query, k, where, rerank, min_rerank_score, use_hybrid,
    )

    chunks = [
        RetrievedChunkResponse(
            text=r.contextualized_text,
            score=round(r.score, 4),
            source=r.metadata.get("source", ""),
            page=r.metadata.get("page", 0),
            headings=r.metadata.get("headings", ""),
        )
        for r in result.results
    ]

    if min_score is not None:
        chunks = [c for c in chunks if c.score >= min_score]

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            yield f"event: meta\ndata: {{\"total\": {len(chunks)}, \"format\": \"{format}\"}}\n\n"
            for i, chunk in enumerate(chunks):
                if format == "llm":
                    h = f"Source: {chunk.source} | Page: {chunk.page} | Section: {chunk.headings}" if chunk.source else ""
                    data = f"[{i+1}] {h}\n{chunk.text}"
                else:
                    data = chunk.model_dump_json()
                yield f"event: chunk\ndata: {data}\n\n"
                await asyncio.sleep(0)
            yield "event: done\ndata: {}\n\n"
        except Exception as exc:
            _log.exception("SSE stream error for query='%s'", query)
            yield f"event: error\ndata: {{\"detail\": \"{exc}\"}}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# --- Documents ---


@app.get(
    "/documents",
    summary="List ingested documents",
    response_description="All documents currently stored in the vector store with chunk counts and metadata",
)
async def list_documents(
    pipeline: RAGPipeline = Depends(get_pipeline),
) -> DocumentListResponse:
    sources = pipeline.list_documents()
    docs: list[dict] = []
    for src in sources:
        info = pipeline.get_document_info(src)
        if info:
            docs.append(info)
    return DocumentListResponse(documents=[DocumentInfoResponse(**d) for d in docs], total=len(docs))


@app.get(
    "/documents/{source:path}",
    summary="Get document details",
    response_description="Detailed information about a specific document: chunk count, pages, profiles used",
)
async def get_document(
    source: str,
    pipeline: RAGPipeline = Depends(get_pipeline),
) -> DocumentInfoResponse:
    info = pipeline.get_document_info(source)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Document '{source}' not found in store")
    return DocumentInfoResponse(**info)


@app.delete(
    "/documents/{source:path}",
    summary="Delete a document",
    response_description="Removes all chunks for the given source and invalidates the cache",
)
async def delete_document(
    source: str,
    pipeline: RAGPipeline = Depends(get_pipeline),
    cache: RetrievalCache = Depends(get_cache),
) -> DeleteResponse:
    info = pipeline.get_document_info(source)
    if info is None:
        return DeleteResponse(success=False, source=source, error=f"Document '{source}' not found")
    count = pipeline.delete_source(source)
    cache.invalidate(source=source)
    _log.info("Deleted document '%s': %d chunks removed", source, count)
    return DeleteResponse(success=True, source=source, chunks_removed=count)


# --- Status ---


@app.get(
    "/status",
    summary="Pipeline status",
    response_description="Overview of the vector store, document count, sources, and cache state",
)
async def status(
    pipeline: RAGPipeline = Depends(get_pipeline),
    cache: RetrievalCache = Depends(get_cache),
) -> StatusResponse:
    s = pipeline.status()
    return StatusResponse(
        document_count=s["document_count"],
        sources=s["sources"],
        embedding_model=s["embedding_model"],
        chunk_count_by_source=s.get("chunk_count_by_source", {}),
        cache_entries=cache.size,
    )


# --- Entry point ---


def main() -> None:
    import uvicorn
    uvicorn.run(
        "src.api.server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
