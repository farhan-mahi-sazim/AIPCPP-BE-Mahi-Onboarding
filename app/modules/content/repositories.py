from sqlalchemy.ext.asyncio import AsyncSession
from app.models.document import Document
from app.models.job import ProcessingJob
from uuid import UUID


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, document: Document) -> Document:
        self.session.add(document)
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def get_by_id(self, document_id: UUID) -> Document | None:
        return await self.session.get(Document, document_id)


class ProcessingJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, job: ProcessingJob) -> ProcessingJob:
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def get_by_id(self, job_id: UUID) -> ProcessingJob | None:
        return await self.session.get(ProcessingJob, job_id)
