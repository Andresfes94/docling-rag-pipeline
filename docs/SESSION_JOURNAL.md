# Session Journal — Observability & Pipeline Instrumentation

## Current State (2026-07-19)

### What's Built

**All 14 original tickets** (auth, Redis, DI, integration tests, concurrency, LLM retry, metrics, logging, .env, Docker, CI, validation, tracing, list_models fix) +
**Data pipeline** (TextCleaner, CrossEncoderReranker, BM25/vector hybrid) +
**Multi-engine ingestion** (5 engines, orchestrator with per-page fallback, quality scorer, hybrid profiles) +
**Batch-clean script** (clean_existing_data.py) +
**API docs** (11 endpoints, curl examples, parameter tables).

**159 tests passing** (114 unit + 9 integration + 10 engine + 6 chunker + 5 quality scorer + 15 other).

### Observability & Metrics — Delivered

| Work | What | Files |
|---|---|---|
| OTel span instrumentation | Each pipeline step (convert/extract/quality/chunk/clean/vectorize/orchestrate) wrapped in `_record_step()` context manager with spans; retrieve and hybrid_retrieve also instrumented | `src/retrieval/pipeline.py` |
| New Prometheus counters | `pipeline_step_duration_seconds{step,profile,status}`, `engine_quality_score{engine}`, `profile_selected_total{profile,reason}`, `rerank_score` | `src/api/metrics.py` |
| LLM metrics wired up | `llm_calls_total{provider}` and `llm_duration_seconds{provider}` now increment in CrossEncoderReranker | `src/retrieval/reranker.py` |
| Orchestrator metrics | `engine_quality_score` recorded per page; `profile_selected_total{reason=hybrid}` | `src/ingestion/orchestrator.py` |
| `GET /profiles` | Returns all profiles from `profiles.yaml` with descriptions and options | `src/api/server.py:206`, `src/api/models.py` |
| Quality persisted in ChromaDB | `page_confidence` and `extraction_engine` stored in chunk metadata for hybrid path; `quality_status` for Docling path | `src/ingestion/chunker.py`, `src/storage/vector_store.py`, `src/retrieval/pipeline.py` |
| Prometheus in Docker Compose | New `prometheus` service on port 9090, scrapes `/metrics` | `docker-compose.yml`, `monitoring/prometheus.yml` |

### Architecture

```
Observe pipeline step                                   Expose /metrics
     │                                                       │
     ▼                                                       ▼
Pipeline Step ──► _record_step() ──► OTel span ──► Prometheus histogram
                     │                                    
                     ├── span.set_attribute(step, profile, ...)
                     ├── span.record_exception(error)
                     └── pipeline_step_duration_seconds.observe()

Reranker ──► llm_calls_total{provider} ++
          ──► llm_duration_seconds.observe()
          ──► rerank_score.observe()

Orchestrator ──► engine_quality_score{engine}.observe()
             ──► profile_selected_total{profile,reason} ++
```

### Metrics Reference

| Metric | Type | Labels | Wired |
|---|---|---|---|
| `rag_pipeline_step_duration_seconds` | Histogram | step, profile, status | pipeline.py |
| `rag_engine_quality_score` | Histogram | engine | orchestrator.py |
| `rag_profile_selected_total` | Counter | profile, reason | pipeline.py + orchestrator.py |
| `rag_rerank_score` | Histogram | — | reranker.py |
| `rag_llm_calls_total` | Counter | provider, status | reranker.py |
| `rag_llm_duration_seconds` | Histogram | provider | reranker.py |
| `rag_ingest_documents_total` | Counter | profile, status | server.py (already) |
| `rag_retrieve_requests_total` | Counter | cache_hit | server.py + cache.py (already) |

### How to Use

```bash
# List available profiles
curl http://localhost:8000/profiles

# View Prometheus metrics
curl http://localhost:8000/metrics

# Start Prometheus alongside the app
docker-compose up prometheus
# Then visit http://localhost:9090
```

### OTel Tracing

Tracing is configured via `setup_tracing()` in `tracing.py`. All pipeline spans (ingest steps, retrieve, hybrid queries) are created but require an OTel collector endpoint to export:

```bash
# Enable with any OTLP-compatible collector
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
```

Without the env var, spans are no-ops (OpenTelemetry API defaults to NoOpTracer).

### Prometheus Scrape Target

The Prometheus config at `monitoring/prometheus.yml` targets the `rag-pipeline` Docker service on port 8000 at `/metrics`.

### Next Steps for Continuing Agent

1. Build `POST /pipeline/compare` endpoint for profile benchmarking (Phase 2)
2. Add Grafana with pre-built dashboards once there's real metric data
3. Instrument the VLM engines (Granite, SmolDocling) with token usage tracking
4. Push `dev` branch and verify CI passes
