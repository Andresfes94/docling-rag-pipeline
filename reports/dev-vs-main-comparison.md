# Dev vs Main — Branch Comparison Report

**Generated**: 2026-07-19
**Dev branch**: `7052bef` (1 commit ahead of `origin/main`)
**Main branch**: `178db22` (on GitHub)

---

## 1. High-Level Diff

```
126 files changed, 43156 insertions(+), 243 deletions(-)
```

The dev branch contains **all work from Sessions 8, 9, and 10** — approximately 8 full days of engineering across 3 roles (Backend Engineer, Data Engineer, DevOps Engineer).

---

## 2. New Modules (Not in Main)

| Module | Role | Lines | Purpose |
|---|---|---|---|
| `src/config.py` | Backend | 63 | Centralized `Settings` dataclass with env var loading |
| `src/api/auth.py` | Backend | 58 | API key authentication middleware |
| `src/api/state.py` | Backend | 144 | Redis-backed state stores (tasks, cache, rate limit) |
| `src/api/metrics.py` | Both | 117 | Prometheus metrics (HTTP, ingest, retrieve, LLM, cache, rate limit) |
| `src/api/logging_config.py` | Both | 74 | Structured JSON logging with request_id + elapsed_ms |
| `src/api/tracing.py` | DevOps | 47 | OpenTelemetry tracing (opt-in) |
| `src/api/validation.py` | Backend | 69 | Source validation for ingest endpoint |
| `src/ingestion/cleaner.py` | Data | 130 | Text cleaning: Unicode, PII, whitespace, dedup, length filter |
| `src/retrieval/reranker.py` | Backend | 91 | Cross-encoder reranker for improved search relevance |
| `src/retrieval/hybrid_search.py` | Backend | 131 | BM25 retriever + Reciprocal Rank Fusion |

---

## 3. Files Significantly Modified

| File | Diff | Changes |
|---|---|---|
| `src/api/server.py` | +250 lines | DI refactor, auth, CORS env, .env config, SSE try/except, auth reload, tracing, reranker init |
| `src/retrieval/pipeline.py` | +45 lines | TextCleaner integration, reranker wiring in `retrieve()` |
| `src/llm/client.py` | +20 lines | `list_models()` tag fix, env-based base URLs |
| `Dockerfile` | Full rewrite | Multi-stage, split deps, `INCLUDE_EXTRAS` arg, healthcheck |
| `.github/workflows/ci.yml` | Full rewrite | Separate integration job, schedule-only |
| `src/storage/vector_store.py` | +72 lines | threading.Lock, enable_async(), idempotent re-ingest |

---

## 4. Graphify Architecture Comparison

### Main branch architecture:
```
Ingestion → Extractor → Chunker → VectorStore → ANN retrieve
```
- **Single-stage retrieval**: HNSW ANN only
- **No data cleaning**: Raw text goes to embedder
- **No reranking**: Chroma distance order only
- **No auth**: Everything public
- **No metrics**: Zero observability
- **No config**: All paths hardcoded
- **Monolith Dockerfile**: All deps, no split

### Dev branch architecture:
```
Ingestion → Extractor → Chunker → TextCleaner → VectorStore
                                                      │
                                                      ▼
Response ← Reranker ← ANN (k*3)  ← Embedder ← Query
                               
Auth (API key)     Redis (state/cache/rate)     .env config
Prometheus metrics     JSON logging     OpenTelemetry (opt-in)
```

- **Multi-stage retrieval**: ANN → Cross-encoder reranker → sorted results
- **Data cleaning pipeline**: Unicode repair → whitespace normalization → PII stripping → dedup → length filter
- **Full auth**: API key middleware with rotation webhook
- **Observability**: 15+ Prometheus metrics, structured JSON logs, request tracing
- **Configuration**: 17 environment variables, .env file, startup validation
- **Docker**: Multi-stage, 3-way deps split, build-arg extras, healthcheck

---

## 5. Test Coverage Delta

| Metric | Main | Dev | Delta |
|---|---|---|---|
| Total tests | 0 (no test suite on main) | 123 | +123 |
| Unit tests | 0 | 114 | +114 |
| Integration tests | 0 | 9 | +9 |
| Test files | 0 | 14 | +14 |

---

## 6. Key Structural Changes

### Data flow (before → after):
```
BEFORE: source → Docling → extract → chunk → embed → store → ANN retrieve
AFTER:  source → validate → Docling → extract → chunk → clean → embed → store
                                                                     ↓
                                                              ANN retrieve (k*3)
                                                                     ↓
                                                              Cross-encoder rerank
                                                                     ↓
                                                              BM25 + RRF (future)
                                                                     ↓
                                                              Response
```

### Deployment (before → after):
```
BEFORE: docker-compose with hardcoded paths, no .env
AFTER:  .env.example with 17 vars, env_file in compose, startup validation
```

### CI (before → after):
```
BEFORE: single `pytest tests/` job
AFTER:  lint → typecheck → test (unit) → build → integration (schedule-only)
```

---

## 7. API Surface Changes

| Endpoint | Main | Dev |
|---|---|---|
| `GET /health` | ✅ | ✅ (unchanged) |
| `POST /ingest` | ✅ | ✅ + source validation (400 on invalid) |
| `POST /retrieve` | ✅ | ✅ + `rerank`, `min_rerank_score` params |
| `GET /retrieve/stream` | ✅ | ✅ + `rerank`, `min_rerank_score` params |
| `GET /documents` | — | ✅ |
| `DELETE /documents/{source}` | — | ✅ |
| `GET /status` | — | ✅ |
| `POST /auth/reload` | — | ✅ |
| `GET /metrics` | — | ✅ (Prometheus) |
| SSE events | — | + `event: error` on exceptions |
