"""Batch-clean all existing chunks in the Chroma store using TextCleaner.

Usage:
    python scripts/clean_existing_data.py [--persist-dir data/chroma]
                                          [--model sentence-transformers/all-MiniLM-L6-v2]
                                          [--dry-run]

Reads every chunk from the vector store, runs TextCleaner (PII stripping,
whitespace normalization, dedup, length filter), re-embeds, and re-stores.
Works on a per-source basis — sources with no surviving chunks are deleted.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
_log = logging.getLogger("clean_existing_data")


@dataclass
class _ChunkProxy:
    text: str
    contextualized_text: str
    chunk_index: int = 0
    page: int | None = None
    source: str = ""
    token_count: int = 0
    headings: list[str] = field(default_factory=list)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-clean existing chunks with TextCleaner")
    parser.add_argument("--persist-dir", default="data/chroma", help="ChromaDB persist directory")
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2", help="Embedding model name")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be cleaned without modifying")
    args = parser.parse_args()

    from src.storage.vector_store import VectorStore
    from src.ingestion.cleaner import TextCleaner

    store = VectorStore(persist_directory=args.persist_dir)
    cleaner = TextCleaner()

    all_chunks = store.get_all_chunks()
    if not all_chunks:
        _log.info("No chunks found in store — nothing to clean")
        return

    sources: dict[str, list[dict[str, Any]]] = {}
    for c in all_chunks:
        src = (c.get("metadata") or {}).get("source", "unknown")
        sources.setdefault(src, []).append(c)

    _log.info("Found %d chunks across %d sources", len(all_chunks), len(sources))

    total_original = 0
    total_after = 0
    deleted_sources: list[str] = []

    for source, chunks in sorted(sources.items()):
        total_original += len(chunks)
        proxies: list[_ChunkProxy] = []
        for c in chunks:
            meta = c.get("metadata") or {}
            text = c.get("text", "")
            headings_str = meta.get("headings", "")
            proxies.append(_ChunkProxy(
                text=text,
                contextualized_text=text,
                chunk_index=meta.get("chunk_index", 0),
                page=meta.get("page"),
                source=source,
                token_count=meta.get("token_count", 0),
                headings=headings_str.split(" > ") if headings_str else [],
            ))

        cleaned = cleaner.process_chunks(proxies)

        if not cleaned:
            _log.warning("Source '%s': all %d chunks removed by cleaner — will delete", source, len(proxies))
            deleted_sources.append(source)
            total_after += 0
            continue

        _log.info(
            "Source '%s': %d → %d chunks (removed %d)",
            source, len(proxies), len(cleaned), len(proxies) - len(cleaned),
        )
        total_after += len(cleaned)

        if args.dry_run:
            continue

        store.add_document(chunks=cleaned, source=source, model_name=args.model)

    for source in deleted_sources:
        if not args.dry_run:
            store.delete_source(source)
            _log.info("Deleted source '%s' (all chunks removed)", source)

    _log.info("")
    _log.info("Summary: %d → %d chunks (%d removed)", total_original, total_after, total_original - total_after)

    if deleted_sources:
        _log.info("Sources deleted (no chunks survived): %s", ", ".join(deleted_sources))

    if args.dry_run:
        _log.info("DRY RUN — no changes made")
        return

    from src.retrieval.hybrid_search import BM25Retriever

    bm25 = BM25Retriever()
    chunks_meta = store.get_all_chunks()
    if chunks_meta:
        bm25.build_index(chunks_meta, text_key="text")
        _log.info("BM25 index rebuilt with %d chunks", len(chunks_meta))

    _log.info("Done — %d chunks now in store", store.document_count())


if __name__ == "__main__":
    main()
