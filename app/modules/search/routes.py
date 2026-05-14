from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.config.db import get_db_session
from app.modules.search.constants import (
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_SEARCH_OFFSET,
    MAX_SEARCH_LIMIT,
)
from app.modules.search.schemas import TSearchResponse
from app.modules.search.services import SearchService

router = APIRouter(prefix="/search", tags=["search"])


DUMMY_USER_ID = UUID("00000000-0000-0000-0000-000000000000")


class TSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Search query text")
    limit: int = Field(
        default=DEFAULT_SEARCH_LIMIT,
        ge=1,
        le=MAX_SEARCH_LIMIT,
        description="Maximum number of results",
    )
    offset: int = Field(
        default=DEFAULT_SEARCH_OFFSET,
        ge=0,
        description="Number of results to skip",
    )


async def get_current_user_id() -> UUID:
    return DUMMY_USER_ID


@router.post(
    "",
    response_model=TSearchResponse,
    summary="Semantic Document Search",
    description="Search across document contents using semantic similarity. "
    "Matches query against stored embeddings using cosine similarity.",
)
async def search_documents(
    request: TSearchRequest,
    owner_id: UUID | None = Query(
        None, description="Filter by owner user ID (optional)"
    ),
    session=Depends(get_db_session),
    current_user_id: UUID = Depends(get_current_user_id),
) -> TSearchResponse:
    effective_owner_id = owner_id if owner_id else current_user_id

    service = SearchService(session)
    return await service.search(
        query=request.query,
        owner_id=effective_owner_id,
        limit=request.limit,
        offset=request.offset,
    )
