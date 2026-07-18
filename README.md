# Docling RAG Pipeline

A modular, production-ready **RAG ingestion pipeline** built with [Docling](https://github.com/docling-project/docling) for intelligent document extraction, chunking, embedding, and retrieval.

> Built as an interview project for **Senior Integration Engineer – AI Platform** at octonomy. Demonstrates end-to-end data engineering from unstructured documents to AI-ready vector search.

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
| **REST API** | FastAPI with `/ingest`, `/retrieve`, `/status` endpoints |
| **CLI** | `python scripts/run.py ingest` / `retrieve` / `detect` / `ingest-batch` / `list-profiles` |
| **Extraction Viewer** | `streamlit run scripts/viewer.py` — browse pages with extracted text side-by-side |
| **Docker** | Multi-stage build + `docker-compose.yml` |
| **CI/CD** | GitHub Actions: lint → typecheck → test → build |

---

## Quick Start

```bash
# Install
pip install docling docling-core sentence-transformers chromadb fastapi uvicorn pyyaml

# Detect document type (pre-scan for classification)
python scripts/run.py detect mydocument.pdf

# Ingest a document
python scripts/run.py ingest https://arxiv.org/pdf/2408.09869 --profile standard

# Ingest with auto-detection (recommended)
python scripts/run.py ingest mydocument.pdf --profile auto

# Batch process multiple documents in parallel
python scripts/run.py ingest-batch doc1.pdf doc2.pdf doc3.pdf --workers 7

# Search
python scripts/run.py retrieve "document conversion" --k 5

# List available profiles
python scripts/run.py list-profiles

# Launch the document extraction viewer
streamlit run scripts/viewer.py
```

### API

```bash
# Start server
uvicorn src.api.server:app --port 8000

# Ingest
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "report.pdf", "profile": "standard"}'

# Retrieve
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "key findings", "k": 5}'

# Status
curl http://localhost:8000/status
```

### Docker

```bash
docker compose build
docker compose up
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
                                                                       │
                embedder.py ◄── vector_store.py ◄── pipeline.py ◄──────┘
                                                                       │
                        api/server.py (FastAPI) ◄───────────────────────┘
                            /ingest  /retrieve  /status
```

### Data Flow

1. **Conversion**: Docling parses the document (standard OCR or VLM pipeline)
2. **Extraction**: `DoclingDocument.texts`, `.tables`, `.pictures`, `.body` tree traversal
3. **Quality Gate**: `docling-evaluate.py` checks text density, duplicates, replacement chars
4. **Chunking**: Heading hierarchy first, then token-count subdivision
5. **Embedding**: `sentence-transformers` → 384-dim vectors
6. **Storage**: Chroma with cosine similarity, source metadata, page numbers
7. **Retrieval**: FastAPI returns chunks ranked by semantic similarity

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
│   │   ├── extractor.py        # DoclingDocument traversal
│   │   ├── chunker.py          # HybridChunker wrapper
│   │   ├── quality.py          # Quality evaluation wrapper
│   │   └── detector.py         # Pre-scan classification (PyPDF2)
│   ├── embeddings/embedder.py  # SentenceTransformer embeddings
│   ├── storage/vector_store.py # Chroma persistent store
│   ├── retrieval/
│   │   ├── pipeline.py         # Full orchestration
│   │   └── batch.py            # Parallel batch processor
│   └── api/
│       ├── server.py           # FastAPI endpoints
│       └── models.py           # Pydantic schemas
│
├── scripts/
│   ├── run.py                  # CLI entrypoint
│   ├── docling-evaluate.py     # Quality evaluator
│   └── viewer.py               # Streamlit extraction viewer
│
├── tests/                      # 16 pytest tests
└── skills/SKILL.md             # Agent skill for AI coding tools
```

---

## Testing

```bash
pytest tests/ -v
```

All 16 tests pass: profile loading, quality evaluation, API endpoints.

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

## Skills Demonstrated

| Skill | Evidence in this project |
|---|---|
| **Production Python** | Typed, modular, tested code with pyproject.toml |
| **Docker** | Multi-stage Dockerfile + docker-compose |
| **RAG pipelines** | Full ingest → chunk → embed → retrieve flow |
| **LLM Agent experience** | `skills/SKILL.md` — Cursor/Claude-compatible agent skill |
| **Data wrangling** | Docling-based PDF extraction with quality gates |
| **CI/CD** | GitHub Actions: lint → typecheck → test → build |
| **Cloud-ready** | Designed for AWS/Azure deployment via Docker |
| **Config-driven design** | YAML profiles — add new OCR engines without code changes |

---

## License

MIT — based on [Docling](https://github.com/docling-project/docling) (MIT).
