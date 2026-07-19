# Data Engineer Report — Docling RAG Pipeline

**Author**: Data Engineer
**Date**: 2026-07-19
**Status**: ✅ All assigned tasks complete

---

## 1. Executed Tasks

### TICKET-005: End-to-End Integration Tests (P1, Complete)
**Owner transitioned**: QA → Data Engineer
**Files**: `tests/test_integration.py`, `tests/fixtures/`, `tests/conftest.py`

9 integration tests covering the full ingest → chunk → embed → store → retrieve → delete pipeline:

| Test | Scenarios | What It Proves |
|---|---|---|
| `test_ingest_pdf_creates_chunks` | PDF → Docling → chunks → Chroma | Whole pipeline works with born-digital PDF |
| `test_ingest_xlsx_creates_chunks` | Excel → Docling → chunks → Chroma | Non-PDF ingestion works |
| `test_ingest_then_retrieve` | Ingest → query → verify results | Retrieval returns semantically relevant text |
| `test_auto_detect_selects_standard_profile` | Auto-profile → verify `standard` selected | Document detection is accurate |
| `test_retry_chain_triggers_on_empty_document` | Image-only PDF → retry to VLM/OCR | Graceful degradation on unreadable docs |
| `test_ingest_with_quality_check` | Ingest + quality eval → verify status | Quality gates fire during pipeline |
| `test_delete_removes_chunks` | Delete → verify Chroma cleared | Document lifecycle works |
| `test_multiple_ingests_isolation` | 2 pipelines, temp dirs → no cross-contamination | Test isolation confirmed |
| `test_reingest_idempotent_no_duplicates` | Ingest → re-ingest → same chunk count | Idempotency enforced |

**Fixtures created** (`tests/fixtures/`):
- `sample_text.pdf` (2.2KB, 2-page born-digital PDF, known text about quantitative trading)
- `sample_image.pdf` (1.3KB, 1-page image-only PDF) 
- `sample.xlsx` (5.2KB, 10-row trade log spreadsheet)

**Design decisions**:
- All tests marked `@pytest.mark.integration` — excluded from `pytest tests/` without `-m integration`
- Each test uses a temp Chroma directory via `tmp_path` fixture
- Pipeline fixtures in `conftest.py` accept injection for persist_directory, profiles_path, output_dir
- 9 tests run in ~50s total (embedding model loading shared via `_MODEL_CACHE`)

### Production-Grade Quality Checks (Complete)
**File**: `src/ingestion/quality.py` — `_basic_fallback()` rewritten

**Before**: 2 checks (total_chars < 100, markdown < 200)

**After**: 8 checks:

| Check | Threshold | Catches |
|---|---|---|
| Total text content | < 100 chars | Empty documents |
| Text density | < 50 chars/page, > 1 page | Scanned/image-heavy docs |
| Garbled text | > 10 Unicode replacement chars (`\ufffd`) | Encoding corruption |
| Section headers | 0 headers on ≥ 3-page doc | Unstructured/raw text |
| Duplicate content | > 2 repeats or > 20% repetition | Boilerplate, header/footer contamination |
| Page coverage | < 50% of pages have text | Image-only pages |
| Markdown length | < 200 chars | Failed markdown export |
| Metrics | page_count, chars_per_page, section_headers, replacement_chars, coverage | Composability |

**Test coverage**: 12 quality tests (7 new) — garbled detection, low text, page coverage, duplicate detection, section headers presence/absence.

### Idempotent Ingestion (Complete)
**File**: `src/storage/vector_store.py` — `add_document()` rewritten

**Before**: Blind `INSERT` — re-ingesting the same source created duplicate chunks.

**After**: Delete-then-insert — `add_document()` first deletes all existing chunks for `source`, then inserts new ones. Chunk IDs use `{source}_chunk_{index}` format.

**Why delete-then-insert vs. upsert**: Chroma's API does not support upsert by metadata filter. Delete-then-insert in the same method call is atomic-enough for single-process usage and guarantees no orphans.

**Verified**: `test_reingest_idempotent_no_duplicates` — re-ingesting the same PDF produces identical chunk count.

### Prometheus Metrics (TICKET-009, Complete)
**File**: `src/api/metrics.py` (new)

| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `rag_http_requests_total` | Counter | method, endpoint, status (2xx/4xx/5xx) | Traffic monitoring |
| `rag_http_request_duration_seconds` | Histogram | method, endpoint | Latency SLOs |
| `rag_ingest_documents_total` | Counter | profile, status | Ingestion throughput |
| `rag_ingest_duration_seconds` | Histogram | profile | Per-profile speed |
| `rag_retrieve_requests_total` | Counter | cache_hit | Cache effectiveness |
| `rag_retrieve_chunks_total` | Counter | — | Volume of data served |
| `rag_retrieve_duration_seconds` | Histogram | — | Query latency |
| `rag_llm_calls_total` | Counter | provider, status | LLM usage tracking |
| `rag_llm_duration_seconds` | Histogram | provider | Per-provider latency |
| `rag_cache_hits_total` | Counter | — | Cache hit rate |
| `rag_vector_store_documents_total` | Counter | — | Store growth |

Endpoint `GET /metrics` returns Prometheus-compatible text format, excluded from OpenAPI schema (`include_in_schema=False`).

### Structured JSON Logging (TICKET-008, Complete)
**File**: `src/api/logging_config.py` (new)

- **Format**: `LOG_FORMAT=json` env var enables JSON, default is `text` (local dev)
- **Fields**: `timestamp`, `levelname`, `name`, `message`, `request_id`
- **Request correlation**: `contextvars.ContextVar` propagates request_id from middleware to all log records within a request context
- **Noise reduction**: chromadb, httpx, urllib3, docling, sentence_transformers set to WARNING
- **Uvicorn access logs**: Also routed through the JSON formatter

---

## 2. Test Matrix

| Suite | Count | Duration | Notes |
|---|---|---|---|
| Unit tests (`test_*.py` excl. integration) | 33 | 3.5s | 26 original + 7 new quality tests |
| Integration tests | 9 | 50s | Requires `-m integration`, real Docling + Chroma |
| **Total** | **42** | **~54s** | All passing |

### Running
```bash
# All unit tests
pytest tests/ --ignore=tests/test_integration.py

# Integration tests only (slow)
pytest tests/test_integration.py

# Everything
pytest tests/
```

---

## 3. Data Engineering Principles Applied

| Principle | Implementation |
|---|---|
| **Idempotency** | `VectorStore.add_document()` deletes before insert — safe to re-run |
| **Data quality built-in** | `_basic_fallback()` runs 8 checks at ingestion time |
| **Gap detection** | Page coverage, section header, duplicate detection all flag structural gaps |
| **Schema validation** | Pydantic models on API boundary; DocumentChunk/ChunkingResult dataclasses enforce internal shape |
| **Idempotent retry** | Retry chain uses delete-then-insert on re-ingest |
| **Observability** | Prometheus counters + structured JSON logging with request_id |
| **Test isolation** | Temp Chroma dirs, no shared state between tests |
| **Real documents in tests** | `tests/fixtures/` checked into repo — no mock responses |

---

## 4. File Inventory

| File | Action | Lines | Purpose |
|---|---|---|---|
| `tests/test_integration.py` | **CREATE** | 130 | 9 integration tests |
| `tests/fixtures/create_fixtures.py` | **CREATE** | 85 | Fixture generator (PDF+XLSX+image) |
| `tests/fixtures/sample_text.pdf` | **CREATE** | 2.2KB | Born-digital PDF fixture |
| `tests/fixtures/sample_image.pdf` | **CREATE** | 1.3KB | Image-only PDF fixture |
| `tests/fixtures/sample.xlsx` | **CREATE** | 5.2KB | Spreadsheet fixture |
| `tests/conftest.py` | **MODIFY** | 65 | Added pipeline, fixture path, tmp_chroma fixtures |
| `tests/test_quality.py` | **MODIFY** | 130 | 7 new quality tests (was 5) |
| `src/ingestion/quality.py` | **MODIFY** | 210 | Enhanced `_basic_fallback()` (was 141 lines) |
| `src/storage/vector_store.py` | **MODIFY** | 192 | Idempotent add_document (was 182 lines) |
| `src/api/metrics.py` | **CREATE** | 111 | Prometheus metrics |
| `src/api/logging_config.py` | **CREATE** | 67 | Structured JSON logging |
| `src/api/server.py` | **MODIFY** | 455 | Metrics integration, logging setup, request_id context |
| `pyproject.toml` | **MODIFY** | 60 | Added prometheus-client, python-json-logger, integration marker |
| `data-engineer-report.md` | **CREATE** | — | This report |

---

## 5. Remaining Gaps (Handoff to Backend/DevOps)

These items were out of scope for this pass but identified as important:

1. **Redis-backed state** (TICKET-001): Current metrics/logging are per-process. Multi-instance needs Redis for aggregated counters.
2. **`scripts/docling-evaluate.py`** (external): The evaluator script referenced by `quality.py` is not checked into the repo. The `_basic_fallback()` path handles its absence, but the full evaluator would provide richer quality signals.
3. **CI job for integration tests**: Integration tests are currently manual-only (`-m integration`). A scheduled CI job would catch regressions.
4. **Chroma concurrency control** (TICKET-006): `add_document()` has no lock. Safe for single-process batch, but concurrent API requests could race.
5. **Docker image**: `prometheus-client` and `python-json-logger` dependencies were added to pyproject.toml — Docker build will pick them up on next build.
