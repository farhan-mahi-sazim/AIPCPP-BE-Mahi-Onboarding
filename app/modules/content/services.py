import hashlib
import io
import logging
import os
import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import cache_invalidate, cached
from app.common.cache.constants import CACHE_CONTENT_TTL, ECacheKeyPrefix
from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.sse_manager import SSEManager
from app.common.storage import StorageService
from app.models.document import Document
from app.models.job import ProcessingJob
from app.modules.content.constants import MAX_FILE_SIZE
from app.modules.content.exceptions import StorageError
from app.modules.content.progress import create_progress_callback
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
    def __init__(
        self,
        session: AsyncSession,
        storage_service: StorageService,
        progress_manager: SSEManager | None = None,
    ) -> None:
        self.session = session
        self.storage_service = storage_service
        self.document_repo = DocumentRepository(session)
        self.job_repo = ProcessingJobRepository(session)
        self.progress_manager = progress_manager

    @staticmethod
    def _generate_s3_key(owner_id: uuid.UUID, file_id: uuid.UUID, filename: str) -> str:
        return f"{owner_id}/{file_id}/{filename}"

    @staticmethod
    def _compute_file_hash(file_content: bytes) -> str:
        return hashlib.sha256(file_content).hexdigest()

    def _get_file_type(self, filename: str) -> EFileType:
        extension = os.path.splitext(filename)[1].lower().lstrip(".")
        extension_map = {
            "pdf": EFileType.PDF,
            "txt": EFileType.TEXT,
            "docx": EFileType.DOCX,
            "doc": EFileType.DOC,
        }
        image_extensions = {
            "jpg",
            "jpeg",
            "png",
            "gif",
            "bmp",
            "webp",
            "tiff",
            "tif",
            "svg",
        }
        if extension in image_extensions:
            return EFileType.IMAGE
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
        self,
        file: UploadFile,
        owner_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
    ) -> TUploadResponse:
        self._validate_file_size_early(file)

        file_id = document_id or uuid.uuid4()
        file_content = await file.read()
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File too large. Maximum size is 50MB.",
            )
        file_hash = self._compute_file_hash(file_content)

        existing_doc = await self.document_repo.get_by_file_hash(file_hash, owner_id)
        if existing_doc:
            logger.info(
                "Duplicate file detected with hash %s, reusing existing document %s",
                file_hash,
                existing_doc.id,
            )
            existing_job = await self.job_repo.get_by_document_id(existing_doc.id)
            if not existing_job:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Duplicate file found but job is missing.",
                )
            return TUploadResponse(document=existing_doc, job=existing_job)

        extension = file.filename.split(".")[-1].lower()
        file_type = self._get_file_type(f"file.{extension}")

        s3_key = f"{owner_id}/{file_id}.{extension}"

        progress_callback = create_progress_callback(
            self.progress_manager, str(file_id), max_progress=50
        )

        content_type = file.content_type or "application/octet-stream"

        try:
            await run_in_threadpool(
                self.storage_service.upload_file,
                file_obj=io.BytesIO(file_content),
                s3_key=s3_key,
                content_type=content_type,
                progress_callback=progress_callback,
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
                file_hash=file_hash,
                file_type=file_type,
            )
            created_doc = await self.document_repo.create(document)

            job = ProcessingJob(
                document_id=created_doc.id,
                status=EJobStatus.PROCESSING,
                progress=0,
            )
            created_job = await self.job_repo.create(job)

            await self._trigger_pipeline(created_doc.id)
            await self.session.commit()

            # Notify clients that processing has started
            if self.progress_manager:
                await self.progress_manager.publish(
                    str(created_doc.id),
                    progress=0,
                    stage="processing_started",
                )

            return TUploadResponse(
                document=created_doc,
                job=created_job,
            )

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
        file_types: list[EFileType] | None = None,
    ) -> "TPaginatedSummariesResponse":
        """
        Fetch paginated documents with their latest AI summary.

        Args:
            page: Page number (1-indexed, default: 1)
            page_size: Items per page (default: 20, max: 100)
            sort_by: Field to sort by (prefix with - for descending)
            owner_id: Filter by owner ID (optional)
            search_query: Search in filename (optional)
            file_types: Filter by file types (optional)

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
            file_types=file_types,
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
            summary_title=version.data.get("summary_title") if version else None,
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
            raise StorageError(f"Failed to delete S3 file: {e}", s3_key=s3_key)

        doc.current_version_id = None
        await self.session.flush()

        await self.document_repo.delete_summary(doc)
        await self.session.commit()
