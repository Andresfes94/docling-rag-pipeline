# Graph Report - RAG-pipeline  (2026-07-19)

## Corpus Check
- 80 files · ~60,255 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 979 nodes · 1548 edges · 72 communities (66 shown, 6 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 46 edges (avg confidence: 0.51)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7052befa`
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
- 6. Detailed TODO Tickets
- 4. Vulnerabilities & Risk Register
- 3. Strengths
- Tech Lead Architecture Report — Docling RAG Pipeline
- 10. Handoff Notes for Specialist Agents
- 5. Architecture Decision Records
- 7. Data Contracts (Current State)
- 8. Non-Functional Requirements Assessment
- 1. Executive Summary
- 1. Executed Tasks
- Tech Lead Review — Session 10: Data Pipeline Maturity Upgrade
- server.py
- 3. Strengths
- cache.py
- logging_config.py
- test_api.py
- Tech Lead Architecture Report — Docling RAG Pipeline
- AuthMiddleware
- ingest
- 10. Handoff Notes for Specialist Agents
- Session 9 — Final Completion Report
- Session 6 — API Overhaul for LLM Consumption & Comprehensive Comparison Viewer
- retrieve
- create_fixtures.py
- Docling RAG Pipeline — Final Summary
- 5. Architecture Decision Records
- 7. Data Contracts (Current State)
- 8. Non-Functional Requirements Assessment
- 1. Executive Summary
- sample_text.md
- sample_7ab3f2a9.md

## God Nodes (most connected - your core abstractions)
1. `RAGPipeline` - 57 edges
2. `TextCleaner` - 34 edges
3. `validate_source()` - 29 edges
4. `2. Core Concepts (A-Z)` - 26 edges
5. `CrossEncoderReranker` - 21 edges
6. `TestValidateSource` - 20 edges
7. `RetrievalCache` - 19 edges
8. `LLMClient` - 19 edges
9. `TestAPI` - 19 edges
10. `TestTextCleaner` - 19 edges

## Surprising Connections (you probably didn't know these)
- `TestAPI` --uses--> `RetrievalCache`  [INFERRED]
  tests/test_api.py → src/api/cache.py
- `TestAPI` --uses--> `RAGPipeline`  [INFERRED]
  tests/test_api.py → src/retrieval/pipeline.py
- `get_ollama_models()` --calls--> `LLMClient`  [EXTRACTED]
  scripts/chat.py → src/llm/client.py
- `main()` --calls--> `list_profiles()`  [EXTRACTED]
  scripts/run.py → src/ingestion/profiles.py
- `client()` --calls--> `RetrievalCache`  [EXTRACTED]
  tests/test_api.py → src/api/cache.py

## Import Cycles
- None detected.

## Communities (72 total, 6 thin omitted)

### Community 0 - "server.py"
Cohesion: 0.27
Nodes (12): BaseModel, DeleteResponse, DocumentInfoResponse, DocumentListResponse, ErrorResponse, IngestRequest, IngestResponse, Synchronous ingest result (deprecated, use async pattern). (+4 more)

### Community 1 - "RAGPipeline"
Cohesion: 0.06
Nodes (42): HybridChunker, _format_ingest(), main(), chunk_document(), _chunk_page(), ChunkingResult, create_chunker(), DocumentChunk (+34 more)

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
Cohesion: 0.08
Nodes (25): get_ollama_models(), check_api(), check_ollama(), main(), evaluate_all(), evaluate_question(), _fmt(), _has_rejection_phrase() (+17 more)

### Community 6 - "comparison_viewer.py"
Cohesion: 0.22
Nodes (24): _accuracy_bar(), _cell_fill_rate(), _crop_from_pdf(), extract_camelot(), extract_docling(), extract_pdfplumber(), extract_unstructured(), fmt_label() (+16 more)

### Community 7 - "VectorStore"
Cohesion: 0.05
Nodes (21): ndarray, SentenceTransformer, Build Settings from environment variables.          Environment variables can be, Settings, embed_batch(), embed_text(), embedding_dimension(), _get_model() (+13 more)

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
Cohesion: 0.15
Nodes (15): _basic_fallback(), _count_pages(), _detect_garbled(), evaluate(), _find_duplicate_text(), _has_section_headers(), is_fail(), is_pass() (+7 more)

### Community 13 - "Design Decisions"
Cohesion: 0.25
Nodes (8): API architecture, Async ingest pattern, Cache — LRU with TTL, Comprehensive comparison viewer redesign, Design Decisions, LLM-friendly retrieval format, Rate limiting — token bucket algorithm, SSE streaming endpoint

### Community 14 - "docling-evaluate.py"
Cohesion: 0.30
Nodes (11): collect_text_samples(), evaluate(), heuristic_metrics(), load_document(), main(), metrics_from_doc(), page_numbers_from_doc(), parse_args() (+3 more)

### Community 15 - "viewer.py"
Cohesion: 0.33
Nodes (11): crop_image_from_pdf(), extract_page_numbers(), find_pdf_for_document(), format_label(), get_page_items_with_breadcrumbs(), load_json(), main(), render_page_image() (+3 more)

### Community 16 - "RetrievalCache"
Cohesion: 0.31
Nodes (4): Any, RetrievalCache, delete_document(), status()

### Community 17 - "Session 5 — Deep Enrichment: Camelot, Unstructured & Comparison Viewer"
Cohesion: 0.22
Nodes (9): Comparison viewer, E2E results — page 210 of *Mathematics for Finance*, Enrichment chain (deep mode only), Libraries installed, Problem, Quick reference, Session 5 — Deep Enrichment: Camelot, Unstructured & Comparison Viewer, Solution — Three additions (+1 more)

### Community 18 - "Session Journal — Docling RAG Pipeline"
Cohesion: 0.18
Nodes (10): Architecture, Data flow, Design Decisions, Interview Narrative Flow, Pipeline profiles (profiles.yaml), Project, Project Structure, Session Journal — Docling RAG Pipeline (+2 more)

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
Cohesion: 0.14
Nodes (4): Any, TextCleaner, FakeChunk, TestTextCleaner

### Community 24 - "Session 7 — RAG Evaluation Framework & LLM Integration"
Cohesion: 0.40
Nodes (5): Evaluation metrics tracked, New modules, Session 7 — RAG Evaluation Framework & LLM Integration, Usage, Verified (post-reboot checkpoint — 2026-07-18)

### Community 25 - "Bug Fixes During E2E Testing"
Cohesion: 0.50
Nodes (4): 1. Chunker page number extraction — `src/ingestion/chunker.py`, 2. CLI --verbose flag placement — `scripts/run.py`, Bug Fixes During E2E Testing, E2E Test with PHASE404-Strategy.pdf (30 pages)

### Community 27 - "Architecture"
Cohesion: 0.09
Nodes (12): ASGIApp, BaseHTTPMiddleware, Request, Response, RateLimiterMiddleware, CacheStore, Any, RateLimitStore (+4 more)

### Community 28 - "How to Demo (Interview Walkthrough)"
Cohesion: 0.67
Nodes (3): Classic walkthrough, How to Demo (Interview Walkthrough), Quick commands

### Community 39 - "6. Detailed TODO Tickets"
Cohesion: 0.12
Nodes (7): _looks_like_url(), Validate an ingest source path or URL.      Returns an error message string if i, _validate_local_path(), validate_source(), _validate_url(), TestValidateSource, TestValidateSourceIntegration

### Community 40 - "4. Vulnerabilities & Risk Register"
Cohesion: 0.09
Nodes (22): 1. Overview, 2. Files Created/Modified, 3. CrossEncoderReranker, 4. BM25Retriever & HybridRetriever, 5. Pipeline Integration, 6. API Changes, 7. Test Coverage, 8. Performance Characteristics (+14 more)

### Community 41 - "3. Strengths"
Cohesion: 0.10
Nodes (20): 6. Detailed TODO Tickets, Epic 1: Production Scaling (Critical), Epic 2: Reliability & Testing (High), Epic 3: Observability (Medium), Epic 4: Deployment & Configuration (Medium), Epic 5: Technical Debt (Low), TICKET-001: Add Redis-backed persistent state store, TICKET-002: Add API Key authentication middleware (+12 more)

### Community 42 - "Tech Lead Architecture Report — Docling RAG Pipeline"
Cohesion: 0.12
Nodes (17): 4. Vulnerabilities & Risk Register, V-01: In-Memory State (Critical, Certain), V-02: No Authentication or Authorization (Critical, Likely), V-03: Single-Process Rate Limiter (Critical, Likely), V-04: Global Singletons Break Test Isolation (High, Certain), V-05: No Integration Tests for the Core Pipeline (High, Certain), V-06: No Concurrency Control on Chroma Writes (High, Possible), V-07: SSE Stream Drops Connection on Error (High, Possible) (+9 more)

### Community 43 - "10. Handoff Notes for Specialist Agents"
Cohesion: 0.12
Nodes (16): 1. Recommendation, 2. Delivery Assessment by Ticket, 3. What's Left — By Owner, 4. Test & CI Status, 5. Architecture Risk Update, 6. Go/No-Go for Next Milestone, Any Agent (~0.5 day), Backend Engineer (~2 days) (+8 more)

### Community 44 - "5. Architecture Decision Records"
Cohesion: 0.25
Nodes (4): CrossEncoderReranker, Any, FakeChunk, TestCrossEncoderReranker

### Community 45 - "7. Data Contracts (Current State)"
Cohesion: 0.13
Nodes (14): 1. Overview, 2. Files Created/Modified, 3. TextCleaner — Design & Capabilities, 4. Test Coverage, 5. Design Decisions, 6. Gaps & Future Work, Cleaning pipeline (`process_chunks`):, Configuration (all optional, opt-in): (+6 more)

### Community 46 - "8. Non-Functional Requirements Assessment"
Cohesion: 0.15
Nodes (12): 1. Executed Tasks, 2. Test Matrix, 3. Data Engineering Principles Applied, 4. File Inventory, 5. Remaining Gaps (Handoff to Backend/DevOps), Data Engineer Report — Docling RAG Pipeline, Idempotent Ingestion (Complete), Production-Grade Quality Checks (Complete) (+4 more)

### Community 47 - "1. Executive Summary"
Cohesion: 0.17
Nodes (11): 1. Executed Tasks, 2. Test Matrix, 3. Files Changed/Created, 4. Remaining Architecture Gaps, Backend Engineer Report — Docling RAG Pipeline, TICKET-001: Redis-Backed Persistent State Store (P0, Critical), TICKET-002: API Key Authentication Middleware (P0, Critical), TICKET-003: Redis-Backed Rate Limiter (P0, Critical, Depends on TICKET-001) (+3 more)

### Community 48 - "1. Executed Tasks"
Cohesion: 0.17
Nodes (11): 1. Executed Tasks, 2. Test Matrix, 3. Files Changed/Created, 4. Remaining Tickets (All P3 / Low), CI: Integration Test Job, DevOps & Backend Engineer Report — Session 9, Quick Items: Metrics & Logging Gaps, TICKET-011: `.env` Configuration Support (P2, Medium) (+3 more)

### Community 49 - "Tech Lead Review — Session 10: Data Pipeline Maturity Upgrade"
Cohesion: 0.17
Nodes (11): 1. What Was Delivered, 2. RAG Maturity — Before & After, 3. Current Pipeline Architecture (dev branch), 4. Data Cleaning — Design Review, 5. Reranker — Design Review, 6. Hybrid Search — Design Review, 7. Test Quality, 8. Production Readiness Checklist (+3 more)

### Community 50 - "server.py"
Cohesion: 0.24
Nodes (7): _load_keys(), auth_reload(), get_document(), lifespan(), FastAPI, Initialize OpenTelemetry tracing.      Disabled by default. Set OTEL_EXPORTER_OT, setup_tracing()

### Community 51 - "3. Strengths"
Cohesion: 0.18
Nodes (11): 3.10 CI/CD Pipeline, 3.1 Modular Architecture with Clear Boundaries, 3.2 Async-First API Design, 3.3 Token Bucket Rate Limiter, 3.4 LRU Cache with TTL and Source Invalidation, 3.5 Graceful Degradation Chain, 3.6 Config-Driven Profiles, 3.7 Multi-Library Enrichment with Graceful Fallbacks (+3 more)

### Community 52 - "cache.py"
Cohesion: 0.22
Nodes (7): MetricsMiddleware, ASGIApp, BaseHTTPMiddleware, FastAPI, Request, Response, setup_metrics()

### Community 53 - "logging_config.py"
Cohesion: 0.29
Nodes (8): LogRecord, get_elapsed_ms(), get_request_id(), RequestIdFilter, set_elapsed_ms(), set_request_id(), setup_logging(), request_id_middleware()

### Community 54 - "test_api.py"
Cohesion: 0.28
Nodes (8): JSONResponse, get_cache(), get_pipeline(), get_tasks(), global_exception_handler(), Exception, Request, client()

### Community 55 - "Tech Lead Architecture Report — Docling RAG Pipeline"
Cohesion: 0.25
Nodes (7): 2. Architecture Overview (C4 Context), 9. Risk Profile by Layer, Container Diagram, Context Diagram, Module Dependency Graph, Table of Contents, Tech Lead Architecture Report — Docling RAG Pipeline

### Community 56 - "AuthMiddleware"
Cohesion: 0.25
Nodes (6): AuthMiddleware, ASGIApp, BaseHTTPMiddleware, Request, Response, Require X-API-Key header on all endpoints except /health and /metrics.      Read

### Community 57 - "ingest"
Cohesion: 0.38
Nodes (7): BackgroundTasks, IngestTaskResponse, Async ingest task status. Poll with GET /ingest/{task_id}., ingest(), ingest_status(), Any, _run_ingest()

### Community 58 - "10. Handoff Notes for Specialist Agents"
Cohesion: 0.29
Nodes (7): 10. Handoff Notes for Specialist Agents, For the Backend Engineer, For the Data Engineer, For the DevOps Engineer, For the Frontend/3D Engineer, For the GIS / Geospatial Engineer, For the QA Engineer

### Community 59 - "Session 9 — Final Completion Report"
Cohesion: 0.33
Nodes (5): Completed This Session, Files Created/Modified, Session 9 — Final Completion Report, Test Results, What's Left (Deferred / Nice-to-Have)

### Community 60 - "Session 6 — API Overhaul for LLM Consumption & Comprehensive Comparison Viewer"
Cohesion: 0.33
Nodes (6): API Routes (final), Files created/modified, Objectives, Session 6 — API Overhaul for LLM Consumption & Comprehensive Comparison Viewer, Test Results, Verified

### Community 61 - "retrieve"
Cohesion: 0.53
Nodes (6): RetrievedChunkResponse, _build_llm_context(), retrieve(), retrieve_stream(), _where_from_filters(), StreamingResponse

### Community 62 - "create_fixtures.py"
Cohesion: 0.53
Nodes (5): create_image_pdf(), create_sample_pdf(), create_sample_xlsx(), _make_png_bytes(), Path

### Community 63 - "Docling RAG Pipeline — Final Summary"
Cohesion: 0.40
Nodes (4): All Tickets, Docling RAG Pipeline — Final Summary, Reports in This Directory, Risks (V-01 through V-16)

### Community 64 - "5. Architecture Decision Records"
Cohesion: 0.40
Nodes (5): 5. Architecture Decision Records, ADR-001: In-Memory State Must Be Made Persistent Before Multi-Instance Deployment, ADR-002: API Contracts Must Be Defined Before Frontend Development, ADR-003: Prefer Redis Over In-Memory for Production State, ADR-004: Dependency Injection Over Global Singletons

### Community 65 - "7. Data Contracts (Current State)"
Cohesion: 0.40
Nodes (5): 7.1 Internal: Ingestion Pipeline Data Contract, 7.2 External: HTTP API Contract, 7.3 External: LLM Provider Contract, 7.4 Chroma Store Schema, 7. Data Contracts (Current State)

### Community 66 - "8. Non-Functional Requirements Assessment"
Cohesion: 0.40
Nodes (5): 8.1 Performance, 8.2 Security, 8.3 Availability, 8.4 Data Licensing, 8. Non-Functional Requirements Assessment

### Community 67 - "1. Executive Summary"
Cohesion: 0.50
Nodes (4): 1. Executive Summary, Verdict, What needs work before production, What's good

## Knowledge Gaps
- **347 isolated node(s):** `docling-rag-pipeline`, `graphify`, `Table of Contents`, `1. What We Built`, `RAG (Retrieval-Augmented Generation)` (+342 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `RAGPipeline` connect `RAGPipeline` to `server.py`, `LLMClient`, `VectorStore`, `QualityReport`, `5. Architecture Decision Records`, `TestAPI`, `RetrievalCache`, `server.py`, `test_api.py`, `conftest.py`, `ingest`, `retrieve`?**
  _High betweenness centrality (0.104) - this node is a cross-community bridge._
- **Why does `TextCleaner` connect `conftest.py` to `RAGPipeline`, `VectorStore`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Why does `validate_source()` connect `6. Detailed TODO Tickets` to `ingest`, `server.py`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `RAGPipeline` (e.g. with `BatchItemResult` and `BatchResult`) actually correct?**
  _`RAGPipeline` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `TextCleaner` (e.g. with `IngestionResult` and `RAGPipeline`) actually correct?**
  _`TextCleaner` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `CrossEncoderReranker` (e.g. with `IngestionResult` and `RAGPipeline`) actually correct?**
  _`CrossEncoderReranker` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `docling-rag-pipeline`, `graphify`, `Table of Contents` to the rest of the system?**
  _347 weakly-connected nodes found - possible documentation gaps or missing edges._