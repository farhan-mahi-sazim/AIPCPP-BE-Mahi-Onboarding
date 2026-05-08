from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk, DocumentVersion
from app.models.job import ProcessingJob

# --- ASYNC REPOSITORIES (Used by FastAPI) ---


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

    async def get_all_with_summaries(
        self,
    ) -> list[tuple[Document, DocumentVersion | None]]:
        """Fetch all documents with their latest AI version."""
        stmt = (
            select(Document, DocumentVersion)
            .join(
                DocumentVersion,
                Document.current_version_id == DocumentVersion.id,
                isouter=True,
            )
            .order_by(Document.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.all())

    async def delete_summary(self, document: Document) -> None:
        await self.session.delete(document)
        await self.session.flush()

    async def get_summary(
        self, document_id: UUID
    ) -> tuple[Document, DocumentVersion | None] | None:
        stmt = (
            select(Document, DocumentVersion)
            .join(
                DocumentVersion,
                Document.current_version_id == DocumentVersion.id,
                isouter=True,
            )
            .where(Document.id == document_id)
        )
        result = await self.session.execute(stmt)
        return result.one_or_none()


class DocumentVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, version: DocumentVersion) -> DocumentVersion:
        self.session.add(version)
        await self.session.flush()
        await self.session.refresh(version)
        return version


class DocumentChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_many(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        self.session.add_all(chunks)
        await self.session.flush()
        return chunks

    async def delete_by_document_id(self, document_id: UUID) -> None:
        stmt = delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        await self.session.execute(stmt)


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

    async def get_by_document_id(self, document_id: UUID) -> ProcessingJob | None:
        stmt = select(ProcessingJob).where(ProcessingJob.document_id == document_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


# --- SYNC REPOSITORIES (Used by Celery) ---


class DocumentRepositorySync:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, document: Document) -> Document:
        self.session.add(document)
        self.session.flush()
        self.session.refresh(document)
        return document

    def get_by_id(self, document_id: UUID) -> Document | None:
        return self.session.get(Document, document_id)


class DocumentVersionRepositorySync:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, version: DocumentVersion) -> DocumentVersion:
        self.session.add(version)
        self.session.flush()
        self.session.refresh(version)
        return version


class DocumentChunkRepositorySync:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_many(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        self.session.add_all(chunks)
        self.session.flush()
        return chunks

    def delete_by_document_id(self, document_id: UUID) -> None:
        stmt = delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        self.session.execute(stmt)


class ProcessingJobRepositorySync:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, job: ProcessingJob) -> ProcessingJob:
        self.session.add(job)
        self.session.flush()
        self.session.refresh(job)
        return job

    def get_by_id(self, job_id: UUID) -> ProcessingJob | None:
        return self.session.get(ProcessingJob, job_id)

    def get_by_document_id(self, document_id: UUID) -> ProcessingJob | None:
        stmt = select(ProcessingJob).where(ProcessingJob.document_id == document_id)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()
