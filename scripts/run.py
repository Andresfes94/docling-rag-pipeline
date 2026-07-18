#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingestion.profiles import list_profiles
from src.ingestion.detector import detect
from src.retrieval.pipeline import RAGPipeline
from src.retrieval.batch import ingest_batch


def _format_ingest(result) -> str:
    lines = [
        f"Ingested:        {result.source}",
        f"Profile:         {result.profile}",
    ]
    if result.retry_chain:
        lines.append(f"Retry chain:     {' → '.join(result.retry_chain)}")
    if result.detector_info:
        d = result.detector_info
        lines.append(f"Detected:        {d['page_count']}pgs, {'scanned' if d['is_scanned'] else 'digital'}, {d['kb_per_page']}KB/pg")
    if result.conversion:
        lines.append(f"Pages:           {result.conversion.page_count}")
        lines.append(f"Duration:        {result.conversion.duration_seconds:.2f}s")
    if result.chunking:
        lines.append(f"Chunks:          {result.chunking.total_chunks}")
        lines.append(f"Avg tokens/chunk: {result.chunking.avg_tokens}")
    if result.quality:
        lines.append(f"Quality status:  {result.quality.status}")
    lines.append(f"Vector store:    {result.vector_count} total documents")
    return "\n".join(lines)


def main() -> None:
    argv = [a for a in sys.argv[1:] if a not in ("-v", "--verbose")]
    verbose = len(argv) != len(sys.argv) - 1

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Docling RAG Pipeline — ingest documents and retrieve chunks",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    ingest_p = sub.add_parser("ingest", help="Ingest a document into the vector store")
    ingest_p.add_argument("source", type=str, help="File path or URL to the document")
    ingest_p.add_argument(
        "--profile", "-p",
        type=str,
        default="standard",
        help="Pipeline profile or 'auto' (default: standard)",
    )
    ingest_p.add_argument(
        "--deep",
        action="store_true",
        help="Enable deep enrichment: Camelot + Unstructured fallback for tables and formula text",
    )
    ingest_p.add_argument(
        "--skip-quality",
        action="store_true",
        help="Skip quality evaluation",
    )
    ingest_p.add_argument(
        "--no-retry",
        action="store_true",
        help="Disable auto-retry chain",
    )

    ingest_batch_p = sub.add_parser("ingest-batch", help="Ingest multiple documents in parallel")
    ingest_batch_p.add_argument("sources", type=str, nargs="+", help="File paths or URLs")
    ingest_batch_p.add_argument(
        "--profile", "-p",
        type=str,
        default="auto",
        help="Pipeline profile or 'auto' (default: auto)",
    )
    ingest_batch_p.add_argument(
        "--workers", "-w",
        type=int,
        default=0,
        help="Number of parallel workers (default: CPU cores - 1)",
    )

    retrieve_p = sub.add_parser("retrieve", help="Search the vector store")
    retrieve_p.add_argument("query", type=str, help="Search query")
    retrieve_p.add_argument("--k", type=int, default=5, help="Number of results (default: 5)")

    sub.add_parser("list-profiles", help="List available pipeline profiles")

    detect_p = sub.add_parser("detect", help="Analyze a document and suggest a profile")
    detect_p.add_argument("source", type=str, help="File path to analyze")

    status_p = sub.add_parser("status", help="Show pipeline status")
    status_p.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Output as JSON",
    )

    args = parser.parse_args(argv)

    pipeline = RAGPipeline()

    if args.command == "list-profiles":
        profiles = list_profiles()
        print(f"Available profiles ({len(profiles)}):")
        for p in profiles:
            print(f"  {p['name']:20s}  {p['description']}")
        return

    if args.command == "detect":
        doc_profile = detect(args.source)
        d = doc_profile.to_dict()
        print(f"Source:          {d['source']}")
        print(f"Pages:           {d['page_count']}")
        print(f"Size:            {d['file_size_bytes'] / 1024:.0f} KB")
        print(f"Selectable text: {d['has_selectable_text']}")
        print(f"Type:            {'scanned' if d['is_scanned'] else 'born-digital'}")
        print(f"KB per page:     {d['kb_per_page']}")
        print(f"Suggested:       {d['suggested_profile']}")
        return

    if args.command == "status":
        status = pipeline.status()
        if args.as_json:
            print(json.dumps(status, indent=2))
        else:
            print(f"Documents in store: {status['document_count']}")
            print(f"Sources: {status['sources'] or '(none)'}")
            print(f"Embedding model: {status['embedding_model']}")
        return

    if args.command == "ingest":
        result = pipeline.ingest(
            source=args.source,
            profile=args.profile,
            skip_quality=args.skip_quality,
            deep=args.deep,
        )

        if result.success:
            print(_format_ingest(result))
        else:
            print(f"FAILED: {result.error}", file=sys.stderr)
            if result.retry_chain:
                print(f"Retried: {' → '.join(result.retry_chain)}", file=sys.stderr)
            sys.exit(1)
        return

    if args.command == "ingest-batch":
        batch_result = ingest_batch(
            sources=args.sources,
            profile=args.profile,
            workers=args.workers,
        )
        print(f"Batch ingest: {batch_result.succeeded}/{batch_result.total} succeeded, "
              f"{batch_result.failed} failed in {batch_result.total_duration:.1f}s")
        for r in batch_result.results:
            status = "✅" if r.success else "❌"
            print(f"  {status} {Path(r.source).name}: {r.profile}, {r.page_count}pgs, {r.chunks} chunks, {r.duration_seconds:.1f}s")
        if batch_result.failed > 0:
            sys.exit(1)
        return

    if args.command == "retrieve":
        result = pipeline.retrieve(query=args.query, k=args.k)

        print(f"Query:    {result.query}")
        print(f"Results:  {result.total_results}")
        print()
        for r in result.results:
            meta = r.metadata
            source = meta.get("source", "?")
            page = meta.get("page", "?")
            headings = meta.get("headings", "")
            score = r.score
            text_preview = r.text[:200].replace("\n", " ")

            print(f"[{score:.3f}] {source} (p.{page})")
            if headings:
                print(f"       headings: {headings}")
            print(f"       {text_preview}...")
            print()
        return


if __name__ == "__main__":
    main()
