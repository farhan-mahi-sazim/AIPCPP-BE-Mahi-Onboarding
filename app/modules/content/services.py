from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.content.repositories import ContentRepository
from app.modules.content.schemas import TContentCreate, TContentRead


class ContentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ContentRepository(session)

    async def process_and_store_content(self, data: TContentCreate) -> TContentRead:
        # In a real app, you might trigger a Celery task here or use litellm for processing.
        # For now, we just save the raw data.
        created_content = await self.repository.create(data)

        # Service coordinates commits
        await self.session.commit()
        return created_content
