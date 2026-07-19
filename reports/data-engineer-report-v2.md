# Data Engineer Report — Session 10: Data Cleaning & Normalization

**Author**: Data Engineer
**Date**: 2026-07-19
**Focus**: Text cleaning pipeline, Unicode repair, PII stripping, deduplication, chunk quality filtering

---

## 1. Overview

The ingestion pipeline previously sent raw Docling-extracted text directly to the chunker and embedder with zero cleaning. This session added a `TextCleaner` module that operates on chunked text before storage.

**Pipeline flow (updated)**:
```
Docling → Convert → Extract → Chunk → TextCleaner → VectorStore
                                        │
                                        ├── Unicode repair
                                        ├── Whitespace normalization
                                        ├── PII stripping (email, URL, phone)
                                        ├── Chunk length filtering
                                        └── Content-hash deduplication
```

---

## 2. Files Created/Modified

| File | Action | Purpose |
|---|---|---|
| `src/ingestion/cleaner.py` | **CREATE** | `TextCleaner` class with all cleaning operations |
| `src/retrieval/pipeline.py` | **MODIFY** | Wire `TextCleaner` into `_try_ingest()` between chunking and storage |
| `tests/test_cleaner.py` | **CREATE** | 17 tests covering all cleaning features |

---

## 3. TextCleaner — Design & Capabilities

### Configuration (all optional, opt-in):

| Parameter | Default | Effect |
|---|---|---|
| `fix_unicode` | `True` | Replace `\ufffd`, strip control chars, re-encode to UTF-8 |
| `normalize_whitespace` | `True` | Collapse multi-spaces, normalize newlines (max 2), strip line whitespace |
| `strip_pii` | `True` | Replace emails → `[EMAIL]`, URLs → `[URL]`, phones → `[PHONE]` |
| `min_chunk_chars` | `20` | Drop chunks shorter than this (likely noise/fragments) |
| `max_chunk_chars` | `100_000` | Drop unreasonably long chunks (safety limit) |
| `dedup_by_hash` | `True` | Remove chunks with identical `contextualized_text` (SHA-256) |

### Cleaning pipeline (`process_chunks`):

```
chunks → clean_text(chunk.text) → clean_text(chunk.contextualized_text)
       → filter_by_length() → deduplicate() → reindex()
```

### PII patterns:

| Pattern | Regex | Replacement |
|---|---|---|
| Email | `[\w.+-]+@[\w-]+\.[\w.-]+` | `[EMAIL]` |
| URL | `https?://[^\s<>"']+|www\.[^\s<>"']+` | `[URL]` |
| Phone | `\+?\d[\d\s\-().]{7,}\d` | `[PHONE]` |

All patterns are non-destructive — they replace with placeholders, preserving document structure.

### Deduplication:

SHA-256 hash of `contextualized_text`. First occurrence kept, subsequent identical hashes dropped. Logs count of removed duplicates. Re-indexes remaining chunks after dedup so `chunk_index` remains sequential.

---

## 4. Test Coverage

17 tests in `tests/test_cleaner.py`:

| Test | What it verifies |
|---|---|
| `test_clean_text_strips_whitespace` | Basic `.strip()` |
| `test_clean_text_normalizes_newlines` | `\n{3,}` → `\n\n` |
| `test_clean_text_collapses_spaces` | Multi-space → single |
| `test_clean_text_strips_control_chars` | Null bytes and control chars removed |
| `test_clean_text_strips_pii_email` | Email → `[EMAIL]` |
| `test_clean_text_strips_pii_url` | URL → `[URL]` |
| `test_clean_text_strips_pii_phone` | Phone → `[PHONE]` |
| `test_clean_text_no_pii_flag` | PII stripping skips when disabled |
| `test_deduplicate_removes_duplicates` | Identical chunks collapsed |
| `test_deduplicate_no_duplicates` | Unique chunks preserved |
| `test_filter_by_length_removes_short` | Min length enforced |
| `test_filter_by_length_removes_long` | Max length enforced |
| `test_process_chunks_full_pipeline` | End-to-end clean + dedup + reindex |
| `test_process_chunks_empty_text_removed` | Sub-min chunks dropped |
| `test_unicode_replacement_handling` | `\ufffd` preserved (not stripped entirely) |
| `test_cleaner_disabled` | All features off = passthrough |
| `test_chunk_hash_uses_contextualized_text` | Different context = different hash |

---

## 5. Design Decisions

### Why clean after chunking, not before?

The Docling `HybridChunker` makes structure-aware decisions based on the raw document (headings, paragraph boundaries, table spans). Cleaning before chunking would alter the document text and could degrade chunk boundary quality. Cleaning individual chunk texts after chunking preserves structure while normalizing content.

### Why SHA-256 for dedup?

Content-hash dedup (vs. embedding similarity dedup) is exact, fast (O(n)), and requires no model inference. It catches the common case of duplicated paragraphs, boilerplate headers/footers repeated across pages, and identical table cells. Semantic dedup (near-duplicate detection) can be added later via the reranker.

### Why PII placeholders instead of redaction?

Placeholders (`[EMAIL]`, `[URL]`, `[PHONE]`) preserve document structure and token count alignment. Full redaction (empty string) would shift token boundaries and potentially confuse the chunker's heading context. The placeholders also make it visible to users that PII was detected and handled.

---

## 6. Gaps & Future Work

| Gap | Priority | Notes |
|---|---|---|
| Language detection | P3 | Could skip or flag non-target-language documents |
| Stemming/lemmatization | P3 | Only helps sparse BM25, not dense embeddings |
| Named entity recognition | P3 | Could enrich metadata with extracted entities |
| Semantic dedup | P3 | Use embedding similarity to catch near-duplicates |
| OCR error correction | P4 | Use spellcheck or language model to fix OCR typos |
