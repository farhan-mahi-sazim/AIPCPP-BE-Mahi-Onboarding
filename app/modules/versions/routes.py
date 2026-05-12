from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.db import get_db_session
from app.modules.versions.schemas import (
    TMessageResponse,
    TPaginatedResponse,
    TVersionOverride,
    TVersionRead,
    TVersionUpdate,
)
from app.modules.versions.services import VersionService

router = APIRouter()


@router.get(
    "/{document_id}/timeline",
    response_model=TPaginatedResponse[TVersionRead],
    summary="Get document version history",
)
async def get_document_timeline(
    document_id: UUID,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
):
    service = VersionService(session)
    return await service.get_timeline(document_id, limit, offset)


@router.post(
    "/{document_id}/override",
    response_model=TVersionRead,
    summary="Create a manual human override version",
)
async def create_version_override(
    document_id: UUID,
    override: TVersionOverride,
    session: AsyncSession = Depends(get_db_session),
):
    # TODO: Get actual user_id from auth dependency
    dummy_user_id = UUID("00000000-0000-0000-0000-000000000000")
    service = VersionService(session)
    return await service.create_human_override(document_id, override, dummy_user_id)


@router.patch(
    "/version/{version_id}",
    response_model=TVersionRead,
    summary="Edit an existing human-generated version",
)
async def edit_user_version(
    version_id: UUID,
    update_data: TVersionUpdate,
    session: AsyncSession = Depends(get_db_session),
):
    # TODO: Get actual user_id from auth dependency
    dummy_user_id = UUID("00000000-0000-0000-0000-000000000000")
    service = VersionService(session)
    return await service.update_human_version(version_id, update_data, dummy_user_id)


@router.delete(
    "/version/{version_id}",
    response_model=TMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a human-generated version",
)
async def delete_version(
    version_id: UUID,
    session: AsyncSession = Depends(get_db_session),
):
    # TODO: Get actual user_id from auth dependency
    dummy_user_id = UUID("00000000-0000-0000-0000-000000000000")
    service = VersionService(session)
    await service.delete_version(version_id, dummy_user_id)
    return TMessageResponse(message="Version deleted successfully")
