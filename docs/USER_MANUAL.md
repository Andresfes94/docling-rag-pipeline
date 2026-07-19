# Docling RAG Pipeline — User Manual

**Version:** 0.2.0

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [CLI Usage](#cli-usage)
5. [API Usage](#api-usage)
6. [Profiles Reference](#profiles-reference)
7. [Observability](#observability)
8. [Docker](#docker)
9. [Common Workflows](#common-workflows)
10. [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements-core.txt
pip install -e .

# 2. List available profiles
python scripts/run.py list-profiles

# 3. Ingest a document
python scripts/run.py ingest ~/my-document.pdf --profile standard

# 4. Search
python scripts/run.py retrieve "what is the main topic" --k 5

# 5. Start the API server
uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

---

## Installation

### Option A: Direct Python

Requires Python 3.11+.

```bash
# Clone the repo
git clone <repo-url>
cd docling-rag-pipeline

# Core dependencies (production)
pip install -r requirements-core.txt

# Install the package
pip install -e .

# (Optional) Install extras for deep enrichment
pip install -r requirements-optional.txt
```

### Option B: Docker

Requires Docker and Docker Compose.

```bash
# Build and start all services
docker-compose up --build -d

# The API is available at http://localhost:8000
# Prometheus is available at http://localhost:9090
```

---

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and adjust values:

```bash
cp .env.example .env
```

Key variables:

| Variable | Default | Description |
|---|---|---|
| `API_HOST` | `0.0.0.0` | Bind address |
| `API_PORT` | `8000` | Port |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `CHROMA_PERSIST_DIR` | `data/chroma` | Vector store persistence |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `text` | `"text"` or `"json"` |
| `API_KEY` / `API_KEYS` | `""` (disabled) | API key authentication |
| `REDIS_URL` | _(none)_ | Redis for rate-limit + cache |

All env vars accept an optional `RAG_` prefix (`RAG_API_HOST` overrides `API_HOST`).

### Profiles

Profiles define how documents are processed. They are stored in `profiles.yaml` and can be listed via:

```bash
python scripts/run.py list-profiles
# or
curl http://localhost:8000/profiles
```

---

## CLI Usage

The `scripts/run.py` script provides a CLI for all pipeline operations without starting the server.

### List Profiles

```bash
python scripts/run.py list-profiles
```

### Analyze / Detect

Analyze a document and see what profile would be suggested:

```bash
python scripts/run.py detect ~/document.pdf
```

Output:

```
Source:          ~/document.pdf
Pages:           42
Size:            2048 KB
Selectable text: True
Type:            born-digital
KB per page:     48.8
Suggested:       standard
```

### Ingest a Document

```bash
python scripts/run.py ingest ~/document.pdf --profile standard
python scripts/run.py ingest ~/document.pdf --profile hybrid  # multi-engine fallback
python scripts/run.py ingest ~/document.pdf --profile auto     # auto-detect
```

Options:
- `--profile, -p`: Profile name (default: `standard`)
- `--deep`: Enable deep enrichment (table formula fallback)
- `--skip-quality`: Skip quality evaluation
- `--no-retry`: Disable automatic retry on failure

Output:

```
Ingested:        ~/document.pdf
Profile:         hybrid
Pages:           42
Duration:        3.25s
Chunks:          156
Avg tokens/chunk: 480
Vector store:    156 total documents
```

### Batch Ingest

```bash
python scripts/run.py ingest-batch ~/doc1.pdf ~/doc2.pdf ~/doc3.pdf --profile auto --workers 4
```

### Search

```bash
python scripts/run.py retrieve "option pricing greeks" --k 10
```

Output:

```
Query:    option pricing greeks
Results:  5

[0.823] document.pdf (p.12)
       headings: Chapter 4 > Option Valuation
       The Black-Scholes model prices European options using five inputs...

[0.745] document.pdf (p.15)
       headings: Chapter 4 > Greeks
       Delta measures the rate of change of the option price...
```

### Pipeline Status

```bash
python scripts/run.py status
python scripts/run.py status --json
```

---

## API Usage

Start the API server:

```bash
uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

### `GET /health`

```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

### `GET /profiles`

```bash
curl http://localhost:8000/profiles
# → {"profiles": [{"name": "standard", "description": "Fast path for born-digital PDFs...", ...}], "total": 12}
```

### `POST /ingest`

Ingests a document asynchronously. Returns a `task_id` — poll `GET /ingest/{task_id}` for completion.

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "/path/to/document.pdf", "profile": "hybrid"}'

# → {"task_id": "abc123", "source": "/path/to/document.pdf", "status": "pending", "profile": "hybrid"}
```

Poll for status:

```bash
curl http://localhost:8000/ingest/abc123
# → {"task_id": "abc123", "source": "...", "status": "done",
#     "pages": 42, "duration_seconds": 3.2, "chunks": 156}
```

### `POST /retrieve`

```bash
# Basic search:
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "option pricing greeks", "k": 5}'

# LLM-ready context:
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "what is backtesting", "k": 3, "format": "llm"}'

# With hybrid search and reranking:
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "volatility smile", "k": 10, "use_hybrid": true, "rerank": true}'
```

### `GET /retrieve/stream`

SSE streaming for real-time LLM consumption:

```bash
curl -N "http://localhost:8000/retrieve/stream?query=option+pricing&k=3&format=llm&use_hybrid=true"
```

### `GET /documents`

```bash
curl http://localhost:8000/documents
# → {"documents": [{"source": "guide.pdf", "chunk_count": 156, ...}], "total": 1}
```

### `DELETE /documents/{source}`

```bash
curl -X DELETE http://localhost:8000/documents/guide.pdf
# → {"success": true, "source": "guide.pdf", "chunks_removed": 156}
```

### `GET /status`

```bash
curl http://localhost:8000/status
# → {"document_count": 156, "sources": ["guide.pdf"], "embedding_model": "...", ...}
```

### `GET /metrics`

Prometheus-formatted metrics:

```bash
curl http://localhost:8000/metrics
# → # HELP rag_pipeline_step_duration_seconds ...
# → # TYPE rag_pipeline_step_duration_seconds histogram
```

---

## Profiles Reference

| Profile | Pipeline | Use Case |
|---|---|---|
| `standard` | Docling | Born-digital PDFs with tables (default) |
| `fast` | Docling | No OCR, no tables — fastest |
| `large_document` | Docling | 150+ page PDFs, no OCR |
| `ocr_easyocr` | Docling | Scanned PDFs with EasyOCR |
| `ocr_tesseract` | Docling | Scanned with Tesseract (requires system tesseract) |
| `ocrmac` | Docling | macOS Vision OCR — fastest OCR on Apple Silicon |
| `ocr_rapid` | Docling | Scanned with RapidOCR (lightweight) |
| `vlm_granite` | VLM | Complex layouts, handwriting, formulas (GPU) |
| `vlm_smoldocling` | VLM | Lighter VLM model |
| `vlm_remote` | VLM | Remote OpenAI-compatible endpoint |
| `hybrid` | Multi-engine | Per-page fallback: PyMuPDF4LLM → Docling → Marker → Landing AI → LlamaParse (threshold 0.8) |
| `hybrid_accuracy` | Multi-engine | Highest accuracy: Marker+LLM → Docling → cloud APIs (threshold 0.85) |

### Hybrid Profiles

The `hybrid` and `hybrid_accuracy` profiles use a multi-engine orchestrator that:

1. Runs the first engine on every page
2. Scores each page with a quality heuristic (density ratio, garbage characters, repeated runs, avg word length)
3. Escalates low-confidence pages to the next engine in the chain
4. Merges per-page results into a single document

Per-page quality scores (`page_confidence`, `extraction_engine`) are stored in each chunk's metadata.

---

## Observability

### Prometheus Metrics

Metrics are available at `GET /metrics` in Prometheus text format.

**Counters:**

| Metric | Labels | Description |
|---|---|---|
| `rag_ingest_documents_total` | `profile`, `status` | Documents ingested |
| `rag_retrieve_requests_total` | `cache_hit` | Retrieve requests |
| `rag_retrieve_chunks_total` | — | Total chunks returned |
| `rag_llm_calls_total` | `provider`, `status` | LLM/reranker calls |
| `rag_profile_selected_total` | `profile`, `reason` | Profile selections |
| `rag_cache_hits_total` | — | Cache hits |
| `rag_cache_misses_total` | — | Cache misses |
| `rag_rate_limit_hits_total` | `endpoint` | Rate limit events |

**Histograms:**

| Metric | Labels | Description |
|---|---|---|
| `rag_pipeline_step_duration_seconds` | `step`, `profile`, `status` | Per-step ingestion duration |
| `rag_engine_quality_score` | `engine` | Quality score per engine |
| `rag_rerank_score` | — | Reranker score distribution |
| `rag_llm_duration_seconds` | `provider` | LLM call duration |
| `rag_ingest_duration_seconds` | `profile` | Total ingestion duration |
| `rag_retrieve_duration_seconds` | — | Retrieve duration |

### OpenTelemetry Tracing

Each pipeline step is instrumented with OpenTelemetry spans:

```
pipeline.ingest
  ├── pipeline.detect          (auto mode only)
  ├── pipeline.convert
  ├── pipeline.extract
  ├── pipeline.quality
  ├── pipeline.chunk
  ├── pipeline.clean
  └── pipeline.vectorize

pipeline.retrieve
  ├── pipeline.hybrid_retrieve.vector_query  (hybrid mode only)
  ├── pipeline.hybrid_retrieve.bm25          (hybrid mode only)
  ├── pipeline.hybrid_retrieve.fuse          (hybrid mode only)
  └── [reranker via LLM metrics]

pipeline.orchestrate         (hybrid profiles only)
```

Tracing is disabled by default. Enable with:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
```

Each span carries attributes: `step`, `profile`, `source`, `duration_ms`, and error details if the step fails.

### Grafana Dashboard

A pre-built Grafana dashboard is provisioned automatically with panels for:

- Pipeline step durations (p50, p95) per step and profile
- Quality score distribution per extraction engine
- Profile selection counters by reason
- LLM calls and duration per provider
- Cache hit ratio and entry count
- Reranker score distribution
- Ingestion and HTTP request rates
- Ingestion duration per profile
- Vector store document count
- Rate limit hits

```bash
# Start everything (pipeline + Prometheus + Grafana)
docker-compose up -d

# Open Grafana at http://localhost:3000
# Default login: admin / admin
# Dashboard: "RAG Pipeline Overview" (auto-provisioned)
```

The dashboard refreshes every 10s and covers the last 15 minutes by default.

### Prometheus + Docker

```bash
# Start Prometheus alongside the pipeline
docker-compose up prometheus

# Prometheus UI (CLI-friendly check):
curl http://localhost:9090/api/v1/targets
```

The Prometheus config at `monitoring/prometheus.yml` scrapes the pipeline every 15s.

---

## Docker

### Services

| Service | Port | Purpose |
|---|---|---|
| `rag-pipeline` | 8000 | API server |
| `prometheus` | 9090 | Metrics collection |
| `grafana` | 3000 | Pre-configured dashboard (auto-login: admin/admin) |

### Commands

```bash
# Build and start everything
docker-compose up --build -d

# View logs
docker-compose logs -f

# Run CLI commands inside the container
docker-compose exec rag-pipeline python scripts/run.py list-profiles
docker-compose exec rag-pipeline python scripts/run.py ingest /data/input/doc.pdf --profile hybrid

# Stop
docker-compose down

# Rebuild after code changes
docker-compose up --build -d
```

### Volumes

| Host path | Container path | Purpose |
|---|---|---|
| `./data` | `/app/data` | ChromaDB persistence + output |
| `./profiles.yaml` | `/app/profiles.yaml` | Profile configuration |
| `./scripts/docling-evaluate.py` | `/app/scripts/docling-evaluate.py` | Quality evaluation script |

### Build Arguments

| Arg | Default | Description |
|---|---|---|
| `INCLUDE_EXTRAS` | `false` | Install optional dependencies (PyMuPDF, pdfplumber, camelot, unstructured) |

```bash
docker build --build-arg INCLUDE_EXTRAS=true -t rag-pipeline:latest .
```

---

## Common Workflows

### Ingest + Search (end-to-end)

```bash
# 1. Ingest a document
python scripts/run.py ingest ~/report.pdf --profile hybrid

# 2. Search
python scripts/run.py retrieve "key findings" --k 5

# 3. Use results with an LLM
# The "llm" format produces ready-to-inject context:
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "key findings", "k": 5, "format": "llm"}'
# → {"context": "[1] Source: report.pdf | Page: 3 | Section: Results\n{text}\n\n---\n\n[2] ..."}
```

### Compare Profiles on the Same Document

```bash
# Run ingested with different profiles and compare results:
python scripts/run.py ingest ~/doc.pdf --profile standard
python scripts/run.py ingest ~/doc.pdf --profile hybrid  # re-ingest replaces old chunks

# Check quality metrics for each:
curl http://localhost:8000/metrics | grep engine_quality_score
curl http://localhost:8000/metrics | grep pipeline_step_duration_seconds
```

### Monitor Pipeline Performance

```bash
# Start the API server
uvicorn src.api.server:app --host 0.0.0.0 --port 8000

# In a separate terminal, watch metrics:
watch -n 2 "curl -s http://localhost:8000/metrics | grep -E '(rag_pipeline_step|rag_engine_quality|rag_llm_calls)'"

# Ingest a document
python scripts/run.py ingest ~/test.pdf --profile hybrid

# Observe the metrics update in real-time
```

---

## Troubleshooting

### No modules found

```bash
pip install -r requirements-core.txt
pip install -e .
```

### Port already in use

```bash
# Change port
API_PORT=8001 uvicorn src.api.server:app --host 0.0.0.0 --port 8001
```

### Document ingestion fails

```bash
# Check the error message
python scripts/run.py ingest ~/doc.pdf --profile standard

# Try detect first to see what's suggested
python scripts/run.py detect ~/doc.pdf

# Try a different profile
python scripts/run.py ingest ~/doc.pdf --profile ocrmac
python scripts/run.py ingest ~/doc.pdf --profile fast
```

### Prometheus won't start

```bash
docker-compose logs prometheus
# Common fix: check monitoring/prometheus.yml syntax
```

### Docker build fails

```bash
# Try without extras first
docker build --build-arg INCLUDE_EXTRAS=false -t rag-pipeline:latest .

# If dependencies fail, check your Docker network/DNS
docker build --network=host -t rag-pipeline:latest .
```

### Performance is slow

- Use `--profile fast` for large born-digital PDFs
- Use `--profile large_document` for 150+ page documents
- Use `--skip-quality` to skip the quality check (faster but no quality metadata)
- Reduce chunk size with `CHUNK_MAX_TOKENS` env var

### No results from retrieve

```bash
# Check if any documents are in the store
python scripts/run.py status

# Re-ingest with a more appropriate profile
python scripts/run.py ingest ~/doc.pdf --profile auto

# Check if the BM25 index needs rebuilding (happens automatically on ingest)
```
