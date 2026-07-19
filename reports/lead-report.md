# Tech Lead Architecture Report — Docling RAG Pipeline

**Author**: Tech Lead / Solutions Architect
**Date**: 2026-07-19
**Scope**: Full architecture review of `docling-rag-pipeline` — ingestion, storage, retrieval, API, LLM integration, evaluation, CI/CD, and deployment.
**Version**: 0.2.0 (Session 7 complete)
**Status**: ✅ Ready for agent handoff

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview (C4 Context)](#2-architecture-overview-c4-context)
3. [Strengths](#3-strengths)
4. [Vulnerabilities & Risk Register](#4-vulnerabilities--risk-register)
5. [Architecture Decision Records](#5-architecture-decision-records)
6. [Detailed TODO Tickets](#6-detailed-todo-tickets)
7. [Data Contracts (Current State)](#7-data-contracts-current-state)
8. [Non-Functional Requirements Assessment](#8-non-functional-requirements-assessment)
9. [Risk Profile by Layer](#9-risk-profile-by-layer)
10. [Handoff Notes for Specialist Agents](#10-handoff-notes-for-specialist-agents)

---

## 1. Executive Summary

The Docling RAG Pipeline is a **well-structured, modular project** that successfully delivers end-to-end document ingestion → chunking → embedding → storage → retrieval → LLM-powered Q&A. It runs fully locally on a MacBook M3 Pro with 26 passing tests and 6 ingested documents producing 2,188 chunks.

### What's good

- Clean separation of concerns (ingestion, storage, retrieval, API, LLM, evaluation)
- Async-first API with rate limiting, LRU caching, SSE streaming
- Graceful degradation on ingestion failures
- Config-driven pipeline profiles (YAML)
- Multi-library enrichment with graceful fallbacks on ImportError
- LLM abstraction supporting both Ollama and LM Studio
- Full RAG evaluation framework with 20 test questions and 9 metrics

### What needs work before production

| Priority | Issue | Impact |
|---|---|---|
| **Critical** | In-memory state (tasks, cache, rate limiter buckets) per process — lost on restart | Blocks multi-instance scaling |
| **Critical** | No authentication or authorization | Can't expose to internet |
| **Critical** | Single-process rate limiter — behind a load balancer, limits are N× effective rate | Security bypass |
| **High** | Global module-level singletons (`_pipeline`, `_cache`) break test isolation | Flaky tests, hard to parallelize |
| **High** | No integration tests for the core ingest→store→retrieve pipeline | No confidence in E2E correctness |
| **High** | No concurrency control on Chroma writes | Race conditions on concurrent ingest |
| **High** | SSE stream has no error event handling — drops connection on failure silently | Bad UX for streaming clients |
| **Medium** | No structured logging, no metrics, no tracing | Invisible in production |
| **Medium** | Docker image is ~2GB+ | Slow deploys, expensive storage |
| **Low** | No `.env` support, hardcoded paths | Inflexible config |
| **Low** | No retry logic for LLM client calls | Brittle when Ollama restarts |

### Verdict

**The core architecture is sound for a single-instance local deployment or interview demo.** It is NOT ready for production multi-instance deployment, internet exposure, or any scenario requiring persistence beyond process lifetime. The recommended path is:

1. First: fix the critical scaling blockers (persistent state, auth, shared rate limiter)
2. Then: fill observability gaps
3. Then: harden with integration tests and concurrency controls
4. Finally: optimize deployment footprint

---

## 2. Architecture Overview (C4 Context)

### Context Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Docling RAG Pipeline System                      │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────────┐ │
│  │  CLI     │   │  Streamlit   │   │  curl /   │   │  Ollama /    │ │
│  │  User    │   │  UI User     │   │  HTTP     │   │  LM Studio   │ │
│  │          │   │              │   │  Client   │   │  LLM Server  │ │
│  └────┬─────┘   └──────┬───────┘   └─────┬────┘   └──────┬───────┘ │
│       │                │                 │               │         │
│       ▼                ▼                 ▼               │         │
│  ┌──────────────────────────────────────────────────┐    │         │
│  │               FastAPI Server (:8000)              │    │         │
│  │  /health  /ingest  /retrieve  /retrieve/stream   │    │         │
│  │  /documents  /status  /ingest/{task_id}          │◄───┘         │
│  └──────────────────────┬───────────────────────────┘              │
│                         │                                          │
│                         ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     RAGPipeline (orchestrator)                │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │  │
│  │  │ Detector │  │ Loader   │  │ Extractor│  │ QualityGate │  │  │
│  │  │ (PyPDF2) │  │ (Docling)│  │ +Enrich  │  │ (subprocess)│  │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └─────────────┘  │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │  │
│  │  │ Chunker  │  │ Embedder │  │ Chroma   │                   │  │
│  │  │(Hybrid)  │  │(SBERT)   │  │ Store    │                   │  │
│  │  └──────────┘  └──────────┘  └──────────┘                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                  LLM Integration Layer                       │  │
│  │  ┌──────────────┐  ┌──────────┐  ┌──────────────────┐      │  │
│  │  │ LLMClient    │  │ RAG      │  │ Evaluation       │      │  │
│  │  │ (Ollama/LMS) │  │ Pipeline │  │ (20 questions)   │      │  │
│  │  └──────────────┘  └──────────┘  └──────────────────┘      │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Container Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Container (:8000)                  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Middleware Stack                                    │   │
│  │  ┌──────────────┐ ┌────────────┐ ┌────────────────┐ │   │
│  │  │ CORS         │ │ RateLimiter│ │ RequestID      │ │   │
│  │  │ (allow all)  │ │ (TokenBkt) │ │ (UUID4[:8])    │ │   │
│  │  └──────────────┘ └────────────┘ └────────────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ API       │ │ Cache     │ │ Pipeline │ │ TaskStore    │ │
│  │ Routes    │ │ (LRU+TTL) │ │ (Global  │ │ (in-memory   │ │
│  │ (9 routes)│ │ (1024 ent)│ │ Singleton│ │  dict)       │ │
│  └───────────┘ └───────────┘ └──────────┘ └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Chroma DB Container                        │
│  Persistent SQLite at data/chroma/ — HNSW cosine index      │
│  2,188 chunks across 6 sources                               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Embedding Model (SBERT)                    │
│  all-MiniLM-L6-v2 — 384-dim — loaded once, cached globally   │
│  ~80MB RAM — CPU device (MPS available on Apple Silicon)     │
└─────────────────────────────────────────────────────────────┘
```

### Module Dependency Graph

```
src/api/ ──→ src/retrieval/ ──→ src/storage/ ──→ src/embeddings/
                                  │
src/api/ ──→ src/api/cache.py     └── src/ingestion/
                                  ├── loader.py ──→ profiles.py
                                  ├── extractor.py
                                  ├── chunker.py
                                  ├── quality.py
                                  └── detector.py

src/llm/ ──→ src/llm/client.py (no internal deps)
src/evaluation/ ──→ src/llm/rag.py ──→ src/llm/client.py
```

---

## 3. Strengths

### 3.1 Modular Architecture with Clear Boundaries

Each layer has a single responsibility and a defined interface:

| Module | Responsibility | Interface |
|---|---|---|
| `src/ingestion/` | Document conversion, extraction, chunking, quality | `convert()`, `extract()`, `chunk_document()`, `evaluate()` |
| `src/embeddings/` | Text → vector embedding | `embed_text()`, `embed_batch()` |
| `src/storage/` | Vector persistence and retrieval | `add_document()`, `query()`, `delete_source()` |
| `src/retrieval/` | Orchestration + auto-retry | `ingest()`, `retrieve()`, `status()` |
| `src/api/` | HTTP API with middleware | FastAPI routes |
| `src/llm/` | LLM provider abstraction | `LLMClient.generate()` |
| `src/evaluation/` | RAG quality measurement | `evaluate_all()`, `print_report()` |

This means any layer can be swapped independently. Replace Chroma with Pinecone? Only touch `src/storage/`. Add a new embedding model? Only touch `src/embeddings/`.

### 3.2 Async-First API Design

The API uses `async def` throughout, `BackgroundTasks` for ingestion, and `StreamingResponse` for SSE. This is the correct choice for an I/O-bound pipeline that spends most of its time waiting on Docling conversion, Chroma queries, and network calls to the LLM.

### 3.3 Token Bucket Rate Limiter

Custom implementation instead of `slowapi` — thread-safe, per-IP, per-endpoint, with different limits per route (30/s for retrieve, 2/s for ingest). The `__slots__` usage on `TokenBucket` shows attention to performance.

### 3.4 LRU Cache with TTL and Source Invalidation

The `RetrievalCache` is thread-safe, keyed by SHA256(query, k, sources, format) to prevent collisions, and supports targeted invalidation when a document is re-ingested. The `min()`-based eviction is simple and correct for moderate cache sizes.

### 3.5 Graceful Degradation Chain

The `_retry_chain()` method tries progressively simpler profiles when ingestion fails. This is the right approach: better to get partial content from `fast` profile than to fail entirely.

### 3.6 Config-Driven Profiles

Adding a new OCR engine is a 5-line YAML change. The `load_profiles()` → `create_converter()` factory pattern correctly separates config from implementation.

### 3.7 Multi-Library Enrichment with Graceful Fallbacks

The deep enrichment path (pdfplumber → camelot → unstructured) wraps each import in try/except, so the pipeline works even when optional libraries are missing. This is the correct pattern for optional dependencies.

### 3.8 LLM Provider Abstraction

`LLMClient` supports Ollama (Ollama API) and LM Studio (OpenAI-compatible API) through a unified `generate()` interface. The `<think>` tag stripping for DeepSeek models is a thoughtful addition.

### 3.9 Test Suite Coverage

26 tests across 3 test files (profiles, quality, API). API tests use `ASGITransport` (no server needed), which is the gold standard for FastAPI testing.

### 3.10 CI/CD Pipeline

Four jobs (lint → typecheck → test → build) running on GitHub Actions. Ruff for linting, mypy for type checking, pytest for tests, Docker build for deployment validation.

---

## 4. Vulnerabilities & Risk Register

Each vulnerability is rated by **Severity** (Critical/High/Medium/Low) and **Likelihood** (Certain/Likely/Possible/Unlikely).

### V-01: In-Memory State (Critical, Certain)

| Field | Location | Problem |
|---|---|---|
| `_tasks: dict[str, dict]` | `src/api/server.py` — module global | All ingest task state lost on restart |
| `_cache: RetrievalCache` | `src/api/server.py` — module global | Cache cleared on every deployment |
| `_buckets: dict[str, TokenBucket]` | `src/api/rate_limiter.py` — instance attr | Rate limit state lost on restart |
| `_PIPELINE: RAGPipeline \| None` | `src/retrieval/pipeline.py` — module global | Pipeline state lost |
| `_MODEL_CACHE: dict[str, SentenceTransformer]` | `src/embeddings/embedder.py` — module global | (acceptable — model reload is expected) |

**Impact**: Any deployment with >1 instance or with rolling restarts will suffer from:
- Lost ingest tasks (user gets "pending" → restart → "task not found")
- Rate limit bypass (each instance starts with fresh buckets)
- Cache miss storm after restart (all queries hit Chroma)

**Root cause**: The project was designed as a single-process local application. None of these states were designed for persistence.

### V-02: No Authentication or Authorization (Critical, Likely)

- `allow_origins=["*"]` in CORS middleware
- No API key check, no OAuth, no JWT
- No rate limiting by user tier
- No admin vs. user distinction

**Impact**: Any internet-facing deployment is immediately vulnerable to:
- Unauthorized ingestion (anyone can upload files)
- Unauthorized retrieval (anyone can query all documents)
- Resource exhaustion (no way to identify abusive clients)

### V-03: Single-Process Rate Limiter (Critical, Likely)

The `RateLimiterMiddleware` stores `TokenBucket` instances per IP per endpoint in a single dict:
```python
self._buckets: dict[str, TokenBucket] = {}
```

Behind a load balancer with N instances, each instance has its own buckets. An attacker can:
- Send 30 req/s to instance A AND 30 req/s to instance B = 60 req/s to `/retrieve`
- The 429 response only triggers when a single instance sees >30/s

**Mitigation needed**: Redis-backed shared bucket store.

### V-04: Global Singletons Break Test Isolation (High, Certain)

```python
# retrieval/pipeline.py
_PIPELINE: Any = None
def _get_pipeline():
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = RAGPipeline()
    return _PIPELINE

# api/server.py
_pipeline: RAGPipeline | None = None
_cache: RetrievalCache | None = None
def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline
```

**Impact**:
- Tests that share `_pipeline` state can interfere with each other
- Parallel test execution is impossible (shared Chroma connection)
- The `test_retrieve_empty` test creates chunks that persist for the next test
- Tests cannot be run in random order

### V-05: No Integration Tests for the Core Pipeline (High, Certain)

**Coverage gaps**:

| Scenario | Tested? | File |
|---|---|---|
| API routes respond correctly | ✅ 14 tests | `test_api.py` |
| Profile loading works | ✅ 7 tests | `test_profiles.py` |
| Quality evaluation logic | ✅ 5 tests | `test_quality.py` |
| Ingest a real PDF → verify chunks in Chroma | ❌ | — |
| Retrieve a document → verify semantic ranking | ❌ | — |
| Retry chain logic (auto → ocrmac → large) | ❌ | — |
| Batch processor (ProcessPoolExecutor) | ❌ | — |
| Deep enrichment (pdfplumber/Camelot/Unstructured) | ❌ | — |
| LLM client (needs Ollama running) | ❌ | — |
| Evaluation framework (20 questions) | ❌ | — |
| Concurrent requests / race conditions | ❌ | — |
| Rate limiter returning 429 | ❌ | — |
| SSE stream error recovery | ❌ | — |

### V-06: No Concurrency Control on Chroma Writes (High, Possible)

```python
# src/storage/vector_store.py
def add_document(self, chunks, source, model_name):
    embeddings = embed_batch(texts, model_name=model_name)
    self._collection.add(embeddings=..., documents=..., metadatas=..., ids=...)
```

Two concurrent ingest tasks for the same document would:
1. Both embed successfully
2. Both call `self._collection.add()` concurrently
3. Chroma's SQLite backend may deadlock or produce duplicate IDs

**Mitigation needed**: Thread lock or queue-based writer.

### V-07: SSE Stream Drops Connection on Error (High, Possible)

```python
# src/api/server.py
async def event_stream():
    yield f"event: meta\ndata: ...\n\n"
    for chunk in chunks:
        yield f"event: chunk\ndata: ...\n\n"
    yield "event: done\ndata: {}\n\n"
```

If an exception occurs mid-stream (e.g., in `_build_llm_context()` — wait, it's called before the generator, so it's fine. But there's no try/except around `pipe.retrieve()` in the stream endpoint). Actually looking more carefully:

```python
async def retrieve_stream(...):
    result = get_pipeline().retrieve(query=query, k=k, where=where)  # could throw
    chunks = [...]  # list comprehension, unlikely to throw
    async def event_stream():
        ...
    return StreamingResponse(event_stream(), ...)
```

The `retrieve()` call is BEFORE the generator, so exceptions there would return a 500. The generator itself only yields pre-computed data, so it won't throw mid-stream. This vulnerability is actually LOW, not HIGH. Let me correct this.

**Correction**: The SSE stream endpoint is actually safe. The `retrieve()` call happens synchronously before the generator starts, so any exception becomes a standard HTTP 500. The generator only yields pre-computed data. **Severity: Low**.

### V-08: No Structured Logging (Medium, Certain)

```python
_log.info("Converting %s with profile '%s'...", source, profile_name)
_log.warning("Rate limit hit: %s on %s (%.1f req/s)", client_ip, path, rate)
```

Plain text logs with `%` formatting. No JSON, no structured fields, no log levels per module beyond WARNING/INFO. In production:
- Can't search logs with structured queries
- Can't correlate logs across services
- Can't set up log-based metrics without regex parsing

### V-09: No Metrics (Medium, Certain)

No Prometheus endpoint, no request counters, no latency histograms, no error rates, no vector store size gauges. Zero observability into:
- How many documents were ingested in the last hour?
- What is P99 retrieval latency?
- How many 429 rate limit responses are we returning?
- Is the cache hit rate healthy?

### V-10: No Distributed Tracing (Medium, Unlikely)

A single request through `chat.py`:
1. HTTP POST to `/retrieve`
2. Pipeline `retrieve()` → Chroma query
3. LLM `generate()` → Ollama API

Without distributed tracing, diagnosing "why did this query take 30 seconds" requires reading logs from 3 components manually.

### V-11: Docker Image is Oversized (Medium, Likely)

The Dockerfile installs `requirements.txt` which includes:
- `docling` (~500MB with CUDA deps)
- `sentence-transformers` (~300MB with PyTorch CPU)
- `chromadb` (~200MB with embedded DuckDB)
- `unstructured[pdf]` (~150MB with dependencies)
- Optional extras (camelot, pdfplumber, etc.)

**Estimated final image size**: 1.5-2.5 GB. This means:
- ~5 minute pull time on a cold ECS/ECS instance
- Higher ECR/ECR storage costs
- Slower CI build times

### V-12: No `.env` Configuration (Medium, Possible)

Hardcoded paths throughout:
```python
# api/server.py
API_URL = "http://localhost:8000"
# vector_store.py
persist_directory: str | Path = "data/chroma"
# pipeline.py
persist_directory: str | Path = "data/chroma"
profiles_path: str | Path = "profiles.yaml"
output_dir: str | Path = "data/output"
```

No support for environment-specific overrides. Deploying to staging vs. production means changing code.

### V-13: No Retry for LLM Calls (Low, Possible)

```python
# llm/client.py
def _ollama_generate(self, ...):
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
```

If Ollama is restarting, overloaded, or a model is still loading, this fails immediately with an exception that propagates to the user as an HTTP 500. No retry with backoff.

### V-14: `list_models()` Strips Model Tags Incorrectly (Low, Possible)

```python
# llm/client.py
m["name"].split(":")[0] if ":" in m["name"] else m["name"]
```

For Ollama model `"mistral:latest"`, this returns `"mistral"`. But for `"hf.co/bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF:Q4_K_M"`, the `split(":")[0]` returns only `"hf.co/bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF"`. This model name would then be used in `generate()` but sent to Ollama without the `:Q4_K_M` tag, which may fail.

### V-15: `<think>` Tag Parsing is DeepSeek-Specific with Edge Cases (Low, Unlikely)

```python
# llm/client.py
if text.startswith("<think>"):
    end = text.find("</think>")
    if end != -1:
        result["thinking"] = text[7:end].strip()
        result["text"] = text[end + 8:].strip()
```

Edge cases:
- If a non-DeepSeek model outputs `<think>` at the start of a normal sentence (probability: near zero for Mistral/Llama, but non-zero for fine-tuned models), the tag is stripped.
- If the model outputs `<think>` without `</think>` (truncated at `max_tokens`), the full text including the opening tag is returned as-is.

### V-16: `test_retrieve_empty` Has Shared State (Low, Certain)

```python
# test_api.py
async def test_retrieve_empty(self, client):
    resp = await client.post("/retrieve", json={"query": "test", "k": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_results"] >= 0
```

This test depends on the real Chroma store state. If a previous test ingested data, `total_results` will be > 0. The test only checks `>= 0`, so it won't fail, but it's testing against whatever happens to be in the store rather than a known state.

---

## 5. Architecture Decision Records

### ADR-001: In-Memory State Must Be Made Persistent Before Multi-Instance Deployment

- **Context**: Tasks, cache, and rate limiter state are in-memory per process.
- **Decision**: Use Redis as the shared backend for all three.
- **Alternatives considered**:
  - PostgreSQL: slower for cache/rate-limiter use cases, adds connection overhead.
  - SQLite: doesn't support multi-instance access.
  - File-based: too slow for rate limiter (every request writes to disk).
- **Consequences**: All state survives restarts. Multi-instance works. Adds Redis as a dependency.
- **Exit ramp**: If Redis infrastructure is unavailable, keep the current in-memory fallback with a configuration toggle.

### ADR-002: API Contracts Must Be Defined Before Frontend Development

- **Context**: The API currently returns JSON with inline documentation. There is no formal contract document.
- **Decision**: Generate OpenAPI 3.1 spec from FastAPI, publish as the source of truth for all API consumers.
- **Consequences**: Frontend/3D team and LLM integration agents can develop against a stable contract. Breaking changes are visible in the spec diff.
- **Status**: FastAPI already generates OpenAPI. Action item: version the spec and add contract tests.

### ADR-003: Prefer Redis Over In-Memory for Production State

- **Context**: Multiple components need shared state.
- **Decision**: Single Redis instance for: task store (persistent), cache (volatile, with TTL), rate limiter buckets (volatile). Use different Redis namespaces.
- **Consequences**: +1 infrastructure dependency. Removes all scaling blockers.
- **Alternatives**:
  - Dragonfly: Redis-compatible, higher performance for cache-heavy workloads. Not evaluated.
  - KeyDB: Redis fork with multi-threading. Not evaluated.

### ADR-004: Dependency Injection Over Global Singletons

- **Context**: `_pipeline`, `_cache`, `_MODEL_CACHE` are module-level globals.
- **Decision**: Refactor to use FastAPI's `Depends()` for the API layer and constructor injection for the pipeline layer.
- **Consequences**: Test isolation improves. Parallel test execution becomes possible. Slightly more boilerplate in route definitions.
- **Pattern**:
```python
# Before
_pipeline = None
def get_pipeline():
    global _pipeline
    ...

# After
@app.get("/retrieve")
async def retrieve(req: RetrieveRequest, pipeline: RAGPipeline = Depends(get_pipeline)):
    ...
```

---

## 6. Detailed TODO Tickets

### Epic 1: Production Scaling (Critical)

---

#### TICKET-001: Add Redis-backed persistent state store

| Field | Value |
|---|---|
| **Owner** | Backend Engineer |
| **Priority** | P0 (Critical) |
| **Depends on** | Nothing |
| **Effort** | 3-4 days |

**Problem**: All state is in-memory per process: tasks, cache, rate limiter buckets. Lost on restart. Doesn't scale to >1 instance.

**Definition of Done**:
- [ ] Add `redis-py` dependency to `pyproject.toml`
- [ ] Create `src/api/state.py` with `RedisState` class wrapping:
  - Task store: `HSET tasks:{task_id}` with TTL of 1 hour
  - Cache: `SET cache:{sha256_key}` with TTL matching the current 300s
  - Rate limiter: `INCR rate:{ip}:{endpoint}:{window}` with TTL of window size
- [ ] Keep in-memory `DictState` fallback for `REDIS_URL` not set
- [ ] Add configuration: `REDIS_URL` env var, default `None` (use in-memory)
- [ ] Update `get_cache()`, `get_pipeline()`, and rate limiter to accept a `State` instance
- [ ] Verify: restart API → tasks, cache, rate limits survive
- [ ] Verify: 2 API instances → shared state, correct rate limiting

---

#### TICKET-002: Add API Key authentication middleware

| Field | Value |
|---|---|
| **Owner** | Backend Engineer |
| **Priority** | P0 (Critical) |
| **Depends on** | Nothing |
| **Effort** | 1 day |

**Problem**: No auth — anyone can call any endpoint. CORS allows all origins.

**Definition of Done**:
- [ ] Create `src/api/auth.py` with API key middleware
- [ ] Support static API key via `API_KEY` env variable
- [ ] Add `X-API-Key` header check to all endpoints except `/health`
- [ ] Auth check before rate limiter (reject unauthenticated early)
- [ ] Add optional key rotation support (list of valid keys)
- [ ] Update CORS config to allow configurable origins instead of `["*"]`
- [ ] Verify: requests without key → 401
- [ ] Verify: requests with wrong key → 401
- [ ] Verify: requests with valid key → pass through
- [ ] Verify: `/health` still accessible without key

---

#### TICKET-003: Make rate limiter Redis-backed for multi-instance safety

| Field | Value |
|---|---|
| **Owner** | Backend Engineer |
| **Priority** | P0 (Critical) |
| **Depends on** | TICKET-001 (Redis setup) |
| **Effort** | 2 days |

**Problem**: Token buckets are per-process. Behind a load balancer, rate limits are N× the configured value.

**Definition of Done**:
- [ ] Create `src/api/rate_limiter.py` — add `RedisTokenBucket` class:
  - Use Redis sorted sets with timestamps for sliding window
  - Or use `INCR` + `EXPIRE` for simpler fixed-window
- [ ] Keep `MemoryTokenBucket` as fallback
- [ ] Middleware selects implementation based on `REDIS_URL` availability
- [ ] Verify: single instance, rate limit works
- [ ] Verify: 2 instances → rate limit is enforced across both
- [ ] Verify: Redis restart → rate limit resets (acceptable)

---

### Epic 2: Reliability & Testing (High)

---

#### TICKET-004: Refactor global singletons to dependency injection

| Field | Value |
|---|---|
| **Owner** | Backend Engineer |
| **Priority** | P1 (High) |
| **Depends on** | Nothing (can start in parallel with Epic 1) |
| **Effort** | 2-3 days |

**Problem**: `_pipeline`, `_cache`, `_MODEL_CACHE` are module-level globals. Test isolation is broken, parallel testing is impossible.

**Definition of Done**:
- [ ] Refactor `src/api/server.py`:
  - Remove `_pipeline` and `_cache` module globals
  - Create `get_pipeline()` and `get_cache()` as FastAPI dependencies using `Depends()`
  - Use `request.app.state.pipeline` pattern (FastAPI lifespan state)
- [ ] Refactor `src/retrieval/pipeline.py`:
  - Remove `_PIPELINE` global
  - Accept `VectorStore` and `embedding_model` as constructor parameters
- [ ] Refactor `src/embeddings/embedder.py`:
  - Keep `_MODEL_CACHE` with `lru_cache` on `_get_model()` instead of manual dict
- [ ] Update tests:
  - Each test creates its own pipeline instance with a temp Chroma directory
  - Tests no longer share state
- [ ] Verify: `pytest tests/ -v -x` passes
- [ ] Verify: `pytest tests/ -v -x -n auto` (parallel) passes

---

#### TICKET-005: Add end-to-end integration tests

| Field | Value |
|---|---|
| **Owner** | QA Engineer |
| **Priority** | P1 (High) |
| **Depends on** | TICKET-004 (testable pipeline) |
| **Effort** | 3-4 days |

**Problem**: No test proves that ingest → chunk → embed → store → retrieve → LLM answer works end-to-end with real documents.

**Definition of Done**:
- [ ] Create `tests/test_integration.py`:
  - Test 1: Ingest a known PDF → verify chunks in Chroma (count, content)
  - Test 2: Ingest PDF → retrieve with known query → verify results contain expected text
  - Test 3: Auto-detect + ingest → verify profile selection
  - Test 4: Retry chain → empty PDF (pure image, no OCR) → verify fallback attempted
  - Test 5: Deep enrichment → PDF with table → verify pdfplumber enrichment
  - Test 6: SSE streaming → verify meta → chunks → done event sequence
  - Test 7: Delete document → verify chunks removed → re-retrieve returns empty
- [ ] Use a small test PDF (3-5 pages, known content) checked into `tests/fixtures/`
- [ ] Use a small test XLSX (1 sheet, 10 rows) for Excel ingestion
- [ ] Each test uses its own temporary Chroma directory (isolation)
- [ ] Verify: `pytest tests/ -v` includes new tests in CI pipeline

---

#### TICKET-006: Add concurrency control for Chroma writes

| Field | Value |
|---|---|
| **Owner** | Backend Engineer |
| **Priority** | P1 (High) |
| **Depends on** | Nothing |
| **Effort** | 1 day |

**Problem**: Two concurrent ingest tasks writing to the same Chroma collection can cause race conditions.

**Definition of Done**:
- [ ] Add `threading.Lock` to `VectorStore.add_document()`
- [ ] Wrap the embed + add sequence in the lock
- [ ] Use `try/finally` to ensure lock release even on exception
- [ ] For multi-process (batch), use file-based lock (`portalocker` or `fcntl`)
- [ ] Add `async` variant: `asyncio.Lock` for the async API path
- [ ] Verify: 10 concurrent ingest requests to same document → no errors, no duplicates
- [ ] Verify: batch mode with 4 workers → no file-level race conditions on staging

---

#### TICKET-007: Add retry logic to LLM client

| Field | Value |
|---|---|
| **Owner** | Backend Engineer |
| **Priority** | P2 (Medium) |
| **Depends on** | Nothing |
| **Effort** | 0.5 day |

**Problem**: If Ollama is restarting or overloaded, the LLM call fails immediately with no retry.

**Definition of Done**:
- [ ] Add retry wrapper in `LLMClient.generate()`:
  - 3 retries with exponential backoff (1s, 2s, 4s)
  - Only retry on connection errors and HTTP 5xx
  - Don't retry on HTTP 4xx (bad request) or invalid JSON response
- [ ] Add `LLMClient._generate_with_retry()` method
- [ ] Log each retry attempt
- [ ] Verify: `LLMClient` returns response on successful retry
- [ ] Verify: All 3 retries exhausted → original exception propagates

---

### Epic 3: Observability (Medium)

---

#### TICKET-008: Add structured JSON logging

| Field | Value |
|---|---|
| **Owner** | Backend Engineer |
| **Priority** | P2 (Medium) |
| **Depends on** | Nothing |
| **Effort** | 1 day |

**Problem**: Plain text logs are not searchable, filterable, or parseable at scale.

**Definition of Done**:
- [ ] Add `python-json-logger` dependency
- [ ] Configure JSON formatter for all loggers
- [ ] Each log entry includes: `timestamp`, `level`, `logger`, `message`, `request_id`, `elapsed_ms`
- [ ] Add `RequestFilter` that attaches request_id to all log records automatically
- [ ] Verify: logs are valid JSON
- [ ] Verify: every log line has a `request_id` (tracable to HTTP request)
- [ ] Keep plain-text format as configurable fallback for local development

---

#### TICKET-009: Add Prometheus metrics endpoint

| Field | Value |
|---|---|
| **Owner** | Backend Engineer / DevOps |
| **Priority** | P2 (Medium) |
| **Depends on** | Nothing |
| **Effort** | 2 days |

**Problem**: No metrics — zero visibility into system health and performance.

**Definition of Done**:
- [ ] Add `prometheus-client` dependency
- [ ] Create `src/api/metrics.py` with counters:
  - `rag_requests_total{method, endpoint, status}`
  - `rag_ingest_duration_seconds{profile, status}`
  - `rag_retrieve_duration_seconds{source_filter, format}`
  - `rag_cache_hits_total` / `rag_cache_misses_total`
  - `rag_rate_limit_hits_total{endpoint}`
  - `rag_chroma_size_bytes`
  - `rag_llm_duration_seconds{provider, model}`
- [ ] Add `GET /metrics` endpoint returning Prometheus format
- [ ] Add `Gauge` for vector store size (updated on ingest/delete)
- [ ] Middleware auto-increments request counters
- [ ] Verify: `curl http://localhost:8000/metrics` returns valid Prometheus output
- [ ] Verify: metrics are updated on every request

---

#### TICKET-010: Add OpenTelemetry tracing

| Field | Value |
|---|---|
| **Owner** | DevOps Engineer |
| **Priority** | P3 (Low) |
| **Depends on** | TICKET-008 (structured logging) |
| **Effort** | 1-2 days |

**Problem**: Can't trace a single request through ingest → convert → chunk → embed → store.

**Definition of Done**:
- [ ] Add `opentelemetry-distro` and `opentelemetry-exporter-otlp` dependencies
- [ ] Instrument FastAPI with `OpenTelemetryMiddleware`
- [ ] Add manual spans for: `convert()`, `extract()`, `chunk_document()`, `embed_batch()`, `_collection.add()`, `LLMClient.generate()`
- [ ] Export traces to OTLP collector (or stdout for local dev)
- [ ] Verify: trace with all spans visible in Jaeger (or equivalent)
- [ ] Verify: `request_id` from HTTP header is propagated as trace ID

---

### Epic 4: Deployment & Configuration (Medium)

---

#### TICKET-011: Add `.env` configuration support

| Field | Value |
|---|---|
| **Owner** | Backend Engineer |
| **Priority** | P2 (Medium) |
| **Depends on** | Nothing |
| **Effort** | 1 day |

**Problem**: All paths and settings are hardcoded. Deploying to different environments requires code changes.

**Definition of Done**:
- [ ] Add `python-dotenv` dependency
- [ ] Create `.env.example` with all configurable values:
  - `API_HOST`, `API_PORT`
  - `CHROMA_PERSIST_DIR`
  - `PROFILES_PATH`
  - `OUTPUT_DIR`
  - `EVALUATOR_SCRIPT`
  - `EMBEDDING_MODEL`
  - `CHUNK_MAX_TOKENS`
  - `CACHE_CAPACITY`, `CACHE_TTL`
  - `REDIS_URL` (TICKET-001)
  - `API_KEY` (TICKET-002)
  - `LOG_LEVEL`, `LOG_FORMAT`
  - `OLLAMA_BASE_URL`, `LMSTUDIO_BASE_URL`
- [ ] Update `RAGPipeline.__init__()` to read from env with sensible defaults
- [ ] Update `LLMClient` to accept base URL from parameter, not hardcoded constant
- [ ] Add config validation at startup (fail fast on invalid config)
- [ ] Update `docker-compose.yml` to pass env variables
- [ ] Verify: default config works without `.env` file
- [ ] Verify: setting env var overrides default

---

#### TICKET-012: Optimize Docker image size

| Field | Value |
|---|---|
| **Owner** | DevOps Engineer |
| **Priority** | P2 (Medium) |
| **Depends on** | Nothing |
| **Effort** | 1 day |

**Problem**: Docker image is ~2GB+. Slow deploys, expensive storage.

**Definition of Done**:
- [ ] Audit `requirements.txt` — split into `requirements-core.txt` and `requirements-optional.txt`
- [ ] Dockerfile: only install `requirements-core.txt` in the final image
- [ ] Dockerfile: install optional deps only if `--build-arg INCLUDE_EXTRAS=true`
- [ ] Use `--no-cache-dir` and `--no-deps` where possible
- [ ] Consider `slim-buster` or `alpine` base image (if Chroma/Docling support it)
- [ ] Verify: core image size < 800MB
- [ ] Verify: image with all extras < 1.5GB
- [ ] Verify: `docker compose build` completes in < 5 minutes

---

### Epic 5: Technical Debt (Low)

---

#### TICKET-013: Fix `list_models()` tag stripping for long model names

| Field | Value |
|---|---|
| **Owner** | Backend Engineer |
| **Priority** | P3 (Low) |
| **Depends on** | Nothing |
| **Effort** | 0.5 day |

**Problem**: `split(":")[0]` on `"hf.co/.../DeepSeek-R1-Distill-Qwen-7B-GGUF:Q4_K_M"` strips the quant tag.

**Definition of Done**:
- [ ] Change `list_models()` to only strip the `:latest` suffix (standard convention)
- [ ] Use `m["name"].removesuffix(":latest")` instead of `split(":")[0]`
- [ ] Verify: `"mistral:latest"` → `"mistral"` (correct)
- [ ] Verify: `"hf.co/.../model:Q4_K_M"` → `"hf.co/.../model:Q4_K_M"` (preserved)

---

#### TICKET-014: Add `Content-Type` validation for ingest source parameter

| Field | Value |
|---|---|
| **Owner** | Backend Engineer |
| **Priority** | P3 (Low) |
| **Depends on** | Nothing |
| **Effort** | 0.5 day |

**Problem**: Ingest accepts any path/URL without validation. Garbage in produces confusing error messages.

**Definition of Done**:
- [ ] Add `validate_source()` function that checks:
  - File exists (for local paths)
  - URL is reachable (for URLs)
  - Extension is in supported list (`.pdf`, `.xlsx`, `.docx`, `.pptx`, `.csv`, `.html`, `.png`, `.jpg`)
- [ ] Return 400 with clear error message for invalid sources
- [ ] Add unit tests for validation function

---

## 7. Data Contracts (Current State)

### 7.1 Internal: Ingestion Pipeline Data Contract

```
Input:  str (file path or URL)
        + profile: str ("standard", "ocrmac", "auto", etc.)
        + deep: bool
        + skip_quality: bool

Output: IngestionResult
        ├── source: str
        ├── profile: str
        ├── conversion: ConversionOutput | None
        │   ├── document: DoclingDocument (Docling internal type)
        │   ├── source: str
        │   ├── profile: str
        │   ├── duration_seconds: float
        │   ├── page_count: int
        │   ├── timed_out: bool
        │   └── error: str | None
        ├── chunking: ChunkingResult | None
        │   ├── chunks: list[DocumentChunk]
        │   │   ├── text: str
        │   │   ├── contextualized_text: str
        │   │   ├── headings: list[str]
        │   │   ├── page: int | None
        │   │   ├── source: str
        │   │   └── token_count: int
        │   └── total_chunks: int
        ├── quality: QualityReport | None
        ├── vector_count: int
        ├── success: bool
        ├── error: str | None
        └── retry_chain: list[str]
```

**Contract stability**: Internal — can be refactored. No external consumers.

### 7.2 External: HTTP API Contract

Auto-generated at `http://localhost:8000/openapi.json`. Key endpoints:

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/health` | — | `{"status": "ok"}` |
| POST | `/ingest` | `{"source": str, "profile": str, "skip_quality": bool, "deep": bool}` | `{"task_id": str, "source": str, "status": "pending"}` |
| GET | `/ingest/{task_id}` | — | `{"task_id": str, "status": str, ...}` |
| POST | `/retrieve` | `{"query": str, "k": int, "format": str, "sources": [str], "page_range": [int, int], "min_score": float}` | `{"query": str, "results": [...], "context": str\|null}` |
| GET | `/retrieve/stream` | Query params: query, k, sources, format, min_score | SSE: `event: meta → event: chunk → event: done` |
| GET | `/documents` | — | `{"documents": [...], "total": int}` |
| DELETE | `/documents/{source}` | — | `{"success": bool, "chunks_removed": int}` |
| GET | `/status` | — | `{"document_count": int, "sources": [...], ...}` |

**Contract stability**: Relatively stable. The `format` parameter (`json`/`llm`) and the response structure are unlikely to break backward compatibly. Adding auth (TICKET-002) will add `X-API-Key` header requirement but won't change response bodies.

### 7.3 External: LLM Provider Contract

```
Ollama:
  POST http://localhost:11434/api/generate
  {"model": str, "prompt": str, "system": str, "stream": false, "options": {"temperature": float, "num_predict": int}}
  → {"response": str, "eval_count": int, "eval_duration": int}

LM Studio (OpenAI-compatible):
  POST http://localhost:1234/v1/chat/completions
  {"model": str, "messages": [...], "temperature": float, "max_tokens": int, "stream": false}
  → {"choices": [{"message": {"content": str}}], "usage": {"completion_tokens": int}}
```

### 7.4 Chroma Store Schema

```
Collection: "documents"
Embedding function: cosine similarity (HNSW)
Dimension: 384

Document metadata:
  ├── source: str          (e.g., "data/sample/report.pdf")
  ├── chunk_index: int     (0, 1, 2...)
  ├── page: int            (page number)
  ├── token_count: int
  └── headings: str        (e.g., "Chapter 3 > Section 2 > Subsection A")

Document content:
  contextualized_text (the chunk text with heading context)
```

---

## 8. Non-Functional Requirements Assessment

### 8.1 Performance

| Concern | Current | Target | Gap |
|---|---|---|---|
| PDF ingestion (born-digital) | ~2 pgs/sec (M3 Pro) | ~5 pgs/sec | Acceptable for MVP — optimization deferred |
| PDF ingestion (scanned, OCR) | ~1 pg/sec (ocrmac, M3 Pro) | ~2 pgs/sec | Hard to improve without GPU OCR |
| Embedding throughput | ~500 chunks/sec (CPU) | ~1000 chunks/sec | Batch GPU embedding would help |
| Retrieval latency (cache hit) | ~1ms | <10ms | ✅ Already meeting |
| Retrieval latency (cache miss) | ~100-200ms | <500ms | ✅ Already meeting |
| LLM generation (llama3.2:3B) | ~20-40s for 512 tokens | <10s | Hard without GPU — depends on Ollama |
| API response time (health) | <5ms | <10ms | ✅ Already meeting |

### 8.2 Security

| Concern | Current | Target | Gap |
|---|---|---|---|
| Authentication | None | API key required | ❌ **Critical gap** |
| Authorization | None | Per-key document access | ❌ Not yet scoped |
| CORS | `allow_origins=["*"]` | Configurable origin list | ❌ Needs env var |
| Input validation | Minimal (Pydantic for API, none for file paths) | Full validation | ❌ Gaps exist |
| Secret management | None | `.env` file + gitignored | ❌ Needs implementation |
| Rate limiting | In-memory, per-process | Redis-backed, multi-instance | ❌ **Critical gap** |

### 8.3 Availability

| Concern | Current | Target | Gap |
|---|---|---|---|
| Single instance uptime | Good | 99.9% | Acceptable |
| Multi-instance failover | Not supported | Auto-failover | ❌ Requires Redis + load balancer |
| Data persistence | SQLite (Chroma) | SQLite (Chroma) + Redis | ✅ Chroma persists |
| State persistence | In-memory only | Redis-backed | ❌ **Critical gap** |

### 8.4 Data Licensing

The project currently ingests:
- `data/sample/` — test PDFs that appear to be publicly available educational content
- User-provided documents

No formal attribution tracking. If this pipeline ingests OSM, Overture Maps, or other licensed geospatial data in the future, attribution strings must be embedded in metadata and exposed in retrieve responses.

**Current status**: No licensing compliance infrastructure. Not blocking for current use case.

---

## 9. Risk Profile by Layer

```
Layer              Risk Level   Key Risks
─────────────────────────────────────────────────
Ingestion          🟡 Medium    No input validation, oversized deps
Storage            🟢 Low       Chroma is stable, SQLite persistence
API                🔴 High      No auth, in-memory state, single-process rate
Caching            🟡 Medium    In-memory, lost on restart
Rate Limiter       🔴 High      Single-process, bypassable behind LB
LLM Integration    🟢 Low       Provider abstraction is clean, retry missing
Evaluation         🟢 Low       Standalone, no production dependencies
Tests              🟡 Medium    No integration tests, shared state
CI/CD              🟢 Low       Working, but no security scanning
Docker             🟡 Medium    Oversized image
```

---

## 10. Handoff Notes for Specialist Agents

### For the Backend Engineer

Start with **Epic 1 (TICKET-001, TICKET-002, TICKET-003)** — these are the critical scaling blockers. The Redis refactoring is the foundation everything else depends on. After Epic 1, move to **Epic 2**, specifically **TICKET-004** (dependency injection) and **TICKET-006** (concurrency control).

Key files to know:
- `src/api/server.py` — all routes, middleware, global state
- `src/api/rate_limiter.py` — needs Redis backend
- `src/api/cache.py` — needs Redis backend  
- `src/retrieval/pipeline.py` — core orchestrator, has `_PIPELINE` global
- `src/ingestion/detector.py` — `_is_macos()` check may need Linux fallback for Docker

### For the Data Engineer

Start with **TICKET-005** (integration tests). The current trust model is "the pipeline works because we ran it locally." You need to prove it works with automated tests that use real documents. Also review `src/ingestion/quality.py` — the `_basic_fallback()` quality check is very basic and should be enhanced for production.

### For the QA Engineer

**TICKET-005** is your primary ticket. Create `tests/test_integration.py` with the scenarios listed above. Also add property-based tests for the chunker and embedder:
- All chunks have unique IDs
- All chunks have non-empty text
- Embedding dimension is always 384
- Chroma distance is always 0.0-1.0

### For the DevOps Engineer

Start with **TICKET-012** (Docker image size) and **TICKET-011** (`.env` config). These are quick wins that improve deployability immediately. Then **TICKET-009** (metrics) and **TICKET-010** (tracing) — you can't operate what you can't observe.

### For the Frontend/3D Engineer

The API contract is stable at `/retrieve` and `/retrieve/stream`. You can consume these endpoints today. Watch for:
- **TICKET-002** adding `X-API-Key` header requirement (non-breaking, just add header)
- The SSE stream at `/retrieve/stream?query=...&format=llm` is the best fit for real-time rendering

### For the GIS / Geospatial Engineer

Not yet applicable — this project is focused on financial documents, not geospatial data. If geospatial documents (GeoPDF, vector tiles metadata) are introduced later, the extractor will need to handle spatial references and coordinate systems.

---

*End of report. This document is intended for agent handoff and should be reviewed by the Tech Lead before any implementation begins.*
