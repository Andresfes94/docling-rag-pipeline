# Graph Report - RAG-pipeline  (2026-07-19)

## Corpus Check
- 45 files · ~33,533 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 547 nodes · 869 edges · 39 communities (34 shown, 5 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 17 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `178db221`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- server.py
- RAGPipeline
- 2. Core Concepts
- Docling RAG Pipeline
- 2. Core Concepts (A-Z)
- LLMClient
- comparison_viewer.py
- VectorStore
- GitHub setup — full transcript
- create_converter
- extractor.py
- QualityReport
- TestAPI
- Design Decisions
- docling-evaluate.py
- viewer.py
- RetrievalCache
- Session 5 — Deep Enrichment: Camelot, Unstructured & Comparison Viewer
- Session Journal — Docling RAG Pipeline
- Session 3 — Full Dataset Ingestion & Document Viewer
- Files Created (34 total)
- Enhancement Round 2 — Auto-detection, Degradation, Parallel Batch
- Docling RAG Pipeline Skill
- conftest.py
- Session 7 — RAG Evaluation Framework & LLM Integration
- Bug Fixes During E2E Testing
- graphify.js
- Architecture
- How to Demo (Interview Walkthrough)
- AGENTS.md
- docling-rag-pipeline

## God Nodes (most connected - your core abstractions)
1. `RAGPipeline` - 28 edges
2. `2. Core Concepts (A-Z)` - 26 edges
3. `Session Journal — Docling RAG Pipeline` - 17 edges
4. `GitHub setup — full transcript` - 16 edges
5. `extract()` - 15 edges
6. `VectorStore` - 15 edges
7. `TestAPI` - 15 edges
8. `2. Core Concepts` - 15 edges
9. `QualityReport` - 13 edges
10. `LLMClient` - 13 edges

## Surprising Connections (you probably didn't know these)
- `get_ollama_models()` --calls--> `LLMClient`  [EXTRACTED]
  scripts/chat.py → src/llm/client.py
- `main()` --calls--> `list_profiles()`  [EXTRACTED]
  scripts/run.py → src/ingestion/profiles.py
- `TestQuality` --uses--> `QualityReport`  [INFERRED]
  tests/test_quality.py → src/ingestion/quality.py
- `check_ollama()` --calls--> `LLMClient`  [EXTRACTED]
  scripts/evaluate_rag.py → src/llm/client.py
- `main()` --calls--> `evaluate_all()`  [EXTRACTED]
  scripts/evaluate_rag.py → src/evaluation/evaluator.py

## Import Cycles
- None detected.

## Communities (39 total, 5 thin omitted)

### Community 0 - "server.py"
Cohesion: 0.08
Nodes (46): ASGIApp, BackgroundTasks, BaseHTTPMiddleware, BaseModel, Exception, FastAPI, JSONResponse, Response (+38 more)

### Community 1 - "RAGPipeline"
Cohesion: 0.09
Nodes (29): HybridChunker, _format_ingest(), main(), chunk_document(), _chunk_page(), ChunkingResult, create_chunker(), DocumentChunk (+21 more)

### Community 2 - "2. Core Concepts"
Cohesion: 0.04
Nodes (47): 1. What We Built, 2. Core Concepts, 3. Architecture Decisions & Why, 4. Problems Encountered & Solutions, 5. Project Structure Map, 6. How to Run Everything, 7. Glossary, API Server (+39 more)

### Community 3 - "Docling RAG Pipeline"
Cohesion: 0.05
Nodes (42): 1. Document Q&A with RAG, 1. Local Installation (pip), 2. Docker Deployment, 2. Quality Validation Pipeline, 3. LLM Setup (for Chat & Evaluation), 3. Multi-Library Extraction Comparison, 4. Batch Document Processing, 4. Verify Installation (+34 more)

### Community 4 - "2. Core Concepts (A-Z)"
Cohesion: 0.05
Nodes (39): 1. What We Built, 2. Core Concepts (A-Z), 3. Architecture Decisions & Trade-offs, 4. Session-by-Session Journey, 5. Key Metrics, 6. Lessons Learned, 7. Glossary, Async Ingestion (+31 more)

### Community 5 - "LLMClient"
Cohesion: 0.11
Nodes (21): get_ollama_models(), check_api(), check_ollama(), main(), evaluate_all(), evaluate_question(), _fmt(), _has_rejection_phrase() (+13 more)

### Community 6 - "comparison_viewer.py"
Cohesion: 0.22
Nodes (24): _accuracy_bar(), _cell_fill_rate(), _crop_from_pdf(), extract_camelot(), extract_docling(), extract_pdfplumber(), extract_unstructured(), fmt_label() (+16 more)

### Community 7 - "VectorStore"
Cohesion: 0.12
Nodes (10): ndarray, SentenceTransformer, embed_batch(), embed_text(), embedding_dimension(), _get_model(), Any, Path (+2 more)

### Community 8 - "GitHub setup — full transcript"
Cohesion: 0.09
Nodes (23): 10. First push — blocked by workflow scope, 11. Work around — push without workflow file first, 12. Grant workflow scope to the token, 13. Re-push with refreshed token, 14. Final repo state, 1. Install GitHub CLI, 2. Check auth status, 3. Web-based auth login (+15 more)

### Community 9 - "create_converter"
Cohesion: 0.20
Nodes (12): DocumentConverter, PdfPipelineOptions, _apply_ocr_engine(), _build_pipeline_options(), _build_standard_options(), _build_vlm_options(), create_converter(), list_profiles() (+4 more)

### Community 10 - "extractor.py"
Cohesion: 0.26
Nodes (17): DoclingDocument, _build_heading_breadcrumbs(), _enrich_tables_with_camelot(), _enrich_tables_with_pdfplumber(), _enrich_with_unstructured(), extract(), ExtractedDocument, ExtractedPicture (+9 more)

### Community 11 - "QualityReport"
Cohesion: 0.26
Nodes (10): _basic_fallback(), evaluate(), is_fail(), is_pass(), is_warn(), Path, QualityReport, Minimal quality check when the evaluator script is unavailable. (+2 more)

### Community 13 - "Design Decisions"
Cohesion: 0.14
Nodes (14): API architecture, API Routes (final), Async ingest pattern, Cache — LRU with TTL, Comprehensive comparison viewer redesign, Design Decisions, Files created/modified, LLM-friendly retrieval format (+6 more)

### Community 14 - "docling-evaluate.py"
Cohesion: 0.30
Nodes (11): collect_text_samples(), evaluate(), heuristic_metrics(), load_document(), main(), metrics_from_doc(), page_numbers_from_doc(), parse_args() (+3 more)

### Community 15 - "viewer.py"
Cohesion: 0.33
Nodes (11): crop_image_from_pdf(), extract_page_numbers(), find_pdf_for_document(), format_label(), get_page_items_with_breadcrumbs(), load_json(), main(), render_page_image() (+3 more)

### Community 17 - "Session 5 — Deep Enrichment: Camelot, Unstructured & Comparison Viewer"
Cohesion: 0.22
Nodes (9): Comparison viewer, E2E results — page 210 of *Mathematics for Finance*, Enrichment chain (deep mode only), Libraries installed, Problem, Quick reference, Session 5 — Deep Enrichment: Camelot, Unstructured & Comparison Viewer, Solution — Three additions (+1 more)

### Community 18 - "Session Journal — Docling RAG Pipeline"
Cohesion: 0.25
Nodes (7): Design Decisions, Interview Narrative Flow, Project, Project Structure, Session Journal — Docling RAG Pipeline, Todo List — All Complete ✅, Verified

### Community 19 - "Session 3 — Full Dataset Ingestion & Document Viewer"
Cohesion: 0.25
Nodes (8): Answer prep, Data directory growth, E2E results — all 6 documents ingested, Key findings, New file, Session 3 — Full Dataset Ingestion & Document Viewer, Usage, Verified checklist (updated)

### Community 20 - "Files Created (34 total)"
Cohesion: 0.29
Nodes (7): Config (5 files), Data, Docs (2 files), Files Created (34 total), Scripts (2 files), Source code (11 files), Tests (4 files)

### Community 21 - "Enhancement Round 2 — Auto-detection, Degradation, Parallel Batch"
Cohesion: 0.29
Nodes (7): E2E results — all scenarios covered, Enhancement Round 2 — Auto-detection, Degradation, Parallel Batch, Files enhanced, Fixes during this round, Graceful degradation chain (verified), New files created, Resource utilization on M3 Pro (11 cores, 18GB, MPS)

### Community 22 - "Docling RAG Pipeline Skill"
Cohesion: 0.33
Nodes (5): Dependencies, Docling RAG Pipeline Skill, Pipeline Profiles, Quality Evaluation, Quick Start

### Community 23 - "conftest.py"
Cohesion: 0.47
Nodes (5): profiles_path(), Path, Create a minimal DoclingDocument JSON for testing., sample_json(), sample_markdown()

### Community 24 - "Session 7 — RAG Evaluation Framework & LLM Integration"
Cohesion: 0.40
Nodes (5): Evaluation metrics tracked, New modules, Session 7 — RAG Evaluation Framework & LLM Integration, Usage, Verified (post-reboot checkpoint — 2026-07-18)

### Community 25 - "Bug Fixes During E2E Testing"
Cohesion: 0.50
Nodes (4): 1. Chunker page number extraction — `src/ingestion/chunker.py`, 2. CLI --verbose flag placement — `scripts/run.py`, Bug Fixes During E2E Testing, E2E Test with PHASE404-Strategy.pdf (30 pages)

### Community 27 - "Architecture"
Cohesion: 0.67
Nodes (3): Architecture, Data flow, Pipeline profiles (profiles.yaml)

### Community 28 - "How to Demo (Interview Walkthrough)"
Cohesion: 0.67
Nodes (3): Classic walkthrough, How to Demo (Interview Walkthrough), Quick commands

## Knowledge Gaps
- **195 isolated node(s):** `docling-rag-pipeline`, `graphify`, `Table of Contents`, `1. What We Built`, `RAG (Retrieval-Augmented Generation)` (+190 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `RAGPipeline` connect `RAGPipeline` to `server.py`, `QualityReport`, `LLMClient`, `VectorStore`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **Why does `Session Journal — Docling RAG Pipeline` connect `Session Journal — Docling RAG Pipeline` to `GitHub setup — full transcript`, `Design Decisions`, `Session 5 — Deep Enrichment: Camelot, Unstructured & Comparison Viewer`, `Session 3 — Full Dataset Ingestion & Document Viewer`, `Files Created (34 total)`, `Enhancement Round 2 — Auto-detection, Degradation, Parallel Batch`, `Session 7 — RAG Evaluation Framework & LLM Integration`, `Bug Fixes During E2E Testing`, `Architecture`, `How to Demo (Interview Walkthrough)`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `RAGPipeline` (e.g. with `BatchItemResult` and `BatchResult`) actually correct?**
  _`RAGPipeline` has 7 INFERRED edges - model-reasoned connections that need verification._
- **What connects `docling-rag-pipeline`, `graphify`, `Table of Contents` to the rest of the system?**
  _195 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `server.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07662337662337662 - nodes in this community are weakly interconnected._
- **Should `RAGPipeline` be split into smaller, more focused modules?**
  _Cohesion score 0.0942684766214178 - nodes in this community are weakly interconnected._
- **Should `2. Core Concepts` be split into smaller, more focused modules?**
  _Cohesion score 0.041666666666666664 - nodes in this community are weakly interconnected._