from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TSearchResult(BaseModel):
    document_id: UUID
    filename: str
    file_type: str
    chunk_content: str
    chunk_index: int
    similarity_score: float
    summary: str | None = None
    created_at: datetime


class TSearchResponse(BaseModel):
    results: list[TSearchResult]
    total: int
    query: str
    limit: int
    offset: int
