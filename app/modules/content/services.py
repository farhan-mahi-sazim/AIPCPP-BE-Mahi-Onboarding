import logging
import os
import uuid
from typing import TYPE_CHECKING

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool

from app.common.cache import cache_invalidate, cached
from app.common.cache.constants import CACHE_CONTENT_TTL, ECacheKeyPrefix
from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.storage import StorageService
from app.models.document import Document
from app.models.job import ProcessingJob
from app.modules.content.constants import (
    INVALID_FILE_TYPE_MESSAGE,
    MAX_FILE_SIZE,
)
from app.modules.content.repositories import DocumentRepository, ProcessingJobRepository
from app.modules.content.schemas import (
    TPaginatedSummariesResponse,
    TSummaryRead,
    TUploadResponse,
)

if TYPE_CHECKING:
    from app.models.document import DocumentVersion

logger = logging.getLogger(__name__)


class ContentService:
    def __init__(self, session, storage_service: StorageService) -> None:
        self.session = session
        self.storage_service = storage_service
        self.document_repo = DocumentRepository(session)
        self.job_repo = ProcessingJobRepository(session)

    @staticmethod
    def _generate_s3_key(owner_id: uuid.UUID, file_id: uuid.UUID, filename: str) -> str:
        return f"{owner_id}/{file_id}/{filename}"

    def _get_file_type(self, filename: str) -> EFileType:
        extension = os.path.splitext(filename)[1].lower().lstrip(".")
        extension_map = {
            "pdf": EFileType.PDF,
            "jpg": EFileType.IMAGE,
            "jpeg": EFileType.IMAGE,
            "png": EFileType.IMAGE,
            "txt": EFileType.TEXT,
            "docx": EFileType.DOCX,
            "doc": EFileType.DOC,
        }
        if extension not in extension_map:
            raise ValueError(f"Unsupported file type: {extension}")
        return extension_map[extension]

    def _validate_file_size_early(self, file: UploadFile) -> None:
        content_length = None
        try:
            headers = getattr(file, "headers", None)
            if headers:
                content_length = (
                    headers.get("content-length")
                    if isinstance(headers, dict)
                    else getattr(headers, "get", lambda x: None)("content-length")
                )
        except Exception as e:
            logger.debug("Could not read headers from file: %s", e)

        if content_length:
            try:
                file_size = int(content_length)
                if file_size > MAX_FILE_SIZE:
                    raise ValueError("File too large. Maximum size is 50MB.")
            except ValueError as e:
                if "Maximum size" in str(e):
                    raise
                logger.warning(
                    "Could not parse Content-Length for %s, will validate during upload",
                    file.filename,
                )
        else:
            logger.debug(
                "Content-Length header missing or empty for %s. Size validation during upload.",
                file.filename,
            )

    async def _trigger_pipeline(self, document_id: uuid.UUID) -> None:
        """Triggers the background processing pipeline for a document."""
        try:
            from celery import chain, group

            from app.modules.processing.tasks import (
                analyze_content_task,
                extract_text_task,
                generate_embeddings_task,
                validate_and_finalize_job_task,
            )

            # Optimization: Parallelize Analysis and Embedding after Extraction
            # Finalize task ensures synchronization and state correctness
            processing_pipeline = chain(
                extract_text_task.s(str(document_id)),
                group(analyze_content_task.s(), generate_embeddings_task.s()),
                validate_and_finalize_job_task.s(document_id_str=str(document_id)),
            )
            processing_pipeline.apply_async()
            logger.info("Background pipeline triggered for document %s", document_id)
        except ImportError:
            logger.debug("Celery tasks not yet implemented, skipping pipeline")
        except Exception as e:
            logger.error(
                "Failed to trigger pipeline for document %s: %s", document_id, e
            )

    @cache_invalidate(ECacheKeyPrefix.CONTENT_SUMMARIES.value)
    @cache_invalidate(ECacheKeyPrefix.SEARCH_RESULTS.value)
    async def upload_document(
        self, file: UploadFile, owner_id: uuid.UUID
    ) -> TUploadResponse:
        self._validate_file_size_early(file)

        file_id = uuid.uuid4()
        extension = file.filename.split(".")[-1].upper()

        try:
            file_type = EFileType[extension]
        except KeyError:
            raise ValueError(INVALID_FILE_TYPE_MESSAGE.format(extension=extension))

        s3_key = f"{owner_id}/{file_id}.{extension.lower()}"

        try:
            import io

            await run_in_threadpool(
                self.storage_service.upload_file,
                file_obj=io.BytesIO(await file.read()),
                s3_key=s3_key,
                content_type=file.content_type,
            )
        except Exception as e:
            logger.error("Failed to upload to S3: %s", e)
            raise e

        try:
            document = Document(
                id=file_id,
                owner_id=owner_id,
                filename=file.filename,
                s3_key=s3_key,
                file_type=file_type,
            )
            created_doc = await self.document_repo.create(document)

            job = ProcessingJob(document_id=created_doc.id, status=EJobStatus.PENDING)
            created_job = await self.job_repo.create(job)

            await self._trigger_pipeline(created_doc.id)
            await self.session.commit()

            return TUploadResponse(document=created_doc, job=created_job)

        except Exception as e:
            logger.error(
                "Pipeline trigger or DB commit failed for file %s. S3 key: %s. Error: %s",
                file.filename,
                s3_key,
                str(e),
            )
            await self.session.rollback()

            try:
                await run_in_threadpool(
                    self.storage_service.delete_file,
                    s3_key=s3_key,
                )
                logger.info(
                    "Cleaned up S3 object after pipeline/commit failure: %s", s3_key
                )
            except Exception as cleanup_error:
                logger.error(
                    "Failed to cleanup S3 object after failure: %s. Error: %s",
                    s3_key,
                    str(cleanup_error),
                )

            raise e

    @cached(
        prefix=ECacheKeyPrefix.CONTENT_SUMMARIES.value,
        ttl=CACHE_CONTENT_TTL,
    )
    async def get_all_summaries(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "-created_at",
        owner_id: uuid.UUID | None = None,
        search_query: str | None = None,
    ) -> "TPaginatedSummariesResponse":
        """
        Fetch paginated documents with their latest AI summary.

        Args:
            page: Page number (1-indexed, default: 1)
            page_size: Items per page (default: 20, max: 100)
            sort_by: Field to sort by (prefix with - for descending)
            owner_id: Filter by owner ID (optional)
            search_query: Search in filename (optional)

        Returns:
            Paginated response with summaries and metadata
        """

        offset = (page - 1) * page_size

        rows, total = await self.document_repo.get_all_summaries(
            offset=offset,
            limit=page_size,
            sort_by=sort_by,
            owner_id=owner_id,
            search_query=search_query,
        )

        summaries = [self._build_summary_read(doc, version) for doc, version in rows]

        return TPaginatedSummariesResponse.create(
            data=summaries, total=total, page=page, page_size=page_size
        )

    @staticmethod
    def _build_summary_read(
        doc: "Document", version: "DocumentVersion | None"
    ) -> TSummaryRead:
        """Helper method to build TSummaryRead from Document and DocumentVersion."""
        return TSummaryRead(
            document_id=doc.id,
            filename=doc.filename,
            file_type=doc.file_type,
            summary=version.data.get("summary") if version else None,
            category=version.data.get("category") if version else None,
            tags=version.data.get("tags", []) if version else [],
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    async def get_summary(self, document_id: uuid.UUID) -> TSummaryRead | None:
        row = await self.document_repo.get_summary(document_id)

        if not row:
            return None

        doc, version = row
        return self._build_summary_read(doc, version)

    @cache_invalidate(ECacheKeyPrefix.CONTENT_SUMMARIES.value)
    @cache_invalidate(ECacheKeyPrefix.SEARCH_RESULTS.value)
    async def delete_document(self, document_id: uuid.UUID) -> None:
        doc = await self.document_repo.get_by_id(document_id)
        if not doc:
            raise ValueError("Document not found")

        s3_key = doc.s3_key

        try:
            await run_in_threadpool(self.storage_service.delete_file, s3_key=s3_key)
        except Exception as e:
            logger.error("Failed to delete S3 file %s: %s", s3_key, e)
            raise ValueError(f"Failed to delete S3 file: {e}")

        doc.current_version_id = None
        await self.session.flush()

        await self.document_repo.delete_summary(doc)
        await self.session.commit()
