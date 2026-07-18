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

## Installation

### System Requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| **Python** | 3.10 | 3.11 |
| **RAM** | 4 GB | 8 GB+ (for OCR / VLM) |
| **Disk** | 2 GB (dependencies) | 10 GB+ (documents + vector store) |
| **OS** | Linux, macOS, Windows (WSL2) | macOS (Apple Silicon) or Linux (GPU) |
| **GPU** | None (CPU-only works) | NVIDIA GPU or Apple MPS |

---

### 1. Local Installation (pip)

#### A. Standard virtual environment

```bash
# Clone the repository
git clone https://github.com/Andresfes94/docling-rag-pipeline.git
cd docling-rag-pipeline

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # Linux / macOS
# venv\Scripts\activate           # Windows (WSL2)

# Upgrade pip
pip install --upgrade pip

# Install all dependencies (core + optional + dev)
pip install -r requirements.txt

# Install the package itself (editable mode for development)
pip install -e .
```

#### B. Conda environment

```bash
conda create -n docling-rag python=3.11
conda activate docling-rag
pip install -r requirements.txt
pip install -e .
```

#### C. Optional dependency groups

| Group | Packages | When you need it |
|---|---|---|
| **Deep Enrichment** | `pdfplumber`, `camelot-py[base]`, `unstructured[pdf]`, `tabulate` | Using `--deep` flag for table/formula enrichment |
| **VLM Pipeline** | `torch`, `transformers`, `accelerate` | Using `vlm_granite` or `vlm_smoldocling` profiles |
| **Apple MLX** | `mlx`, `mlx-lm` | Running Docling on Apple Silicon with MLX acceleration |
| **Dev / Testing** | `pytest`, `pytest-asyncio`, `ruff`, `mypy` | Running tests or type-checking |

Install extras with:
```bash
# All extras
pip install -r requirements.txt

# Individual groups
pip install pdfplumber camelot-py[base] unstructured[pdf] tabulate
pip install torch transformers accelerate
```

#### D. System dependencies

Some optional libraries require system packages:

| Library | macOS (Homebrew) | Linux (apt) |
|---|---|---|
| **Poppler** (Unstructured) | `brew install poppler` | `sudo apt install poppler-utils` |
| **Ghostscript** (Camelot) | `brew install ghostscript` | `sudo apt install ghostscript` |
| **Tesseract** (Tesseract OCR) | `brew install tesseract` | `sudo apt install tesseract-ocr` |

These are **optional** — the pipeline works without them. Missing libraries are caught gracefully at runtime with `ImportError` handling.

---

### 2. Docker Deployment

#### Build and run the API service

```bash
# Build the image (multi-stage, ~5 min first build)
docker compose build

# Start the API server
docker compose up

# Run in detached mode
docker compose up -d

# Follow logs
docker compose logs -f
```

The API is available at `http://localhost:8000`. OpenAPI docs at `http://localhost:8000/docs`.

#### Docker volumes

The `docker-compose.yml` mounts three volumes for persistence and live config:

| Host path | Container path | Purpose |
|---|---|---|
| `./data` | `/app/data` | Persistent vector store (Chroma), conversion artifacts |
| `./profiles.yaml` | `/app/profiles.yaml` | Live pipeline profile configuration |
| `./scripts/docling-evaluate.py` | `/app/scripts/docling-evaluate.py` | Quality evaluator script |

#### Build only (without docker-compose)

```bash
docker build -t docling-rag-pipeline .
docker run -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/profiles.yaml:/app/profiles.yaml" \
  docling-rag-pipeline
```

---

### 3. LLM Setup (for Chat & Evaluation)

The LLM features (`scripts/chat.py`, `scripts/evaluate_rag.py`) require a local LLM server. Choose one:

#### A. Ollama (recommended)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh   # Linux
brew install ollama                               # macOS

# Start the Ollama service
ollama serve

# In a separate terminal, pull a model
ollama pull llama3.2
ollama pull deepseek-r1:8b
ollama pull mistral

# Verify
ollama list
```

The chat scripts connect to `http://localhost:11434` by default.

#### B. LM Studio

1. Download from [lmstudio.ai](https://lmstudio.ai)
2. Download a model (e.g., Llama 3.2, DeepSeek R1)
3. Start the local inference server on port 1234
4. Use `--provider lmstudio` when running chat/evaluation scripts

#### C. Verify LLM connection

```bash
python -c "from src.llm.client import LLMClient; c = LLMClient(); print('Ollama available:', c.check_available())"
```

---

### 4. Verify Installation

```bash
# CLI works
python scripts/run.py --help
python scripts/run.py list-profiles

# Run the test suite (26 tests)
python -m pytest tests/ -v

# Start the API server
uvicorn src.api.server:app --port 8000

# Health check (in another terminal)
curl http://localhost:8000/health
# → {"status": "ok"}
```

---

## Quick Start

Once installed, here's the typical workflow:

### Ingest a document

```bash
# Auto-detect document type and ingest
python scripts/run.py ingest mydocument.pdf --profile auto

# Ingest with deep enrichment (Camelot + Unstructured fallback)
python scripts/run.py ingest mydocument.pdf --profile standard --deep

# Ingest from URL
python scripts/run.py ingest https://arxiv.org/pdf/2408.09869 --profile standard

# Batch process multiple files in parallel
python scripts/run.py ingest-batch doc1.pdf doc2.pdf doc3.pdf --workers 4
```

### Search ingested content

```bash
# Search
python scripts/run.py retrieve "option pricing greeks" --k 5
```

### Interactive RAG chat

```bash
# Requires Ollama running with llama3.2
python scripts/chat.py

# With a specific model
python scripts/chat.py --model deepseek-r1:8b

# With LM Studio
python scripts/chat.py --provider lmstudio --model local-model
```

### Run the RAG evaluation

```bash
# 20-question evaluation against your vector store
python scripts/evaluate_rag.py --model llama3.2 --k 5

# Save results
python scripts/evaluate_rag.py --model llama3.2 --k 5 --output eval_results.json
```

### Launch the Streamlit UIs

```bash
# Document viewer (original PDF vs extracted text side-by-side)
streamlit run scripts/viewer.py

# Library comparison viewer (Docling, pdfplumber, Camelot, Unstructured)
streamlit run scripts/comparison_viewer.py
```

### Start the API server

```bash
uvicorn src.api.server:app --reload --port 8000
# OpenAPI docs: http://localhost:8000/docs
```

---

## Use Cases

### 1. Document Q&A with RAG

Ingest financial/technical documents, then ask questions with automatic context retrieval:

```bash
# Ingest your documents
python scripts/run.py ingest report.pdf --profile auto

# Chat interactively
python scripts/chat.py

# Or use the API for programmatic access
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the Sharpe ratio?", "k": 5, "format": "llm"}'
```

### 2. Quality Validation Pipeline

Before deploying a new document corpus, run the evaluation suite to catch regressions:

```bash
# Run the full 20-question evaluation
python scripts/evaluate_rag.py --model llama3.2 --k 5 --output eval_results.json

# Check accuracy threshold (script exits with code 1 if accuracy < 50%)
echo $?
```

### 3. Multi-Library Extraction Comparison

Compare how different libraries extract the same PDF page:

```bash
streamlit run scripts/comparison_viewer.py
```

Useful for:
- Debugging extraction quality on specific pages
- Choosing the right library for your document types
- Demonstrating the value of hybrid enrichment

### 4. Batch Document Processing

Process large document collections in parallel:

```bash
# Process all PDFs in a directory with 7 workers
python scripts/run.py ingest-batch data/sample/*.pdf --workers 4

# Each worker runs in its own process with isolated conversion
# Results are staged to disk, then batch-imported to Chroma
```

### 5. CI/CD Quality Gate

The quality evaluator can be used in CI to reject poor conversions:

```bash
# Evaluate a conversion
python scripts/docling-evaluate.py data/output/document.json \
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
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_api.py -v

# Run with coverage
python -m pytest tests/ --cov=src
```

All 26 tests pass: profile loading (8), quality evaluation (5), API endpoints (14 async tests).

---

## Document Extraction Viewer

A Streamlit UI that lets you browse ingested documents and compare original pages with extracted text side-by-side.

```bash
streamlit run scripts/viewer.py
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
streamlit run scripts/comparison_viewer.py
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