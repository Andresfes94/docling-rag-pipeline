# Backend Engineer Report — Docling RAG Pipeline

**Author**: Backend Engineer
**Date**: 2026-07-19
**Status**: ✅ All Epic 1 (P0) and Epic 2 (P1/P2) tickets complete

---

## 1. Executed Tasks

### TICKET-002: API Key Authentication Middleware (P0, Critical)
**Files**: `src/api/auth.py` (new), `src/api/server.py` (modified), `tests/test_api.py`

| DoD | Status |
|---|---|
| Create `src/api/auth.py` with API key middleware | ✅ |
| Support `API_KEY` env var for single key | ✅ |
| Support `API_KEYS` env var for multi-key rotation | ✅ |
| `X-API-Key` header check on all endpoints except `/health` and `/metrics` | ✅ |
| Auth check applied before rate limiter | ✅ |
| Update CORS to `CORS_ORIGINS` env var instead of `["*"]` | ✅ |

**Design**:
- `AuthMiddleware` reads `API_KEY` (single) and/or `API_KEYS` (comma-separated, rotation-friendly)
- When neither env var is set, auth is transparently disabled (local-dev-friendly)
- Public paths: `/health`, `/metrics` — always accessible
- Returns `401` with `Missing X-API-Key header` or `Invalid API key` messages

**Tests**: `/health` and `/metrics` accessible without key verified in test suite.

### TICKET-007: LLM Client Retry with Exponential Backoff (P2, Medium)
**Files**: `src/llm/client.py` (modified), `tests/test_llm_client.py` (new, 10 tests)

| DoD | Status |
|---|---|
| 3 retries with exponential backoff (1s, 2s, 4s) | ✅ |
| Retry on connection errors and HTTP 5xx | ✅ |
| Don't retry on HTTP 4xx or invalid JSON | ✅ |
| Log each retry attempt | ✅ |
| `_generate_with_retry()` method | ✅ |

**Retry-eligible errors**:
- `urllib.error.HTTPError` with status >= 500 (server errors)
- `urllib.error.URLError` (DNS failure, connection refused)
- `TimeoutError`, `OSError` (connection reset, timeout)

**Non-retryable**: HTTP 4xx (client errors), `json.JSONDecodeError` (bad response shape)

**Tests**: 10 tests covering all retry paths, both Ollama and OpenAI-compatible providers.

### TICKET-006: Concurrency Control for Chroma Writes (P1, High)
**Files**: `src/storage/vector_store.py` (modified)

| DoD | Status |
|---|---|
| `threading.Lock` in `add_document()` | ✅ |
| Wrap embed + add sequence | ✅ |
| `try/finally` guard via context manager (`with self._lock`) | ✅ |
| `enable_async()` for `asyncio.Lock` | ✅ |
| `use_async_lock` parameter for async API path | ✅ |

The existing `add_document()` already had the `@profile_lock` or similar — now it has a `threading.Lock` guarding the full delete-then-embed-then-insert sequence. The `asyncio.Lock` variant is available via `enable_async()` for the future async API path.

### TICKET-004: Dependency Injection Refactor (P1, High)
**Files**: `src/api/server.py` (rewritten), `tests/test_api.py` (updated)

| DoD | Status |
|---|---|
| Remove `_pipeline`, `_cache`, `_tasks` module globals | ✅ |
| Initialize in `lifespan`, store on `app.state` | ✅ |
| `get_pipeline()`, `get_cache()`, `get_tasks()` as `Depends()` | ✅ |
| Background `_run_ingest` receives pipeline/cache/tasks as arguments | ✅ |
| Tests use `app.dependency_overrides` for isolation | ✅ |

**Before**:
```python
_pipeline = None
def get_pipeline():
    global _pipeline
    ...
```

**After**:
```python
# In lifespan:
app.state.pipeline = RAGPipeline()
app.state.cache = RetrievalCache(ttl=300)

# As FastAPI dependency:
def get_pipeline(request: Request) -> RAGPipeline:
    return request.app.state.pipeline
```

**Pattern**: `app.state` stores long-lived singletons; `Depends()` injects them into routes;
`dependency_overrides` in tests replaces them with isolated instances.

### TICKET-001: Redis-Backed Persistent State Store (P0, Critical)
### TICKET-003: Redis-Backed Rate Limiter (P0, Critical, Depends on TICKET-001)
**Files**: `src/api/state.py` (new), `src/api/cache.py` (rewritten), `src/api/rate_limiter.py` (rewritten)

| Store | Redis Implementation | Fallback |
|---|---|---|
| **Tasks** (`TaskStore`) | `HSET tasks:{id}` + `EXPIRE 3600` | In-memory dict with thread lock |
| **Cache** (`CacheStore`) | `SETEX cache:{key} 300` | In-memory LRU with TTL |
| **Rate limiter** (`RateLimitStore`) | `INCR rate:{key}:{window}` + `EXPIRE` | In-memory token bucket |

**Configuration**:
- Set `REDIS_URL=redis://localhost:6379/0` to enable Redis
- Default (no env var): transparent in-memory fallback, no dependency required

**Graceful degradation**: Redis unavailable → falls back to in-memory. No crash on Redis restart (rate limit counters reset, which is acceptable).

---

## 2. Test Matrix

| Suite | Tests | Duration | Status |
|---|---|---|---|
| Unit tests (excluding integration) | 45 | 15.5s | ✅ All pass |
| Integration tests | 9 | 49s | ✅ All pass |
| **Total** | **54** | **~65s** | ✅ |

---

## 3. Files Changed/Created

| File | Action | Purpose |
|---|---|---|
| `src/api/auth.py` | **CREATE** | API key auth middleware |
| `src/api/state.py` | **CREATE** | Redis + in-memory state stores |
| `src/api/rate_limiter.py` | **REWRITE** | Redis-aware rate limiter |
| `src/api/cache.py` | **REWRITE** | Redis-backed retrieval cache |
| `src/api/server.py` | **REWRITE** | DI refactor, auth, CORS env var |
| `src/llm/client.py` | **MODIFY** | Retry with exponential backoff |
| `src/storage/vector_store.py` | **MODIFY** | Concurrency lock |
| `tests/test_api.py` | **REWRITE** | DI-compatible test fixtures |
| `tests/test_llm_client.py` | **CREATE** | 10 retry tests |
| `backend-engineer-report.md` | **CREATE** | This report |

---

## 4. Remaining Architecture Gaps

1. **`detector.py` Linux fallback**: `_is_macos()` check in `detector.py` means OCR defaults to `ocrmac` which doesn't exist on Linux. Docker deployments need `ocr_easyocr` as default. (Low priority while running on macOS)

2. **Multi-process batch lock**: TICKET-006 only added `threading.Lock` (in-process). Batch mode with `ProcessPoolExecutor` in `batch.py` needs `portalocker` or `fcntl` for cross-process Chroma safety. (Medium priority)

3. **Asyncio.Lock test**: The `enable_async()` path is available but untested. Full async API routes would need this wired in. (Low priority until async routes exist)

4. **`redis-py` not in Dockerfile**: Added to `pyproject.toml` dependencies. Next Docker build will include it.

5. **API key rotation webhook**: `AuthMiddleware` currently reloads keys at import time. A `POST /auth/reload` endpoint or periodic env re-read would allow key rotation without restart. (Nice-to-have)
