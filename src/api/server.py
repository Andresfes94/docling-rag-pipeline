from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException

from src.api.models import (
    IngestRequest,
    IngestResponse,
    RetrieveRequest,
    RetrieveResponse,
    RetrievedChunkResponse,
    StatusResponse,
)
from src.retrieval.pipeline import RAGPipeline

_log = logging.getLogger(__name__)

_pipeline: RAGPipeline | None = None


def get_pipeline() -> RAGPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    _log.info("RAG Pipeline API starting...")
    get_pipeline()
    yield
    _log.info("RAG Pipeline API shutting down...")


app = FastAPI(
    title="Docling RAG Pipeline API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest):
    pipeline = get_pipeline()
    result = pipeline.ingest(
        source=req.source,
        profile=req.profile,
        skip_quality=req.skip_quality,
    )

    return IngestResponse(
        success=result.success,
        source=result.source,
        profile=result.profile,
        pages=result.conversion.page_count if result.conversion else 0,
        duration_seconds=result.conversion.duration_seconds if result.conversion else 0.0,
        chunks=result.chunking.total_chunks if result.chunking else 0,
        avg_tokens_per_chunk=result.chunking.avg_tokens if result.chunking else 0.0,
        quality_status=result.quality.status if result.quality else None,
        vector_count=result.vector_count,
        error=result.error,
    )


@app.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(req: RetrieveRequest):
    pipeline = get_pipeline()
    result = pipeline.retrieve(query=req.query, k=req.k)

    return RetrieveResponse(
        query=result.query,
        total_results=result.total_results,
        results=[
            RetrievedChunkResponse(
                text=r.text[:500],
                score=round(r.score, 4),
                source=r.metadata.get("source", ""),
                page=r.metadata.get("page", 0),
                headings=r.metadata.get("headings", ""),
            )
            for r in result.results
        ],
    )


@app.get("/status", response_model=StatusResponse)
async def status():
    pipeline = get_pipeline()
    s = pipeline.status()
    return StatusResponse(
        document_count=s["document_count"],
        sources=s["sources"],
        embedding_model=s["embedding_model"],
    )


def main():
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
