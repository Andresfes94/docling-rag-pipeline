from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from src.api.models import (
    DeleteResponse,
    DocumentInfoResponse,
    DocumentListResponse,
    ErrorResponse,
    IngestRequest,
    IngestResponse,
    IngestTaskResponse,
    RetrieveRequest,
    RetrieveResponse,
    RetrievedChunkResponse,
    StatusResponse,
)
from src.api.cache import RetrievalCache
from src.api.rate_limiter import RateLimiterMiddleware
from src.retrieval.pipeline import RAGPipeline

_log = logging.getLogger(__name__)

_pipeline: RAGPipeline | None = None
_cache: RetrievalCache | None = None
_tasks: dict[str, dict[str, Any]] = {}


def get_pipeline() -> RAGPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline


def get_cache() -> RetrievalCache:
    global _cache
    if _cache is None:
        _cache = RetrievalCache(capacity=1024, ttl=300)
    return _cache


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    _log.info("RAG Pipeline API starting...")
    get_pipeline()
    get_cache()
    _log.info("Vector store: %d documents", _pipeline.store.document_count() if _pipeline else 0)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimiterMiddleware, default_rate=10.0, default_burst=20)


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
    start = time.monotonic()
    response: Any = await call_next(request)
    elapsed = time.monotonic() - start
    response.headers["X-Request-ID"] = rid
    response.headers["X-Response-Time-Ms"] = str(int(elapsed * 1000))
    return response


# --- Health ---


@app.get("/health", summary="Health check", response_description="Returns ok if the service is running")
async def health() -> dict[str, str]:
    """Lightweight health check. Returns `{\"status\": \"ok\"}` when the API is operational."""
    return {"status": "ok"}


# --- Ingest ---


def _run_ingest(task_id: str, source: str, profile: str, skip_quality: bool, deep: bool) -> None:
    global _tasks
    _tasks[task_id]["status"] = "running"
    try:
        result = get_pipeline().ingest(
            source=source,
            profile=profile,
            skip_quality=skip_quality,
            deep=deep,
        )
        _tasks[task_id].update(
            status="done" if result.success else "failed",
            pages=result.conversion.page_count if result.conversion else 0,
            duration_seconds=result.conversion.duration_seconds if result.conversion else 0.0,
            chunks=result.chunking.total_chunks if result.chunking else 0,
            error=result.error,
        )
        if result.success:
            get_cache().invalidate(source=source)
    except Exception as exc:
        _log.exception("Background ingest failed for %s", source)
        _tasks[task_id].update(status="failed", error=str(exc))


@app.post(
    "/ingest",
    summary="Ingest a document (async)",
    response_description="Returns a task ID immediately; poll GET /ingest/{task_id} for status",
)
async def ingest(req: IngestRequest, background_tasks: BackgroundTasks) -> IngestTaskResponse:
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
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
        _run_ingest, task_id, req.source, req.profile, req.skip_quality, req.deep
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
async def ingest_status(task_id: str) -> IngestTaskResponse:
    task = _tasks.get(task_id)
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
async def retrieve(req: RetrieveRequest) -> RetrieveResponse:
    """Semantic search over ingested documents.

    Supports filtering by **source** and **page range**, minimum score threshold,
    and two output formats:
    - `format=json` (default): returns raw chunks with scores and metadata
    - `format=llm`: assembles chunks into a single context string ready for LLM prompt injection

    Results are **cached** for 5 minutes (keyed by query, k, sources, and format).
    Cache is invalidated when a document is re-ingested or deleted.
    """
    if req.sources:
        src_filter = tuple(sorted(req.sources))
    else:
        src_filter = None

    cache = get_cache()
    cached = cache.get(req.query, req.k, sources=src_filter, fmt=req.format)
    if cached is not None:
        _log.info("Cache hit for query='%s' k=%d fmt=%s", req.query[:60], req.k, req.format)
        return RetrieveResponse(**cached)

    where = _where_from_filters(req.sources, req.page_range)
    result = get_pipeline().retrieve(query=req.query, k=req.k, where=where)

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
    response_description="Server-Sent Events stream: meta → chunk (×N) → done",
)
async def retrieve_stream(
    query: str = Query(..., description="Search query"),
    k: int = Query(5, ge=1, le=100, description="Number of results (max 100)"),
    sources: str | None = Query(None, description="Comma-separated source filter, e.g. 'doc1.pdf,doc2.pdf'"),
    format: str = Query("json", description='Output format per chunk: "json" or "llm"'),
    min_score: float | None = Query(None, ge=0.0, le=1.0, description="Minimum similarity score threshold"),
) -> StreamingResponse:
    src_list = sources.split(",") if sources else None
    where = _where_from_filters(src_list, None)
    result = get_pipeline().retrieve(query=query, k=k, where=where)

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

    """Stream retrieval results as Server-Sent Events.

    Events:
    - `meta`: total result count and format
    - `chunk`: individual result (depends on format parameter)
    - `done`: signals stream completion

    Use with an EventSource client or any SSE-capable HTTP client.
    """
    async def event_stream() -> AsyncGenerator[str, None]:
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
async def list_documents() -> DocumentListResponse:
    pipeline = get_pipeline()
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
async def get_document(source: str) -> DocumentInfoResponse:
    pipeline = get_pipeline()
    info = pipeline.get_document_info(source)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Document '{source}' not found in store")
    return DocumentInfoResponse(**info)


@app.delete(
    "/documents/{source:path}",
    summary="Delete a document",
    response_description="Removes all chunks for the given source and invalidates the cache",
)
async def delete_document(source: str) -> DeleteResponse:
    pipeline = get_pipeline()
    info = pipeline.get_document_info(source)
    if info is None:
        return DeleteResponse(success=False, source=source, error=f"Document '{source}' not found")
    count = pipeline.delete_source(source)
    get_cache().invalidate(source=source)
    _log.info("Deleted document '%s': %d chunks removed", source, count)
    return DeleteResponse(success=True, source=source, chunks_removed=count)


# --- Status ---


@app.get(
    "/status",
    summary="Pipeline status",
    response_description="Overview of the vector store, document count, sources, and cache state",
)
async def status() -> StatusResponse:
    pipeline = get_pipeline()
    s = pipeline.status()
    return StatusResponse(
        document_count=s["document_count"],
        sources=s["sources"],
        embedding_model=s["embedding_model"],
        chunk_count_by_source=s.get("chunk_count_by_source", {}),
        cache_entries=get_cache().size,
    )


# --- Entry point ---


def main() -> None:
    import uvicorn
    uvicorn.run(
        "src.api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
