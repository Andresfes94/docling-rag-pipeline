from __future__ import annotations

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    source: str = Field(
        description="File path or URL to the document (PDF, Excel, image)",
        examples=["/path/to/document.pdf", "https://arxiv.org/pdf/2408.09869"],
    )
    profile: str = Field(
        default="standard",
        description="Pipeline profile name. See GET /profiles or run `python scripts/run.py list-profiles`",
        examples=["standard", "ocrmac", "vlm_granite", "auto"],
    )
    skip_quality: bool = Field(
        default=False,
        description="Skip the quality evaluation gate after conversion",
    )
    deep: bool = Field(
        default=False,
        description="Enable deep enrichment: Camelot table fallback + Unstructured formula patching",
    )


class IngestResponse(BaseModel):
    """Synchronous ingest result (deprecated, use async pattern)."""
    success: bool
    source: str
    profile: str
    pages: int = 0
    duration_seconds: float = 0.0
    chunks: int = 0
    avg_tokens_per_chunk: float = 0.0
    quality_status: str | None = None
    vector_count: int = 0
    error: str | None = None


class IngestTaskResponse(BaseModel):
    """Async ingest task status. Poll with GET /ingest/{task_id}."""
    task_id: str = Field(description="UUID for the ingest task")
    source: str
    status: str = Field(
        description="Current task status",
        examples=["pending", "running", "done", "failed"],
    )
    profile: str = "standard"
    pages: int = 0
    duration_seconds: float = 0.0
    chunks: int = 0
    error: str | None = Field(default=None, description="Error message if status=failed")


class RetrieveRequest(BaseModel):
    query: str = Field(
        description="Natural language search query",
        examples=["option pricing greeks", "what is backtesting"],
    )
    k: int = Field(default=5, ge=1, le=100, description="Number of results to return (1-100)")
    sources: list[str] | None = Field(
        default=None,
        description="Filter: only return chunks from these document sources",
        examples=[["doc1.pdf", "doc2.pdf"]],
    )
    page_range: list[int] | None = Field(
        default=None,
        description="Filter: [min_page, max_page] inclusive",
        min_length=2,
        max_length=2,
        examples=[[1, 50]],
    )
    format: str = Field(
        default="json",
        description='Response format: "json" for raw chunks with metadata, '
        '"llm" for assembled context string ready for prompt injection',
        examples=["json", "llm"],
    )
    min_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity score threshold (0.0-1.0). Results below this are excluded.",
        examples=[0.5, 0.7],
    )
    rerank: bool = Field(
        default=True,
        description="Enable cross-encoder reranking for improved result quality",
    )
    min_rerank_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum cross-encoder reranker score threshold (0.0-1.0)",
        examples=[0.1, 0.3],
    )
    use_hybrid: bool = Field(
        default=False,
        description="Enable BM25 + vector hybrid search with RRF fusion",
    )


class RetrievedChunkResponse(BaseModel):
    text: str = Field(description="Full chunk text")
    score: float = Field(description="Cosine similarity score (0-1, higher = more relevant)")
    source: str = ""
    page: int = 0
    headings: str = Field(default="", description="Heading breadcrumbs, e.g. 'Chapter 3 > Section 2'")


class RetrieveResponse(BaseModel):
    query: str
    total_results: int = Field(description="Number of results returned (may be less than k if filters applied)")
    format: str = Field(default="json", description="Echoes the requested format")
    context: str | None = Field(
        default=None,
        description="Assembled context string when format='llm'. Each chunk formatted as "
        "'[N] Source: X | Page: Y | Section: Z\\n{text}' separated by '---'",
    )
    results: list[RetrievedChunkResponse] = []


class StatusResponse(BaseModel):
    document_count: int = Field(description="Total chunks in the vector store")
    sources: list[str] = Field(default_factory=list, description="Unique document sources")
    embedding_model: str = ""
    chunk_count_by_source: dict[str, int] = Field(
        default_factory=dict,
        description="Per-source chunk counts",
        examples=[{"doc1.pdf": 42, "doc2.pdf": 15}],
    )
    cache_entries: int = Field(default=0, description="Number of entries in the retrieval cache")


class DocumentInfoResponse(BaseModel):
    source: str
    chunk_count: int
    pages: list[int] = Field(default_factory=list, description="Page numbers where chunks exist")
    profiles_used: list[str] = Field(default_factory=list, description="Pipeline profiles used for this document")


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfoResponse] = []
    total: int = 0


class DeleteResponse(BaseModel):
    success: bool
    source: str
    chunks_removed: int = Field(default=0, description="Number of chunks removed from the store")
    error: str | None = None


class ProfileInfo(BaseModel):
    name: str = Field(description="Profile name, used as the `profile` field in /ingest requests")
    description: str = Field(description="Human-readable description of the profile")
    pipeline: str = Field(description="Pipeline backend type (standard, vlm, hybrid)")
    options: dict[str, Any] = Field(default_factory=dict, description="Profile-specific configuration options")


class ProfilesListResponse(BaseModel):
    profiles: list[ProfileInfo] = Field(description="All available pipeline profiles")
    total: int = 0


class ErrorResponse(BaseModel):
    detail: str
    request_id: str | None = Field(default=None, description="Request ID for traceability")
