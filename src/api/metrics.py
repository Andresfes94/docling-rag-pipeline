from __future__ import annotations

import time
from typing import Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, Histogram, generate_latest, REGISTRY
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

http_requests_total = Counter(
    "rag_http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "rag_http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

ingest_documents_total = Counter(
    "rag_ingest_documents_total",
    "Total documents ingested",
    labelnames=["profile", "status"],
)

ingest_duration_seconds = Histogram(
    "rag_ingest_duration_seconds",
    "Document ingestion duration in seconds",
    labelnames=["profile"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

retrieve_requests_total = Counter(
    "rag_retrieve_requests_total",
    "Total retrieve requests",
    labelnames=["cache_hit"],
)

retrieve_chunks_total = Counter(
    "rag_retrieve_chunks_total",
    "Total chunks returned by retrieve",
)

retrieve_duration_seconds = Histogram(
    "rag_retrieve_duration_seconds",
    "Retrieve duration in seconds",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

llm_calls_total = Counter(
    "rag_llm_calls_total",
    "Total LLM generation calls",
    labelnames=["provider", "status"],
)

llm_duration_seconds = Histogram(
    "rag_llm_duration_seconds",
    "LLM generation duration in seconds",
    labelnames=["provider"],
    buckets=(1.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0),
)

cache_entries = Counter(
    "rag_cache_entries_total",
    "Total cache entries created",
)

cache_hits = Counter(
    "rag_cache_hits_total",
    "Total cache hits",
)

cache_misses = Counter(
    "rag_cache_misses_total",
    "Total cache misses",
)

rate_limit_hits = Counter(
    "rag_rate_limit_hits_total",
    "Total rate limit hits",
    labelnames=["endpoint"],
)

vector_store_documents = Counter(
    "rag_vector_store_documents_total",
    "Total documents in vector store",
)

pipeline_step_duration_seconds = Histogram(
    "rag_pipeline_step_duration_seconds",
    "Duration of each pipeline ingestion step",
    labelnames=["step", "profile", "status"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

engine_quality_score = Histogram(
    "rag_engine_quality_score",
    "Quality score distribution per extraction engine",
    labelnames=["engine"],
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

profile_selected_total = Counter(
    "rag_profile_selected_total",
    "Total profile selections by reason (auto, explicit, fallback, hybrid)",
    labelnames=["profile", "reason"],
)

rerank_score = Histogram(
    "rag_rerank_score",
    "Cross-encoder reranker score distribution",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)


class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        method = request.method
        path = request.url.path
        endpoint = path.split("/")[1] if path.count("/") >= 1 else "root"

        start = time.monotonic()
        response: Response = await call_next(request)
        elapsed = time.monotonic() - start

        status_group = f"{response.status_code // 100}xx"
        http_requests_total.labels(method=method, endpoint=endpoint, status=status_group).inc()
        http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(elapsed)

        return response


def setup_metrics(app: FastAPI) -> None:
    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(
            content=generate_latest(REGISTRY).decode("utf-8"),
            media_type="text/plain",
        )

    app.add_middleware(MetricsMiddleware)
