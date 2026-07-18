---
name: docling-rag-pipeline
description: >
  RAG ingestion pipeline using Docling for document extraction. Converts
  PDFs and other documents, evaluates quality, chunks intelligently,
  embeds, and stores in Chroma for retrieval. Triggers: "ingest document",
  "search documents", "check pipeline status", "convert with OCR".
---

# Docling RAG Pipeline Skill

This project provides a complete RAG ingestion pipeline:

- **Ingestion**: Convert PDF/DOCX/HTML via Docling (standard or VLM pipelines)
- **Quality Gate**: Automatic evaluation with `docling-evaluate.py`
- **Chunking**: Hybrid heading+token chunking via `HybridChunker`
- **Embeddings**: Sentence-transformers (all-MiniLM-L6-v2)
- **Storage**: Chroma vector store (persistent)
- **Retrieval**: FastAPI with `/ingest` and `/retrieve` endpoints

## Quick Start

```bash
# CLI
python scripts/run.py ingest report.pdf --profile ocr_easyocr
python scripts/run.py retrieve "key findings" --k 5

# API
uvicorn src.api.server:app --port 8000
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "report.pdf", "profile": "standard"}'
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "key findings", "k": 5}'
```

## Pipeline Profiles

Configured in `profiles.yaml`:

| Profile | Use Case |
|---|---|
| `standard` | Born-digital PDFs, no OCR |
| `ocr_easyocr` | Scanned PDFs with EasyOCR |
| `ocr_tesseract` | Tesseract OCR |
| `ocrmac` | macOS native OCR |
| `vlm_granite` | Complex layouts (GPU) |
| `vlm_remote` | Remote VLM API |

## Quality Evaluation

```bash
python scripts/docling-evaluate.py data/output/report.json --markdown data/output/report.md
```

## Dependencies

```bash
pip install docling docling-core sentence-transformers chromadb fastapi uvicorn pyyaml
```
