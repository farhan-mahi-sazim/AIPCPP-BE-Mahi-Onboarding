from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.db import get_db_session
from app.modules.content.services import ContentService
from app.modules.content.schemas import TUploadResponse, TSummaryRead
from app.common.storage import get_storage_service, StorageService
from app.modules.content.constants import UPLOAD_ERROR_MESSAGE
from typing import List
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# Temporary hardcoded User ID until Auth is implemented
DUMMY_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


@router.get("/summaries", response_model=List[TSummaryRead])
async def get_all_summaries(
    db_session: AsyncSession = Depends(get_db_session),
    storage_service: StorageService = Depends(get_storage_service),
):
    service = ContentService(db_session, storage_service)
    return await service.get_all_summaries()


@router.get("/summaries/{document_id}", response_model=TSummaryRead)
async def get_summary(
    document_id: uuid.UUID,
    db_session: AsyncSession = Depends(get_db_session),
    storage_service: StorageService = Depends(get_storage_service),
):
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
    service = ContentService(db_session, storage_service)
    try:
        return await service.upload_document(file, owner_id=DUMMY_USER_ID)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
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
    service = ContentService(db_session, storage_service)
    try:
        await service.delete_document(document_id)
        return {"message": "Document and associated content deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("Deletion failed for %s: %s", document_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document",
        )
