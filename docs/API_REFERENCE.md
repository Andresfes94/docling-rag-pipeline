# Docling RAG Pipeline — API Reference

**Version:** 0.2.0 — **Base URL:** `http://<host>:<port>` (default `http://0.0.0.0:8000`)

---

## Configuration

All env vars accept an optional `RAG_` prefix (e.g. `RAG_API_HOST`). Direct vars take precedence.

| Variable | Default | Description |
|---|---|---|
| `API_HOST` | `0.0.0.0` | Bind address |
| `API_PORT` | `8000` | Port |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `CHROMA_PERSIST_DIR` | `data/chroma` | ChromaDB persistence directory |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `text` | `"text"` or `"json"` |
| `CACHE_CAPACITY` | `1024` | Max retrieval cache entries |
| `CACHE_TTL` | `300` | Cache TTL in seconds |
| `API_KEY` / `API_KEYS` | `""` (auth disabled) | Single or comma-separated API keys |
| `REDIS_URL` | _(none)_ | Enables Redis-backed rate-limit + cache + task store |

---

## Auth

- **Header:** `X-API-Key: <your-key>`
- **Public paths:** `/health`, `/metrics` (no key required)
- **Disabled** when both `API_KEY` and `API_KEYS` are empty/absent
- Reload keys without restart: `POST /auth/reload`

```bash
# With auth disabled:
curl http://localhost:8000/health

# With auth enabled:
curl -H "X-API-Key: sk-abc123" http://localhost:8000/status
```

---

## Rate Limiting

| Path prefix | Rate | Burst |
|---|---|---|
| `/retrieve` | 30 req/s | 60 |
| `/ingest` | 2 req/s | 4 |
| `/documents` | 60 req/s | 120 |
| Everything else | 60 req/s | 120 |

Exceeded: **429** `{"detail": "Rate limit exceeded"}` with `Retry-After` header.

---

## Endpoints

### `GET /health`

Public health check.

```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

---

### `POST /ingest`

Ingest a document asynchronously. Returns immediately with a `task_id` — poll `GET /ingest/{task_id}` for completion.

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "/path/to/document.pdf", "profile": "standard"}'
# → {"task_id": "abc123", "source": "...", "status": "pending", ...}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `source` | `str` | **required** | Local file path or URL. Supported: `.pdf`, `.xlsx`, `.docx`, `.pptx`, `.csv`, `.html`, `.png`, `.jpg`, `.jpeg` |
| `profile` | `str` | `"standard"` | Pipeline profile: `standard`, `ocrmac`, `ocr_easyocr`, `vlm_granite`, `fast`, `large_document`, `auto` |
| `skip_quality` | `bool` | `false` | Skip Docling quality evaluation gate |
| `deep` | `bool` | `false` | Enable Camelot table fallback + Unstructured formula patching |

**Task lifecycle:** `pending` → `running` → `done` / `failed`

```bash
# Poll task status:
curl http://localhost:8000/ingest/abc123
# → {"task_id": "abc123", "source": "...", "status": "done",
#     "pages": 42, "duration_seconds": 3.2, "chunks": 156}
```

**Re-ingesting existing data (cleaning retroactively):** POST the same `source` path again — the pipeline removes old chunks for that source before storing new ones.

---

### `POST /retrieve`

Semantic search over ingested chunks. Supports reranking, hybrid search, source/page filters, and LLM-formatted output.

```bash
# Basic search:
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "option pricing greeks", "k": 5}'
```

```bash
# LLM-ready context:
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "what is backtesting", "k": 3, "format": "llm"}'
# → {"query": "...", "total_results": 3, "format": "llm",
#     "context": "[1] Source: doc.pdf | Page: 12 | Section: Ch 3 > Validation\n{text}\n\n---\n\n[2] ...",
#     "results": [...]}
```

```bash
# With source filter, score threshold, and hybrid search:
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "volatility smile",
    "k": 10,
    "sources": ["options_guide.pdf"],
    "page_range": [1, 50],
    "min_score": 0.4,
    "rerank": true,
    "min_rerank_score": 0.1,
    "use_hybrid": true
  }'
```

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | **required** | Natural language search query |
| `k` | `int` | `5` | Number of results (1–100) |
| `sources` | `list[str]` | `null` | Filter by source filenames |
| `page_range` | `list[int]` | `null` | Filter: `[min_page, max_page]` |
| `format` | `str` | `"json"` | `"json"` or `"llm"` (assembled context string) |
| `min_score` | `float` | `null` | Min cosine similarity (0–1) |
| `rerank` | `bool` | `true` | Enable cross-encoder reranking |
| `min_rerank_score` | `float` | `null` | Min reranker score (0–1) |
| `use_hybrid` | `bool` | `false` | BM25 + vector fusion via RRF |

**Response:**

| Field | Type | Description |
|---|---|---|
| `query` | `str` | Echoed query |
| `total_results` | `int` | Result count (may be < `k` after filtering) |
| `format` | `str` | Echoed format |
| `context` | `str` | LLM context string when `format="llm"` |
| `results` | `list` | `[{text, score, source, page, headings}, ...]` |

**Caching:** LRU cache with 5-minute TTL. Keyed by `SHA256(query|k|sources|model|format)`. Invalidated per-source on re-ingest or delete.

---

### `GET /retrieve/stream`

Server-Sent Events (SSE) streaming of results — progressive delivery for real-time LLM consumption.

```bash
curl -N "http://localhost:8000/retrieve/stream?query=option+pricing&k=3&format=llm&use_hybrid=true"
```

Events:
```
event: meta
data: {"total": 3, "format": "llm"}

event: chunk
data: [1] Source: doc.pdf | Page: 12 | Section: Ch 3 > Valuation
...chunk text...

event: done
data: {}
```

| Query param | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | **required** | Search query |
| `k` | `int` | `5` | Results (1–100) |
| `sources` | `str` | `null` | Comma-separated: `"doc1.pdf,doc2.pdf"` |
| `format` | `str` | `"json"` | `"json"` or `"llm"` |
| `min_score` | `float` | `null` | Min similarity (0–1) |
| `rerank` | `bool` | `true` | Enable reranking |
| `min_rerank_score` | `float` | `null` | Min reranker score |
| `use_hybrid` | `bool` | `false` | Enable BM25 hybrid |

---

### `GET /documents`

List all ingested documents.

```bash
curl http://localhost:8000/documents
# → {"documents": [{"source": "guide.pdf", "chunk_count": 156,
#                    "pages": [1,2,3], "profiles_used": ["standard"]}],
#     "total": 1}
```

---

### `GET /documents/{source}`

Get details for a specific document.

```bash
curl http://localhost:8000/documents/guide.pdf
# → {"source": "guide.pdf", "chunk_count": 156, "pages": [1,2,3], "profiles_used": ["standard"]}
```

---

### `DELETE /documents/{source}`

Delete a document and all its chunks.

```bash
curl -X DELETE http://localhost:8000/documents/guide.pdf
# → {"success": true, "source": "guide.pdf", "chunks_removed": 156}
```

BM25 index is rebuilt automatically after deletion (and after successful ingestion).

---

### `GET /status`

Pipeline overview.

```bash
curl http://localhost:8000/status
# → {"document_count": 156, "sources": ["guide.pdf"],
#     "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
#     "chunk_count_by_source": {"guide.pdf": 156},
#     "cache_entries": 0}
```

---

### `GET /metrics`

Prometheus metrics (public, no auth).

```bash
curl http://localhost:8000/metrics
```

Counters: `ingest_documents_total{profile,status}`, `retrieve_requests_total{cache_hit}`, `retrieve_chunks_total`, `rate_limit_hits{endpoint}`, `cache_hits`, `cache_misses`.

---

### `POST /auth/reload`

Reload API keys from environment without restart.

```bash
curl -X POST http://localhost:8000/auth/reload
# → {"status": "ok", "keys_loaded": 3}
```

Hidden from OpenAPI schema (`include_in_schema=False`).

---

## Search Pipeline (Conceptual)

```
Query ──► ANN retrieval (k×3) ──► Cross-encoder rerank ──► Top k
                    │
          ┌─────────┘
          ▼
      BM25 retrieval (k×3)
          │
          └─────────► RRF fusion ──► (rerank) ──► Top k
```

- **ANN only** → `rerank=false, use_hybrid=false`
- **ANN + reranker** → `rerank=true, use_hybrid=false` (default)
- **Hybrid (BM25 + ANN)** → `use_hybrid=true, rerank=false`
- **Hybrid + rerank** → `use_hybrid=true, rerank=true`

---

## Error Responses

| Status | Meaning |
|---|---|
| 400 | Invalid input (source not found, unsupported extension) |
| 401 | Missing or invalid API key |
| 404 | Task or document not found |
| 429 | Rate limit exceeded |
| 500 | Internal server error (includes `request_id` in body) |

All error responses: `{"detail": "...", "request_id": "abc123"}`

---

## Response Headers

Every response includes:
- `X-Request-ID` — 8-char UUID for tracing
- `X-Response-Time-Ms` — wall-clock duration in milliseconds

---

## OpenAPI Schema

Visit `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/openapi.json` when the server is running.
