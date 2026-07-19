# Knowledge Base — Docling RAG Pipeline (by Cline)

> A hands-on, concept-by-concept walkthrough of building a production-grade RAG pipeline for financial document extraction, chunking, embedding, retrieval, and LLM-powered question answering.

---

## Table of Contents

1. [What We Built](#1-what-we-built)
2. [Core Concepts](#2-core-concepts)
   - [RAG (Retrieval-Augmented Generation)](#rag-retrieval-augmented-generation)
   - [Document Extraction](#document-extraction)
   - [OCR (Optical Character Recognition)](#ocr-optical-character-recognition)
   - [VLM (Vision-Language Models)](#vlm-vision-language-models)
   - [Chunking](#chunking)
   - [Embeddings](#embeddings)
   - [Vector Stores](#vector-stores)
   - [Semantic Search](#semantic-search)
   - [Quality Gates](#quality-gates)
   - [Rate Limiting](#rate-limiting)
   - [Caching](#caching)
   - [SSE Streaming](#sse-streaming)
   - [LLM Integration](#llm-integration)
   - [RAG Evaluation](#rag-evaluation)
3. [Architecture Decisions & Why](#3-architecture-decisions--why)
4. [Problems Encountered & Solutions](#4-problems-encountered--solutions)
5. [Project Structure Map](#5-project-structure-map)
6. [How to Run Everything](#6-how-to-run-everything)
7. [Glossary](#7-glossary)

---

## 1. What We Built

A **modular, profile-driven RAG ingestion pipeline** that:

1. Takes a PDF (or URL, Excel file, image) as input
2. Extracts text, tables, and pictures using **Docling** (IBM's document understanding library)
3. Optionally enriches extraction with **pdfplumber**, **Camelot**, and **Unstructured** for better table and formula handling
4. Evaluates extraction **quality** (text density, duplicate detection, replacement characters)
5. **Chunks** the extracted content by heading hierarchy then token count
6. **Embeds** chunks into 384-dimensional vectors using `sentence-transformers/all-MiniLM-L6-v2`
7. **Stores** vectors in **Chroma DB** (persistent, zero-infra vector database)
8. Serves retrieval via a **FastAPI** REST API with rate limiting, caching, SSE streaming, and async ingestion
9. Connects to a local **LLM** (Ollama or LM Studio) for grounded question answering
10. **Evaluates** RAG quality with 20 curated test questions across 4 categories

**Target documents**: Financial PDFs — *Mathematics for Finance*, *Quantitative Trading*, *Algorithmic & High-Frequency Trading*, *PHASE404 Strategy*, *Chatfield Time Series Analysis*, and an Excel spreadsheet.

---

## 2. Core Concepts

### RAG (Retrieval-Augmented Generation)

**What it is**: A pattern where an LLM answers questions using retrieved context from a knowledge base, rather than relying solely on its training data.

**Why we used it**: LLMs hallucinate on topics outside their training data. By retrieving relevant chunks from our financial documents and injecting them into the LLM's prompt as context, we get answers that are:
- **Grounded** in actual document content
- **Traceable** to specific pages and sections
- **Up-to-date** with the latest documents (no retraining needed)

**How it works in this project**:
```
User Question
    │
    ▼
[1] Embed question into vector
    │
    ▼
[2] Search Chroma for top-k similar chunks
    │
    ▼
[3] Assemble chunks into LLM context block
    │
    ▼
[4] Send to LLM: "Answer using ONLY this context"
    │
    ▼
[5] Return answer + source citations
```

**Key files**: `src/llm/rag.py`, `scripts/chat.py`

---

### Document Extraction

**What it is**: Converting unstructured documents (PDFs, images, spreadsheets) into structured text, tables, and metadata.

**Why we used Docling**: Docling (by IBM) provides:
- Native support for PDF, DOCX, PPTX, XLSX, CSV, HTML, and images
- Built-in OCR engines (EasyOCR, Tesseract, ocrmac, RapidOCR)
- VLM pipelines for complex layouts (Granite, SmolDocling)
- A rich `DoclingDocument` object model with `.texts`, `.tables`, `.pictures`, and a `.body` tree
- Heading hierarchy preservation via `iterate_items()` with level information

**The extraction pipeline**:
```
Docling conversion → extract() → pdfplumber enrichment → (deep mode) Camelot + Unstructured
```

**Key data structures**:
- `ExtractedText` — text content with label, page number, heading breadcrumbs
- `ExtractedTable` — markdown-formatted table with page and caption
- `ExtractedPicture` — image reference with page and caption
- `ExtractedDocument` — container for all extracted content

**Key files**: `src/ingestion/extractor.py`, `src/ingestion/loader.py`

---

### OCR (Optical Character Recognition)

**What it is**: Converting images of text (scanned pages) into machine-readable text.

**Why we needed it**: Scanned PDFs have no text layer — they're just images. Without OCR, extraction produces zero text items.

**OCR engines supported**:

| Engine | Best for | Notes |
|---|---|---|
| **EasyOCR** | General scanned PDFs | Deep learning-based, supports 80+ languages |
| **Tesseract** | System-integrated OCR | Requires system install (`brew install tesseract`) |
| **ocrmac** | macOS users | Uses macOS Vision framework, 2-3x faster on Apple Silicon |
| **RapidOCR** | Lightweight deployment | No C dependencies, pure Python |

**Real-world example**: The 293-page *Chatfield Analysis of Time Series* PDF is scanned. With `standard` profile (no OCR): 0 text items. With `ocrmac`: 2,541 text items in 270 seconds.

**Key file**: `profiles.yaml` (OCR engines are configurable, not hardcoded)

---

### VLM (Vision-Language Models)

**What it is**: AI models that understand both images and text — they "see" the page layout and extract content with awareness of structure.

**Why we included VLM profiles**: Some documents have complex layouts (handwriting, multi-column, dense formulas) that traditional OCR struggles with. VLMs like IBM's GraniteDocling understand the visual context.

**VLM profiles available**:
- `vlm_granite` — Full GraniteDocling via HuggingFace Transformers (GPU recommended)
- `vlm_smoldocling` — Lighter VLM model
- `vlm_remote` — Remote API endpoint (vLLM, LM Studio, Ollama)

**Key insight**: VLMs are powerful but slow and GPU-intensive. The pipeline defaults to standard OCR first and only uses VLM when configured.

---

### Chunking

**What it is**: Splitting a long document into smaller, semantically meaningful pieces for embedding and retrieval.

**Why chunking matters**: 
- LLMs have context windows (typically 4K-128K tokens)
- Embedding an entire book produces a single vector — too coarse for precise retrieval
- Chunks must preserve semantic boundaries so each chunk is self-contained

**Our approach — Hybrid Chunker**:
1. **Heading hierarchy first**: Split by document sections (chapter → section → subsection)
2. **Token count subdivision**: If a section exceeds the max token limit, subdivide by token count while respecting paragraph boundaries

**Why hybrid?**: Pure heading-based chunking produces uneven chunks (some huge, some tiny). Pure token-based chunking breaks mid-sentence. Hybrid gives the best of both.

**Configuration**: `HybridChunker(max_tokens=512, merge_peers=True)` — merges small adjacent chunks under the same heading.

**Key file**: `src/ingestion/chunker.py`

---

### Embeddings

**What it is**: Converting text into a fixed-size vector (list of numbers) that captures semantic meaning.

**Why we need them**: To find relevant chunks for a question, we need to measure semantic similarity. Vectors let us do this with simple math — cosine similarity between the question vector and each chunk vector.

**Our embedding model**: `sentence-transformers/all-MiniLM-L6-v2`
- **Output**: 384-dimensional vectors
- **Size**: ~80MB (runs locally, no API calls)
- **Speed**: ~10K chunks/second on M3 Pro
- **Quality**: Good enough for domain-specific financial documents

**How it works**:
```
"option pricing greeks" → [0.23, -0.45, 0.12, ..., 0.89] (384 numbers)
```

**Key file**: `src/embeddings/embedder.py`

---

### Vector Stores

**What it is**: A database optimized for storing and searching vectors by similarity.

**Why Chroma DB**:
- **Zero infrastructure** — persists to disk as SQLite, no server needed
- **Built-in cosine similarity** — no need to implement distance calculations
- **Metadata filtering** — filter by source, page range, heading
- **Python-native** — integrates directly with our pipeline

**What we store per chunk**:
```
{
  "id": "chunk_uuid",
  "vector": [384 floats],
  "metadata": {
    "source": "Mathematics for Finance.pdf",
    "page": 196,
    "headings": "8.3 Black-Scholes Formula",
    "profile": "standard",
    "chunk_index": 42
  }
}
```

**Key file**: `src/storage/vector_store.py`

---

### Semantic Search

**What it is**: Finding documents by meaning rather than keyword matching.

**How it works**:
1. Embed the query into a vector
2. Compute cosine similarity between query vector and all chunk vectors
3. Return top-k chunks ranked by similarity score (0.0 to 1.0)

**Why cosine similarity?**: It measures the angle between vectors, not their magnitude. Two chunks about "option pricing" will have similar direction even if one is longer than the other.

**Example**:
```
Query: "What is delta hedging?"
→ Chunk 1: "Delta hedging neutralizes price risk" (score: 0.87)
→ Chunk 2: "The Black-Scholes formula for call options" (score: 0.52)
→ Chunk 3: "Tokyo population statistics" (score: 0.12)
```

**Key file**: `src/retrieval/pipeline.py`

---

### Quality Gates

**What it is**: Automated checks that evaluate extraction quality before storing chunks.

**Why we need them**: Bad extraction → bad chunks → bad retrieval → bad answers. Quality gates prevent garbage from entering the pipeline.

**Checks performed**:
| Check | What it detects | Threshold |
|---|---|---|
| **Text density** | Empty or near-empty pages | < 100 chars/page → fail |
| **Replacement characters** | Encoding issues ( characters) | > 1% → fail |
| **Duplicate text** | Repeated content across pages | > 50% similarity → warn |
| **Page coverage** | Missing pages | < 80% pages extracted → warn |

**Output**:
```json
{"status": "pass", "metrics": {"page_count": 30, "chars_per_page": 2850.2, "tables": 5}}
```

**Graceful degradation**: If quality fails, the pipeline auto-retries with a different profile (e.g., `standard` → `ocrmac` → `large_document` → `fast`).

**Key files**: `src/ingestion/quality.py`, `scripts/docling-evaluate.py`

---

### Rate Limiting

**What it is**: Controlling how many requests a client can make in a given time window.

**Why we implemented it**: The API could be abused by a single client making thousands of requests per second, overwhelming the embedding model and Chroma.

**Algorithm — Token Bucket**:
- Each client IP gets a bucket per endpoint
- Bucket fills at a fixed rate (e.g., 30 tokens/second for retrieve)
- Each request consumes one token
- If bucket is empty, return HTTP 429 (Too Many Requests)

**Per-endpoint limits**:
| Endpoint | Rate | Burst | Why |
|---|---|---|---|
| `/retrieve` | 30/s | 60 | Read-heavy, fast |
| `/ingest` | 2/s | 4 | Expensive (full document conversion) |
| `/documents` | 60/s | 120 | Lightweight list/delete |
| `/health`, `/status` | 60/s | 120 | Monitoring |

**Why not slowapi?**: We implemented our own token bucket as Starlette middleware — no external dependency, full control over the algorithm, thread-safe with locks.

**Key file**: `src/api/rate_limiter.py`

---

### Caching

**What it is**: Storing previous retrieval results so identical queries return instantly.

**Why we need it**: Users often ask the same or similar questions. Without caching, every query re-embeds the question and searches Chroma — ~200ms per query. With caching, repeated queries return in <1ms.

**Implementation — LRU with TTL**:
- **LRU** (Least Recently Used): When cache is full (1024 entries), evict the least recently accessed entry
- **TTL** (Time To Live): Each entry expires after 5 minutes
- **Cache key**: SHA256 hash of `(query, k, sources_list, format)`
- **Per-format keys**: `format=llm` and `format=json` have separate cache entries (different response structures)
- **Source invalidation**: When a document is re-ingested or deleted, all cache entries containing that source are cleared

**Key file**: `src/api/cache.py`

---

### SSE Streaming

**What it is**: Server-Sent Events — a standard for pushing real-time data from server to client over HTTP.

**Why we implemented it**: For LLM consumption, waiting for all chunks to arrive before starting to process is wasteful. SSE lets the client consume chunks as they're retrieved.

**Stream format**:
```
event: meta
data: {"total": 3, "format": "llm"}

event: chunk
data: [1] Source: Mathematics for Finance | Page: 196 | Section: 8.3 Black-Scholes Formula
data: C_E(S,t) = S e^{-r(T-t)} N(d_1) - X e^{-rT} N(d_2)

event: chunk
data: [2] Source: ...

event: done
data: {}
```

**Key headers**: `Cache-Control: no-cache`, `X-Accel-Buffering: no` (prevents proxy buffering).

**Key file**: `src/api/server.py` (`/retrieve/stream` endpoint)

---

### LLM Integration

**What it is**: Connecting the RAG pipeline to a local large language model for grounded question answering.

**Supported providers**:
| Provider | URL | Use case |
|---|---|---|
| **Ollama** | `http://localhost:11434` | Local models (llama3.2, mistral, deepseek) |
| **LM Studio** | `http://localhost:1234` | OpenAI-compatible local server |

**How the RAG Q&A pipeline works**:
```python
def answer_question(question, k=5, model="llama3.2", provider="ollama"):
    # 1. Retrieve chunks from Chroma
    chunks = retrieve_context(question, k=k)
    
    # 2. Assemble LLM context
    context = format_chunks_for_llm(chunks)
    
    # 3. Build system prompt
    prompt = f"""Answer using ONLY the context below.
    If the context doesn't contain the answer, say so.
    
    Context:
    {context}
    
    Question: {question}"""
    
    # 4. Call LLM
    answer = llm_client.generate(prompt)
    
    return {"answer": answer, "sources": chunks, ...}
```

**Key files**: `src/llm/client.py`, `src/llm/rag.py`, `scripts/chat.py`

---

### RAG Evaluation

**What it is**: A systematic way to measure how well the RAG pipeline performs.

**Why we built it**: Without evaluation, you can't tell if changes improve or degrade RAG quality. We needed objective metrics to validate the pipeline.

**Test set — 20 questions across 4 categories**:

| Category | Count | What it tests | Example |
|---|---|---|---|
| **Factual Recall** | 6 | Can the pipeline find specific facts? | "What is the Black-Scholes formula used for?" |
| **Synthesis** | 6 | Can it combine info across chunks? | "Compare delta vs gamma hedging" |
| **Out-of-Context** | 4 | Does it reject unknown topics? | "What is the population of Tokyo?" |
| **Source Attribution** | 4 | Does it cite sources correctly? | "What does the document say about Greek parameters?" |

**Metrics tracked**:
| Metric | What it measures |
|---|---|
| `overall_accuracy` | % of questions answered correctly |
| `factual_accuracy` | Recall of specific facts |
| `synthesis_accuracy` | Multi-chunk information combination |
| `out_of_context_rejection_rate` | Correct refusal of unknown topics |
| `attribution_accuracy` | Source citation correctness |
| `avg_keyword_coverage` | Fraction of expected keywords in answer |
| `citation_rate` | How often sources are cited |
| `avg_latency_s` | End-to-end time per question |
| `avg_tokens_per_response` | LLM token consumption |

**Key files**: `src/evaluation/test_set.py`, `src/evaluation/evaluator.py`, `scripts/evaluate_rag.py`

---

## 3. Architecture Decisions & Why

### Why YAML for pipeline profiles?

**Decision**: All pipeline configurations (OCR engine, table structure, VLM model) are defined in `profiles.yaml`, not in Python code.

**Why**: 
- Adding a new OCR engine is a config change, not a code change
- Non-engineers can add profiles without touching Python
- Easy to version-control different profile sets for different environments

**Example**: To add a Surya OCR profile:
```yaml
ocr_surya:
  description: "Surya OCR engine"
  pipeline: standard
  options:
    do_ocr: true
    ocr_engine: surya
    do_table_structure: true
```

### Why deferred imports for optional dependencies?

**Decision**: OCR engines (Tesseract, ocrmac, RapidOCR) and enrichment libraries (Camelot, Unstructured) are imported only when their profile is selected.

**Why**: 
- Avoids import errors on systems where these libraries aren't installed
- Keeps startup time fast
- Graceful degradation — if a library is missing, the pipeline falls back to the next available option

### Why hybrid chunking (heading + token)?

**Decision**: Split by heading hierarchy first, then by token count.

**Why**: 
- Pure heading chunking produces uneven chunks (a 2-page section vs a 50-page chapter)
- Pure token chunking breaks mid-sentence or mid-section
- Hybrid preserves semantic boundaries while keeping chunks uniformly sized for embedding

### Why Chroma over Pinecone/Weaviate?

**Decision**: Chroma DB (persistent, local).

**Why**: 
- Zero infrastructure — no server, no cloud costs
- Persists to disk as SQLite — survives reboots
- Sufficient for our scale (2,188 chunks from 6 documents)
- Swappable — the `VectorStore` class is an interface; switching to Pinecone means implementing the same methods

### Why in-memory rate limiter instead of Redis?

**Decision**: Token bucket implemented as Starlette middleware, in-memory with thread-safe locks.

**Why**: 
- No external dependency (Redis) — simpler deployment
- Sufficient for single-instance deployment
- Swappable — the interface supports Redis-backed buckets for multi-instance

### Why `format=llm` for retrieval?

**Decision**: The API supports a `format` parameter that returns chunks as a pre-assembled LLM context string.

**Why**: 
- Saves the client from formatting chunks manually
- Consistent format across all API consumers
- Ready to inject directly into an LLM prompt

### Why async ingest with task polling?

**Decision**: `POST /ingest` returns immediately with a `task_id`; `GET /ingest/{task_id}` polls status.

**Why**: 
- Document conversion can take 5+ minutes (293-page OCR)
- Blocking the HTTP request for 5 minutes would timeout most clients
- Background task pattern decouples request from execution
- Enables horizontal scaling — multiple workers can process ingest tasks

---

## 4. Problems Encountered & Solutions

### Problem 1: Docling produces broken 1×1 empty tables

**Symptom**: On certain born-digital PDF pages, Docling emits `Table — table (1 rows × 1 cols)` with no actual table data. Cell values appear as individual `text` items with spaces inside numbers (`4 . 14452` instead of `4.14452`).

**Root cause**: Docling's table parser fails on certain PDF layouts, producing empty placeholder tables.

**Solution — `_enrich_tables_with_pdfplumber()`**:
1. Scan `result.tables` for suspicious tables (1×1, empty, or no data rows)
2. Group by page, open the original PDF with pdfplumber
3. Extract tables from those specific pages
4. Replace each suspicious Docling table's markdown with pdfplumber's clean version

**Result**: Clean tables with proper columns and correct number formatting.

### Problem 2: Scanned PDFs produce zero text items

**Symptom**: The 293-page *Chatfield Analysis of Time Series* PDF produced 0 text items with the `standard` profile.

**Root cause**: Scanned PDFs have no text layer — they're images. Without OCR, there's nothing to extract.

**Solution — Auto-detection + graceful degradation**:
1. `detector.py` pre-scans the PDF with PyPDF2 to classify as scanned or born-digital
2. For scanned PDFs, auto-selects `ocrmac` (or the best available OCR profile)
3. If OCR times out, falls back to `large_document` (faster, no OCR)
4. If still empty, falls back to `fast` (no tables, no OCR)

**Result**: 2,541 text items from the same 293-page PDF using `ocrmac`.

### Problem 3: `TableItem.export_to_markdown()` deprecated

**Symptom**: `AttributeError` — the method signature changed in a newer Docling version.

**Root cause**: Docling Core API change — `export_to_markdown()` now requires `doc=doc` argument.

**Solution**: Added `doc=doc` argument to the call:
```python
# Before (broken):
table.export_to_markdown()

# After (fixed):
table.export_to_markdown(doc=doc)
```

### Problem 4: Chunker crashes with `AttributeError` on page number

**Symptom**: `DocumentOrigin` has no `page_no` attribute — crashes during chunking.

**Root cause**: Page numbers live on `doc_items[0].prov[0].page_no` (provenance of individual items within a chunk), not on `DocumentOrigin`.

**Solution**: Added `_chunk_page()` helper that iterates `chunk.meta.doc_items` to extract page numbers from item provenance.

### Problem 5: CLI `--verbose` flag only works before subcommand

**Symptom**: `python scripts/run.py ingest doc.pdf --verbose` fails — argparse doesn't recognize `--verbose` after the subcommand.

**Root cause**: Argparse subcommand parsers don't inherit parent parser flags by default.

**Solution**: Extract `--verbose`/`-v` from `sys.argv` before argparse parsing, then filter it out of the argument list.

### Problem 6: GitHub push rejected for workflow file

**Symptom**: `! [remote rejected] main -> main (refusing to allow an OAuth App to create or update workflow .github/workflows/ci.yml without workflow scope)`

**Root cause**: The `gh` auth token had `repo` scope but not `workflow` scope. GitHub requires explicit `workflow` scope to push files under `.github/workflows/`.

**Solution**: 
1. Push code without the workflow file first
2. Refresh the token with `gh auth refresh -h github.com -s workflow`
3. Re-push with the workflow file included

### Problem 7: Batch processing timeout on large PDFs

**Symptom**: `ingest-batch` with 4+ large PDFs hits the 600s per-worker timeout.

**Root cause**: The 293-page Chatfield OCR takes 270s alone. With 4 large PDFs, total time exceeds the timeout.

**Solution**: Individual ingestion is more reliable for files over 200 pages. Batch mode works best for smaller documents or when workers > documents.

### Problem 8: httpx/starlette version mismatch in tests

**Symptom**: 4 API tests fail with import errors related to `httpx` and `starlette`.

**Root cause**: `httpx` 0.28 changed the transport interface. Old `ASGITransport` import path no longer works.

**Solution**: Updated test imports to use `httpx.ASGITransport` (compatible with httpx 0.28+).

### Problem 9: Camelot over-segments tables

**Symptom**: Camelot lattice mode splits every character boundary, producing 5×15 grids instead of 2×7.

**Root cause**: Camelot's lattice algorithm detects every line in the PDF, including character bounding boxes.

**Solution**: 
- Use Camelot as a fallback only (deep mode), not primary
- Compare results across libraries in the comparison viewer
- pdfplumber produces cleaner results for most born-digital PDFs

### Problem 10: Unstructured requires `hi_res` for table HTML

**Symptom**: Unstructured with `strategy='fast'` finds no tables — only text elements.

**Root cause**: Unstructured's `fast` strategy skips table detection. `hi_res` strategy is needed for table HTML output, but is too slow for full documents.

**Solution**: Use Unstructured only for formula patching (deep mode), not for table extraction. Tables are handled by Docling + pdfplumber + Camelot.

---

## 5. Project Structure Map

```
docling-rag-pipeline/
│
├── profiles.yaml                    # Pipeline profiles (YAML-configurable)
├── pyproject.toml                   # Dependencies & tooling
├── Dockerfile                       # Multi-stage build
├── docker-compose.yml               # API service
│
├── src/
│   ├── ingestion/
│   │   ├── profiles.py              # YAML → pipeline options factory
│   │   ├── loader.py                # DocumentConverter wrapper with timeout
│   │   ├── extractor.py             # DoclingDocument traversal + table enrichment
│   │   ├── chunker.py               # HybridChunker (heading + token)
│   │   ├── quality.py               # Quality evaluation wrapper
│   │   └── detector.py              # Pre-scan classification (PyPDF2)
│   │
│   ├── embeddings/
│   │   └── embedder.py              # SentenceTransformer embedding function
│   │
│   ├── storage/
│   │   └── vector_store.py          # Chroma wrapper (persistent, CRUD)
│   │
│   ├── retrieval/
│   │   ├── pipeline.py              # Orchestrator + auto-retry + degradation
│   │   └── batch.py                 # ProcessPoolExecutor parallel batch
│   │
│   ├── llm/
│   │   ├── client.py                # LLM client (Ollama / LM Studio)
│   │   └── rag.py                   # RAG Q&A pipeline
│   │
│   ├── evaluation/
│   │   ├── test_set.py              # 20 curated test questions
│   │   └── evaluator.py             # Evaluation framework + report
│   │
│   └── api/
│       ├── server.py                # FastAPI (10 routes, CORS, middleware)
│       ├── models.py                # Pydantic schemas
│       ├── rate_limiter.py          # Token bucket middleware
│       └── cache.py                 # LRU cache with TTL
│
├── scripts/
│   ├── run.py                       # CLI (ingest, retrieve, detect, batch)
│   ├── docling-evaluate.py          # Quality evaluator
│   ├── viewer.py                    # Streamlit extraction viewer
│   ├── comparison_viewer.py         # Streamlit library comparison
│   ├── chat.py                      # Streamlit RAG chat
│   └── evaluate_rag.py              # RAG evaluation CLI
│
├── tests/
│   ├── conftest.py                  # Test fixtures
│   ├── test_profiles.py             # 8 profile tests
│   ├── test_quality.py              # 5 quality tests
│   └── test_api.py                  # 14 API tests (async)
│
└── data/
    ├── sample/                      # 6 test documents (54 MB)
    ├── output/                      # Conversion artifacts
    └── chroma/                      # Vector store (SQLite)
```

---

## 6. How to Run Everything

### Prerequisites
```bash
conda activate developer
```

### Document Ingestion
```bash
# Detect document type
python scripts/run.py detect mydoc.pdf

# Ingest with auto-detection
python scripts/run.py ingest mydoc.pdf --profile auto

# Ingest with deep enrichment
python scripts/run.py ingest mydoc.pdf --profile standard --deep

# Batch process
python scripts/run.py ingest-batch doc1.pdf doc2.pdf --workers 4
```

### API Server
```bash
# Start server
uvicorn src.api.server:app --reload --port 8000

# Retrieve (JSON)
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "option pricing", "k": 5}'

# Retrieve (LLM format)
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "option pricing", "k": 5, "format": "llm"}'

# SSE streaming
curl -N "http://localhost:8000/retrieve/stream?query=greeks&k=3&format=llm"
```

### RAG Chat (Streamlit)
```bash
# Terminal 1: API server
uvicorn src.api.server:app --port 8000

# Terminal 2: Chat UI
streamlit run scripts/chat.py
```

### RAG Evaluation
```bash
# Full evaluation (requires Ollama + llama3.2)
python scripts/evaluate_rag.py --model llama3.2 --k 5

# Save results
python scripts/evaluate_rag.py --model llama3.2 --k 5 --output results.json
```

### Viewers
```bash
# Document viewer
streamlit run scripts/viewer.py

# Library comparison viewer
streamlit run scripts/comparison_viewer.py
```

### Tests
```bash
# Run all 26 tests
python -m pytest tests/ -v
```

---

## 7. Glossary

| Term | Definition |
|---|---|
| **RAG** | Retrieval-Augmented Generation — using retrieved context to ground LLM answers |
| **Docling** | IBM's document understanding library for PDF/image/text extraction |
| **OCR** | Optical Character Recognition — converting images of text to machine text |
| **VLM** | Vision-Language Model — AI that understands both images and text |
| **Chunking** | Splitting documents into smaller pieces for embedding |
| **Embedding** | Converting text to a vector of numbers that captures meaning |
| **Vector Store** | Database optimized for similarity search on vectors |
| **Cosine Similarity** | Measure of angle between two vectors (0 to 1) |
| **Semantic Search** | Finding content by meaning, not keywords |
| **Quality Gate** | Automated check that validates extraction quality |
| **Token Bucket** | Rate limiting algorithm — tokens fill at a fixed rate, consumed per request |
| **LRU Cache** | Least Recently Used — evicts oldest entries when full |
| **TTL** | Time To Live — how long a cache entry stays valid |
| **SSE** | Server-Sent Events — real-time data push over HTTP |
| **LLM** | Large Language Model — AI that generates text (e.g., llama3.2) |
| **Ollama** | Local LLM runner — download and run models locally |
| **LM Studio** | GUI-based local LLM server with OpenAI-compatible API |
| **Chroma DB** | Open-source vector database (persistent, local) |
| **Sentence Transformers** | Library for generating text embeddings |
| **PyPDF2** | Python library for reading PDF metadata and structure |
| **pdfplumber** | Python library for PDF text and table extraction |
| **Camelot** | Python library for PDF table extraction (lattice + stream) |
| **Unstructured** | Python library for document element classification |
| **FastAPI** | Python web framework for building APIs |
| **Streamlit** | Python framework for building data UIs |
| **Pydantic** | Python library for data validation and schemas |
| **Starlette** | ASGI framework underlying FastAPI |
| **ASGI** | Asynchronous Server Gateway Interface (Python web standard) |
| **BackgroundTasks** | FastAPI mechanism for running work after HTTP response |
| **Graceful Degradation** | Falling back to simpler profiles when a pipeline fails |
| **Auto-Detection** | Pre-scanning a document to classify its type and pick the best profile |
| **Hybrid Chunker** | Chunking by heading hierarchy then token count |
| **Deep Enrichment** | Optional Camelot + Unstructured fallback for better extraction |
| **ProcessPoolExecutor** | Python parallel execution using multiple processes |
| **MPS** | Metal Performance Shaders — Apple's GPU acceleration framework |

---

> *Created by Cline — July 2026*
> 
> *Based on the Docling RAG Pipeline project — a hands-on exploration of production RAG concepts from document ingestion to LLM-powered question answering.*