from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.db import get_db_session
from app.modules.content.services import ContentService
from app.modules.content.schemas import TContentCreate, TContentRead

router = APIRouter()


@router.post("/", response_model=TContentRead)
async def create_content(
    content_in: TContentCreate, session: AsyncSession = Depends(get_db_session)
) -> TContentRead:
    service = ContentService(session)
    return await service.process_and_store_content(content_in)
