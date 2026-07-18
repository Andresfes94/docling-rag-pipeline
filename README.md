# Docling RAG Pipeline

A modular, production-ready **RAG ingestion pipeline** built with [Docling](https://github.com/docling-project/docling) for intelligent document extraction, chunking, embedding, and retrieval — with a full **LLM evaluation framework** to measure and validate RAG quality.

> Built as an interview project for **Senior Integration Engineer – AI Platform** at octonomy. Demonstrates end-to-end data engineering from unstructured documents to AI-ready vector search with measurable quality metrics.

---

## Features

| Capability | Implementation |
|---|---|
| **Document parsing** | PDF, DOCX, PPTX, XLSX, CSV, HTML, images via Docling (standard & VLM pipelines) |
| **Configurable profiles** | YAML-defined pipeline configs — add OCR engines without touching code |
| **Quality gate** | Automatic `convert → evaluate → refine` loop with heuristic checks |
| **Hybrid chunking** | Heading hierarchy + token count via `HybridChunker` |
| **Local embeddings** | `sentence-transformers/all-MiniLM-L6-v2` (384-dim, fully local) |
| **Vector storage** | Chroma DB (persistent, cosine similarity, metadata filtering) |
| **REST API** | FastAPI with rate limiting, caching, SSE streaming, async ingest, document CRUD, LLM-friendly context assembly |
| **CLI** | `python scripts/run.py ingest` / `retrieve` / `detect` / `ingest-batch` / `list-profiles` |
| **LLM Integration** | RAG question-answering with Ollama/LM Studio — interactive chat or batch evaluation |
| **RAG Evaluation** | 20 curated test questions across 4 categories (factual, synthesis, OOC rejection, attribution) with accuracy, latency, and citation metrics |
| **Extraction Viewer** | `streamlit run scripts/viewer.py` — browse pages with extracted text side-by-side |
| **Library Comparison** | `streamlit run scripts/comparison_viewer.py` — compare Docling, pdfplumber, Camelot, Unstructured output |
| **Deep Enrichment** | Optional Camelot + Unstructured fallback for table/table pages via `--deep` flag |
| **Docker** | Multi-stage build + `docker-compose.yml` |
| **CI/CD** | GitHub Actions: lint → typecheck → test → build |

---

## Quick Start

### Prerequisites

This project uses a **conda environment** (`developer`) with Python 3.11.5 and all dependencies pre-installed.

```bash
# Activate the environment
conda activate developer

# Or run individual commands without activating:
conda run -n developer python scripts/run.py --help
```

### Document Ingestion & Retrieval

```bash
# Detect document type (pre-scan for classification)
conda run -n developer python scripts/run.py detect mydocument.pdf

# Ingest a document with auto-detection (recommended)
conda run -n developer python scripts/run.py ingest mydocument.pdf --profile auto

# Ingest from URL
conda run -n developer python scripts/run.py ingest https://arxiv.org/pdf/2408.09869 --profile standard

# Ingest with deep enrichment (Camelot + Unstructured fallback)
conda run -n developer python scripts/run.py ingest mydocument.pdf --profile standard --deep

# Batch process multiple documents in parallel
conda run -n developer python scripts/run.py ingest-batch doc1.pdf doc2.pdf doc3.pdf --workers 7

# Search ingested documents
conda run -n developer python scripts/run.py retrieve "option pricing greeks" --k 5

# List available pipeline profiles
conda run -n developer python scripts/run.py list-profiles
```

### Interactive Chat (RAG + LLM)

Ask questions against your ingested documents using a local LLM (Ollama):

```bash
# Interactive chat with default model (llama3.2)
conda run -n developer python scripts/chat.py

# Chat with a specific model
conda run -n developer python scripts/chat.py --model deepseek-r1:8b

# Chat with LM Studio provider instead of Ollama
conda run -n developer python scripts/chat.py --provider lmstudio --model local-model
```

The chat script:
1. Takes your question
2. Retrieves the top-k relevant chunks from Chroma
3. Assembles them into an LLM context block
4. Sends to the LLM with a system prompt instructing it to answer from context only
5. Returns the answer with source citations

### RAG Evaluation

Measure how well your RAG pipeline performs across 20 curated test questions:

```bash
# Run full evaluation (requires Ollama running with llama3.2)
conda run -n developer python scripts/evaluate_rag.py --model llama3.2 --k 5

# Save detailed results to JSON
conda run -n developer python scripts/evaluate_rag.py --model llama3.2 --k 5 --output eval_results.json

# Evaluate with a different model
conda run -n developer python scripts/evaluate_rag.py --model deepseek-r1:8b --k 5

# Quiet mode (suppress per-question output, only show summary)
conda run -n developer python scripts/evaluate_rag.py --model llama3.2 --k 5 --quiet
```

**What gets measured:**

| Metric | What it tells you |
|---|---|
| `overall_accuracy` | % of questions answered correctly |
| `factual_accuracy` | Can the RAG pipeline recall specific facts from documents? |
| `synthesis_accuracy` | Can it combine information across multiple chunks? |
| `out_of_context_rejection_rate` | Does it correctly refuse questions not in the documents? |
| `attribution_accuracy` | Does it cite sources when asked about specific document content? |
| `avg_keyword_coverage` | What fraction of expected keywords appear in answers? |
| `citation_rate` | How often does the LLM cite source/page in its answers? |
| `avg_latency_s` | End-to-end time per question (retrieval + LLM generation) |
| `avg_tokens_per_response` | LLM token consumption per answer |

### API Server

```bash
# Start the FastAPI server
conda run -n developer uvicorn src.api.server:app --reload --port 8000

# OpenAPI docs: http://localhost:8000/docs
```

#### `/health` — Health check
```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

#### `/ingest` — Async document ingestion
```bash
# Submit an ingest task (returns immediately with task_id)
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "report.pdf", "profile": "standard", "deep": true}'
# → {"task_id": "abc123", "source": "report.pdf", "status": "pending", ...}

# Poll task status
curl http://localhost:8000/ingest/abc123
# → {"task_id": "abc123", "status": "done", "pages": 30, "chunks": 25, ...}
```

#### `/retrieve` — Semantic search
```bash
# Standard JSON response
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "option pricing greeks", "k": 5}'

# LLM-friendly context assembly (ready to inject into a prompt)
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "backtesting platforms", "k": 3, "format": "llm"}'
# → {"context": "[1] Source: ... | Page: 53 | Section: Summary\n...\n\n---\n\n[2] ...", ...}

# With filters (source, page range, minimum score)
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "risk management", "sources": ["quant.pdf"], "page_range": [1, 100], "min_score": 0.5}'
```

#### `/retrieve/stream` — SSE streaming (real-time LLM consumption)
```bash
curl -N http://localhost:8000/retrieve/stream?query=greeks&k=3&format=llm
# → event: meta
#   data: {"total": 3, "format": "llm"}
# → event: chunk
#   data: [1] Source: ... | Page: 210 | Section: Greeks\n| option | time to expiry | ...
# → event: done
#   data: {}
```

#### `/documents` — Document management
```bash
# List all ingested documents
curl http://localhost:8000/documents

# Get document details (chunk count, pages, profiles used)
curl http://localhost:8000/documents/report.pdf

# Delete a document (removes all chunks from Chroma)
curl -X DELETE http://localhost:8000/documents/report.pdf
```

#### `/status` — Pipeline status
```bash
curl http://localhost:8000/status
# → {"document_count": 2188, "sources": [...], "chunk_count_by_source": {...}, "cache_entries": 3}
```

### LLM Integration Example

```python
import httpx

# 1. Retrieve context formatted for an LLM
resp = httpx.post("http://localhost:8000/retrieve", json={
    "query": "what is the black-scholes model",
    "k": 5,
    "format": "llm",
})
data = resp.json()
context = data["context"]

# 2. Build prompt with retrieved context
prompt = f"""You are a financial analyst. Answer the question using ONLY the context below.

Context:
{context}

Question: What is the Black-Scholes model and how is it used for option pricing?"""

# 3. Send to any LLM (local or remote)
# response = openai.chat.completions.create(model="...", messages=[{"role": "user", "content": prompt}])
```

### Docker

```bash
docker compose build
docker compose up
```

---

## Use Cases

### 1. Document Q&A with RAG

Ingest financial/technical documents, then ask questions with automatic context retrieval:

```bash
# Ingest your documents
conda run -n developer python scripts/run.py ingest report.pdf --profile auto

# Chat interactively
conda run -n developer python scripts/chat.py

# Or use the API for programmatic access
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the Sharpe ratio?", "k": 5, "format": "llm"}'
```

### 2. Quality Validation Pipeline

Before deploying a new document corpus, run the evaluation suite to catch regressions:

```bash
# Run the full 20-question evaluation
conda run -n developer python scripts/evaluate_rag.py --model llama3.2 --k 5 --output eval_results.json

# Check accuracy threshold (script exits with code 1 if accuracy < 50%)
echo $?
```

### 3. Multi-Library Extraction Comparison

Compare how different libraries extract the same PDF page:

```bash
conda run -n developer streamlit run scripts/comparison_viewer.py
```

Useful for:
- Debugging extraction quality on specific pages
- Choosing the right library for your document types
- Demonstrating the value of hybrid enrichment

### 4. Batch Document Processing

Process large document collections in parallel:

```bash
# Process all PDFs in a directory with 7 workers
conda run -n developer python scripts/run.py ingest-batch data/sample/*.pdf --workers 7

# Each worker runs in its own process with isolated conversion
# Results are staged to disk, then batch-imported to Chroma
```

### 5. CI/CD Quality Gate

The quality evaluator can be used in CI to reject poor conversions:

```bash
# Evaluate a conversion
conda run -n developer python scripts/docling-evaluate.py data/output/document.json \
  --markdown data/output/document.md

# Exit code indicates pass/warn/fail — enforce in CI pipeline
```

---

## Pipeline Profiles

Configuration-driven via `profiles.yaml` — no code changes needed.

| Profile | Best for |
|---|---|
| `standard` | Born-digital PDFs, fast, no GPU |
| `ocr_easyocr` | Scanned PDFs with EasyOCR |
| `ocr_tesseract` | Tesseract OCR (system dep) |
| `ocrmac` | macOS native Vision OCR |
| `ocr_rapid` | RapidOCR (lightweight) |
| `vlm_granite` | Complex layouts, handwriting (GPU) |
| `vlm_smoldocling` | Lighter VLM model |
| `vlm_remote` | Remote API (vLLM, LM Studio, Ollama) |

To add a new profile, just add an entry to `profiles.yaml`:

```yaml
  ocr_surya:
    description: "Surya OCR engine"
    pipeline: standard
    options:
      do_ocr: true
      ocr_engine: surya
      do_table_structure: true
```

---

## Architecture

```
Source Document (PDF/URL)
        │
        ▼
profiles.yaml ──► loader.py ──► extractor.py ──► chunker.py ──► quality.py
                  (Docling)    (pdfplumber       (Hybrid        (evaluate.py)
                                Camelot           Chunker)
                                Unstructured  ── enrichment
                                deep mode)
                                               │
                        embedder.py ◄── vector_store.py ◄── pipeline.py
                        (sentence-     (Chroma DB)     (orchestrator +
                         transformers)                  auto-retry)
                                               │
                        api/server.py (FastAPI) ◄──────────┘
                            /ingest (async)    /retrieve     /status
                            /retrieve/stream   /documents    /ingest/{id}
                                               │
                        ┌──────────────────────┴──────────────────────┐
                        │  LLM Integration Layer                      │
                        │  src/llm/client.py  ← Ollama / LM Studio    │
                        │  src/llm/rag.py     ← RAG Q&A pipeline      │
                        │  scripts/chat.py    ← Interactive chat      │
                        │  scripts/evaluate_rag.py ← 20-question eval │
                        └─────────────────────────────────────────────┘
```

### API Features

| Feature | Implementation |
|---|---|
| **Rate limiting** | Token bucket per IP per endpoint (retrieve=30/s, ingest=2/s) |
| **Response caching** | LRU with 5-min TTL, keyed by (query, k, sources, format) |
| **Async ingestion** | `POST /ingest` returns task_id; poll with `GET /ingest/{task_id}` |
| **SSE streaming** | `/retrieve/stream` — Server-Sent Events for real-time LLM consumption |
| **LLM context assembly** | `format=llm` — chunks formatted as prompt-ready context strings |
| **Document CRUD** | List, inspect, and delete ingested documents |
| **Observability** | X-Request-ID and X-Response-Time-Ms on all responses |

### Data Flow

1. **Conversion**: Docling parses the document (standard OCR or VLM pipeline)
2. **Extraction**: `DoclingDocument.texts`, `.tables`, `.pictures`, `.body` tree traversal
3. **Deep Enrichment** (optional `--deep` flag): Camelot table fallback + Unstructured formula patching
4. **Quality Gate**: `docling-evaluate.py` checks text density, duplicates, replacement chars
5. **Chunking**: Heading hierarchy first, then token-count subdivision
6. **Embedding**: `sentence-transformers` → 384-dim vectors
7. **Storage**: Chroma with cosine similarity, source metadata, page numbers
8. **Retrieval**: FastAPI returns chunks ranked by semantic similarity (cached, rate-limited, streamable)
9. **LLM Answering** (optional): Retrieved chunks fed to local LLM for grounded question answering

### Quality Gate Output

```json
{
  "status": "pass",
  "metrics": {
    "page_count": 30,
    "chars_per_page": 2850.2,
    "tables": 5,
    "replacement_chars": 0
  }
}
```

---

## Project Structure

```
├── pyproject.toml              # Dependencies & tooling
├── profiles.yaml               # Pipeline profiles (YAML)
├── Dockerfile                  # Multi-stage build
├── docker-compose.yml          # API service
├── .github/workflows/ci.yml    # CI pipeline
│
├── src/
│   ├── ingestion/
│   │   ├── profiles.py         # YAML → pipeline options factory
│   │   ├── loader.py           # DocumentConverter wrapper
│   │   ├── extractor.py        # DoclingDocument traversal + table enrichment
│   │   ├── chunker.py          # HybridChunker wrapper
│   │   ├── quality.py          # Quality evaluation wrapper
│   │   └── detector.py         # Pre-scan classification (PyPDF2)
│   ├── embeddings/embedder.py  # SentenceTransformer embeddings
│   ├── storage/vector_store.py # Chroma persistent store
│   ├── retrieval/
│   │   ├── pipeline.py         # Full orchestration + auto-retry
│   │   └── batch.py            # Parallel batch processor
│   ├── llm/
│   │   ├── client.py           # LLM client (Ollama / LM Studio)
│   │   └── rag.py              # RAG question-answering pipeline
│   ├── evaluation/
│   │   ├── test_set.py         # 20 curated test questions
│   │   └── evaluator.py        # Evaluation framework + report
│   └── api/
│       ├── server.py           # FastAPI endpoints (rate-limited, cached, async ingest, SSE)
│       ├── models.py           # Pydantic schemas with examples
│       ├── rate_limiter.py     # Token bucket rate limiter middleware
│       └── cache.py            # LRU retrieval cache with TTL + source invalidation
│
├── scripts/
│   ├── run.py                  # CLI entrypoint (ingest, retrieve, detect, batch)
│   ├── docling-evaluate.py     # Quality evaluator
│   ├── viewer.py               # Streamlit extraction viewer
│   ├── comparison_viewer.py    # Streamlit library comparison
│   ├── chat.py                 # Interactive RAG chat with LLM
│   └── evaluate_rag.py         # RAG evaluation CLI
│
├── tests/                      # 26 pytest tests (14 API + 8 profiles + 5 quality)
└── skills/SKILL.md             # Agent skill for AI coding tools
```

---

## Testing

```bash
# Run all tests
conda run -n developer python -m pytest tests/ -v

# Run specific test file
conda run -n developer python -m pytest tests/test_api.py -v

# Run with coverage
conda run -n developer python -m pytest tests/ --cov=src
```

All 26 tests pass: profile loading (8), quality evaluation (5), API endpoints (14 async tests).

---

## Document Extraction Viewer

A Streamlit UI that lets you browse ingested documents and compare original pages with extracted text side-by-side.

```bash
conda run -n developer streamlit run scripts/viewer.py
```

**Features:**
- Dropdown to select any ingested document
- Side-by-side view: PDF page (left) vs extracted text items (right)
- Color-coded item labels (section_header, list_item, table, caption, etc.)
- Heading breadcrumbs showing the section hierarchy
- "Pick 5 random pages" or jump to a specific page
- Works with all document types (PDF, Excel, etc.)

**Traceability:** Every extracted item shows its source file, page number, heading breadcrumbs, and item label — making it easy to trace back from chunk to original document location.

---

## Library Comparison Viewer

A Streamlit app that compares how all 4 extraction libraries handle the same PDF page — with **timing** and **accuracy scores**.

```bash
conda run -n developer streamlit run scripts/comparison_viewer.py
```

**Features:**
- Left column: original PDF page (rendered with PyMuPDF)
- Right column: tabbed per library (Docling, pdfplumber, Camelot, Unstructured)
- Each tab shows ALL content types:
  - **Docling**: texts with labels, tables as grids, pictures cropped from PDF
  - **pdfplumber**: extracted text string, tables
  - **Camelot**: lattice + stream tables with Camelot's built-in accuracy metric
  - **Unstructured**: all classified elements (NarrativeText, Title, Header, Footer, Table, Formula, etc.)
- **Summary banner** at the top: timing + accuracy score for each library
- **Per-table quality metrics**: column consistency %, cell fill rate %
- Caches results per page so you can flip through pages without re-extracting

---

## Skills Demonstrated

| Skill | Evidence in this project |
|---|---|
| **Production Python** | Typed, modular, tested code with pyproject.toml |
| **Docker** | Multi-stage Dockerfile + docker-compose |
| **RAG pipelines** | Full ingest → chunk → embed → retrieve → LLM answer flow |
| **LLM Integration** | Ollama/LM Studio client, RAG Q&A, evaluation framework |
| **Evaluation & Metrics** | 20-question test set with accuracy, latency, citation tracking |
| **Data wrangling** | Docling-based PDF extraction with quality gates + multi-library enrichment |
| **CI/CD** | GitHub Actions: lint → typecheck → test → build |
| **Cloud-ready** | Designed for AWS/Azure deployment via Docker |
| **Config-driven design** | YAML profiles — add new OCR engines without code changes |

---

## License

MIT — based on [Docling](https://github.com/docling-project/docling) (MIT).