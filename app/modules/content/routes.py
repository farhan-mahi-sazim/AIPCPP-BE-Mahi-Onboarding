import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.storage import StorageService, get_storage_service
from app.config.db import get_db_session
from app.modules.content.constants import (
    DELETE_ERROR_MESSAGE,
    UPLOAD_ERROR_MESSAGE,
    StorageError,
)
from app.modules.content.schemas import (
    TPaginatedSummariesResponse,
    TSummaryRead,
    TUploadResponse,
)
from app.modules.content.services import ContentService

logger = logging.getLogger(__name__)

router = APIRouter()


# Temporary hardcoded User ID until Auth is implemented
DUMMY_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


@router.get("/summaries", response_model=TPaginatedSummariesResponse)
async def get_all_summaries(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max: 100)"),
    sort_by: str = Query(
        "-created_at",
        description="Sort field (prefix with - for descending). Options: created_at, filename, updated_at",
    ),
    search: str | None = Query(
        None, min_length=1, max_length=100, description="Search in filename"
    ),
    db_session: AsyncSession = Depends(get_db_session),
    storage_service: StorageService = Depends(get_storage_service),
):
    """
    Get paginated list of summaries with filtering and sorting.

    Query Parameters:
    - **page**: Page number (1-indexed, default: 1)
    - **page_size**: Items per page (default: 20, max: 100)
    - **sort_by**: Sort field (default: -created_at for descending). Prefix with '-' for descending
    - **search**: Optional search term to filter by filename

    Returns paginated response with metadata (total, total_pages, current page)
    """

    allowed_sorts = {"created_at", "filename", "updated_at"}
    sort_field = sort_by.lstrip("-")
    if sort_field not in allowed_sorts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort_by. Allowed values: {', '.join(allowed_sorts)}",
        )

    service = ContentService(db_session, storage_service)
    try:
        result = await service.get_all_summaries(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            owner_id=DUMMY_USER_ID,
            search_query=search,
        )
        return result
    except Exception as e:
        logger.error("Error fetching paginated summaries: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch summaries",
        )


@router.get("/summaries/{document_id}", response_model=TSummaryRead)
async def get_summary(
    document_id: uuid.UUID,
    db_session: AsyncSession = Depends(get_db_session),
    storage_service: StorageService = Depends(get_storage_service),
):
    """Get a single summary by document ID."""
    service = ContentService(db_session, storage_service)
    summary = await service.get_summary(document_id)
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found"
        )
    return summary


@router.post(
    "/upload", response_model=TUploadResponse, status_code=status.HTTP_201_CREATED
)
async def upload_document(
    file: UploadFile = File(...),
    db_session: AsyncSession = Depends(get_db_session),
    storage_service: StorageService = Depends(get_storage_service),
):
    """
    Upload a document for processing.

    Supported formats: PDF, TXT, PNG, JPG, JPEG
    Maximum file size: 50MB

    Returns the created document and processing job with status.
    """
    service = ContentService(db_session, storage_service)
    try:
        return await service.upload_document(file, owner_id=DUMMY_USER_ID)
    except ValueError as e:
        logger.warning("Upload validation error: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Upload error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=UPLOAD_ERROR_MESSAGE,
        )


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    document_id: uuid.UUID,
    db_session: AsyncSession = Depends(get_db_session),
    storage_service: StorageService = Depends(get_storage_service),
):
    """Delete a document and its associated data."""
    service = ContentService(db_session, storage_service)
    try:
        await service.delete_document(document_id)
        return {"message": "Document and associated content deleted successfully"}
    except ValueError as e:
        logger.warning("Delete error - not found: %s", e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except StorageError as e:
        logger.error("Storage error during deletion for %s: %s", document_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=DELETE_ERROR_MESSAGE,
        )
    except Exception as e:
        logger.error("Deletion failed for %s: %s", document_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document",
        )
