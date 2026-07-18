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
