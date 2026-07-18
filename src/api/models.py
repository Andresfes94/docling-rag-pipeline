from __future__ import annotations

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    source: str = Field(description="File path or URL to the document")
    profile: str = Field(default="standard", description="Pipeline profile name")
    skip_quality: bool = Field(default=False, description="Skip quality evaluation")


class IngestResponse(BaseModel):
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


class RetrieveRequest(BaseModel):
    query: str = Field(description="Search query")
    k: int = Field(default=5, ge=1, le=50, description="Number of results")


class RetrievedChunkResponse(BaseModel):
    text: str
    score: float
    source: str = ""
    page: int = 0
    headings: str = ""


class RetrieveResponse(BaseModel):
    query: str
    total_results: int
    results: list[RetrievedChunkResponse] = []


class StatusResponse(BaseModel):
    document_count: int
    sources: list[str] = []
    embedding_model: str = ""
