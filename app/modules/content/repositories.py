from uuid import UUID

from sqlalchemy import delete, desc, func, select
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
        self, limit: int = 10, offset: int = 0
    ) -> list[tuple[Document, DocumentVersion | None]]:
        stmt = (
            select(Document, DocumentVersion)
            .join(
                DocumentVersion,
                Document.current_version_id == DocumentVersion.id,
                isouter=True,
            )
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.all())

    async def get_all_summaries(
        self,
        offset: int = 0,
        limit: int = 20,
        sort_by: str = "-created_at",
        owner_id: UUID | None = None,
        search_query: str | None = None,
    ) -> tuple[list[tuple[Document, DocumentVersion | None]], int]:
        """
        Fetch paginated documents with their latest AI version.

        Args:
            offset: Number of records to skip
            limit: Maximum number of records to return
            sort_by: Field to sort by (prefix with - for descending)
            owner_id: Filter by owner ID (optional)
            search_query: Search in filename (optional)

        Returns:
            Tuple of (paginated results, total count)
        """

        stmt = select(Document, DocumentVersion).join(
            DocumentVersion,
            Document.current_version_id == DocumentVersion.id,
            isouter=True,
        )

        if owner_id:
            stmt = stmt.where(Document.owner_id == owner_id)

        if search_query:
            search_pattern = f"%{search_query}%"
            stmt = stmt.where(Document.filename.ilike(search_pattern))

        count_stmt = select(func.count()).select_from(Document)
        if owner_id:
            count_stmt = count_stmt.where(Document.owner_id == owner_id)
        if search_query:
            search_pattern = f"%{search_query}%"
            count_stmt = count_stmt.where(Document.filename.ilike(search_pattern))

        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        if sort_by.startswith("-"):
            sort_field = sort_by[1:]
            sort_desc = True
        else:
            sort_field = sort_by
            sort_desc = False

        sort_column = getattr(Document, sort_field, Document.created_at)
        if sort_desc:
            stmt = stmt.order_by(desc(sort_column))
        else:
            stmt = stmt.order_by(sort_column)

        stmt = stmt.offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.all()), total

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

    async def get_by_id(self, version_id: UUID) -> DocumentVersion | None:
        return await self.session.get(DocumentVersion, version_id)

    async def get_all_by_document_id(
        self, document_id: UUID, limit: int = 10, offset: int = 0
    ) -> list[DocumentVersion]:
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_by_document_id(
        self, document_id: UUID
    ) -> DocumentVersion | None:
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, version: DocumentVersion) -> DocumentVersion:
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

    def get_by_id(self, version_id: UUID) -> DocumentVersion | None:
        return self.session.get(DocumentVersion, version_id)


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

    def count_by_document_id(self, document_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
        )
        result = self.session.execute(stmt)
        return int(result.scalar_one())


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
