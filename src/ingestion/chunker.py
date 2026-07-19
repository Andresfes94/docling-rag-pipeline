from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer


def _chunk_page(chunk: Any) -> int | None:
    for item in getattr(chunk.meta, "doc_items", []) or []:
        for prov in getattr(item, "prov", []) or []:
            p = getattr(prov, "page_no", None)
            if p is not None:
                return int(p)
    return None


@dataclass
class DocumentChunk:
    text: str
    contextualized_text: str
    headings: list[str] = field(default_factory=list)
    page: int | None = None
    source: str = ""
    chunk_index: int = 0
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkingResult:
    chunks: list[DocumentChunk] = field(default_factory=list)
    total_chunks: int = 0
    min_tokens: int = 0
    max_tokens: int = 0
    avg_tokens: float = 0.0
    empty_document: bool = False


def create_chunker(
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    max_tokens: int = 512,
    merge_peers: bool = True,
) -> HybridChunker:
    tokenizer = HuggingFaceTokenizer.from_pretrained(
        model_name=model_name,
        max_tokens=max_tokens,
    )
    return HybridChunker(tokenizer=tokenizer, merge_peers=merge_peers)


def chunk_markdown(
    markdown_text: str,
    source: str = "",
    max_chars: int = 2000,
    page_quality: list[dict[str, Any]] | None = None,
) -> ChunkingResult:
    import re
    sections = re.split(r"\n(?=#{1,6}\s)", markdown_text)
    result_chunks: list[DocumentChunk] = []
    token_counts: list[int] = []

    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue

        lines = section.split("\n")
        heading = ""
        body_lines: list[str] = []
        for line in lines:
            h_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if h_match and not body_lines:
                heading = h_match.group(2).strip()
                continue
            body_lines.append(line)

        text = "\n".join(body_lines).strip() if body_lines else section
        if not text:
            text = heading
            heading = ""

        meta: dict[str, Any] = {}
        if page_quality and i < len(page_quality):
            meta.update(page_quality[i])

        if len(text) > max_chars:
            sub_chunks = _split_text(text, max_chars)
            for j, sub in enumerate(sub_chunks):
                ctx = f"[{heading}] {sub}" if heading else sub
                tc = len(sub.split())
                token_counts.append(tc)
                result_chunks.append(DocumentChunk(
                    text=sub,
                    contextualized_text=ctx,
                    headings=[heading] if heading else [],
                    source=source,
                    chunk_index=len(result_chunks),
                    token_count=tc,
                    metadata=meta,
                ))
        else:
            ctx = f"[{heading}] {text}" if heading else text
            tc = len(text.split())
            token_counts.append(tc)
            result_chunks.append(DocumentChunk(
                text=text,
                contextualized_text=ctx,
                headings=[heading] if heading else [],
                source=source,
                chunk_index=len(result_chunks),
                token_count=tc,
                metadata=meta,
            ))

    return ChunkingResult(
        chunks=result_chunks,
        total_chunks=len(result_chunks),
        min_tokens=min(token_counts) if token_counts else 0,
        max_tokens=max(token_counts) if token_counts else 0,
        avg_tokens=round(sum(token_counts) / len(token_counts), 1) if token_counts else 0.0,
        empty_document=len(result_chunks) == 0,
    )


def _split_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    if len(paragraphs) > 1:
        chunks: list[str] = []
        current = ""
        for p in paragraphs:
            if len(current) + len(p) + 2 < max_chars:
                current = (current + "\n\n" + p).strip() if current else p
            else:
                if current:
                    chunks.append(current)
                current = p
        if current:
            chunks.append(current)
        if len(chunks) > 1:
            return chunks

    by_dot = text.replace(". ", ".\n").split("\n")
    if len(by_dot) > 1:
        chunks = []
        current = ""
        for s in by_dot:
            if len(current) + len(s) + 1 < max_chars:
                current = (current + " " + s).strip() if current else s
            else:
                if current:
                    chunks.append(current)
                current = s
        if current:
            chunks.append(current)
        if len(chunks) > 1:
            return chunks

    words = text.split()
    chunks = []
    current = ""
    for w in words:
        candidate = (current + " " + w).strip() if current else w
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = w
    if current:
        chunks.append(current)
    return chunks if chunks else [text[:max_chars]]


def chunk_document(
    document: Any,
    source: str = "",
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    max_tokens: int = 512,
    merge_peers: bool = True,
) -> ChunkingResult:
    chunker = create_chunker(
        model_name=model_name,
        max_tokens=max_tokens,
        merge_peers=merge_peers,
    )

    chunks = list(chunker.chunk(document))

    result_chunks: list[DocumentChunk] = []
    token_counts: list[int] = []

    for i, chunk in enumerate(chunks):
        text = chunk.text or ""
        ctx = chunker.contextualize(chunk)

        headings = list(chunk.meta.headings) if chunk.meta.headings else []
        page = _chunk_page(chunk)

        token_count = len(text.split())
        token_counts.append(token_count)

        result_chunks.append(DocumentChunk(
            text=text,
            contextualized_text=ctx,
            headings=headings,
            page=page,
            source=source,
            chunk_index=i,
            token_count=token_count,
        ))

    return ChunkingResult(
        chunks=result_chunks,
        total_chunks=len(result_chunks),
        min_tokens=min(token_counts) if token_counts else 0,
        max_tokens=max(token_counts) if token_counts else 0,
        avg_tokens=round(sum(token_counts) / len(token_counts), 1) if token_counts else 0.0,
        empty_document=len(result_chunks) == 0,
    )
