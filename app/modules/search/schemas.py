from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Search query text")
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of results to skip",
    )


class TSearchMatchChunk(BaseModel):
    chunk_index: int
    highlight: str
    similarity_score: float


class TSearchDocumentResult(BaseModel):
    document_id: UUID
    filename: str
    file_type: str
    summary: str | None = None
    created_at: datetime
    relevance: str = Field(
        description="Relevance level: high (score >= 0.75), medium (>= 0.60), low (< 0.60)"
    )
    match_count: int = Field(description="Number of chunks that matched this document")
    best_chunk: TSearchMatchChunk


class TSearchResponse(BaseModel):
    results: list[TSearchDocumentResult]
    synthesis_answer: str | None = Field(
        default=None,
        description=(
            "Direct answer synthesized from top matching chunks using RAG. "
            "Null when no results are available or synthesis is disabled."
        ),
    )
    total: int = Field(description="Total number of unique documents matched")
    query: str
    limit: int
    offset: int

    model_config = ConfigDict(from_attributes=True)


class TSearchLegacyResult(BaseModel):
    """DEPRECATED: Legacy chunk-level result. Use TSearchDocumentResult instead."""

    document_id: UUID
    filename: str
    file_type: str
    chunk_content: str
    chunk_index: int
    similarity_score: float
    summary: str | None = None
    created_at: datetime


class TLegacySearchResponse(BaseModel):
    """DEPRECATED: Legacy search response. Use TSearchResponse instead."""

    results: list[TSearchLegacyResult]
    total: int
    query: str
    limit: int
    offset: int
