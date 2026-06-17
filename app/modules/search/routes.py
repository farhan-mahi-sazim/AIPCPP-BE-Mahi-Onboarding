from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.config.db import get_db_session
from app.modules.search.schemas import (
    TLegacySearchResponse,
    TSearchRequest,
    TSearchResponse,
)
from app.modules.search.services import SearchService

router = APIRouter(prefix="/search", tags=["search"])


DUMMY_USER_ID = UUID("00000000-0000-0000-0000-000000000000")


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


@router.post(
    "/legacy",
    response_model=TLegacySearchResponse,
    summary="Legacy Semantic Search (Chunk-Level)",
    description="Chunk-level semantic search response for backward compatibility.",
)
async def search_documents_legacy(
    request: TSearchRequest,
    owner_id: UUID | None = Query(
        None, description="Filter by owner user ID (optional)"
    ),
    session=Depends(get_db_session),
    current_user_id: UUID = Depends(get_current_user_id),
) -> TLegacySearchResponse:
    effective_owner_id = owner_id if owner_id else current_user_id

    service = SearchService(session)
    return await service.search_legacy(
        query=request.query,
        owner_id=effective_owner_id,
        limit=request.limit,
        offset=request.offset,
    )
