from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.db import get_db_session
from app.modules.content.services import ContentService
from app.modules.content.schemas import TUploadResponse
import uuid

router = APIRouter()


# Temporary hardcoded User ID until Auth is implemented
DUMMY_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


@router.post(
    "/upload", response_model=TUploadResponse, status_code=status.HTTP_201_CREATED
)
async def upload_document(
    file: UploadFile = File(...), db_session: AsyncSession = Depends(get_db_session)
):
    service = ContentService(db_session)
    try:
        return await service.upload_document(file, owner_id=DUMMY_USER_ID)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during file upload.",
        )
