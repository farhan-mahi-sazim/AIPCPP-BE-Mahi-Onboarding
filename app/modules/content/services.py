import logging
import os
import uuid

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.content.repositories import DocumentRepository, ProcessingJobRepository
from app.models.document import Document, DocumentVersion
from app.models.job import ProcessingJob
from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.storage import StorageService
from app.modules.content.schemas import TUploadResponse, TSummaryRead
from app.modules.content.constants import MAX_FILE_SIZE
from app.modules.processing.tasks import (
    extract_text_task,
    analyze_content_task,
    generate_embeddings_task,
)
from celery import chain
from starlette.concurrency import run_in_threadpool
import os
import logging

logger = logging.getLogger(__name__)


class ContentService:
    def __init__(self, session: AsyncSession, storage_service: StorageService) -> None:
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
        try:
            from celery import chain

            from app.modules.content.tasks import (
                analyze_content_task,
                extract_text_task,
                generate_embeddings_task,
            )

            processing_pipeline = chain(
                extract_text_task.s(str(document_id)),
                analyze_content_task.s(),
                generate_embeddings_task.s(),
            )
            processing_pipeline.apply_async()
            logger.info("Background pipeline triggered for document %s", document_id)
        except ImportError:
            logger.debug("Celery tasks not yet implemented, skipping pipeline")

    async def upload_document(
        self, file: UploadFile, owner_id: uuid.UUID
    ) -> TUploadResponse:
        file_type = self._get_file_type(file.filename)
        self._validate_file_size_early(file)

        file_id = uuid.uuid4()
        s3_key = self._generate_s3_key(owner_id, file_id, file.filename)

        try:
            await run_in_threadpool(
                self.storage_service.upload_file,
                file_obj=file.file,
                s3_key=s3_key,
                content_type=file.content_type or "application/octet-stream",
                max_size=MAX_FILE_SIZE,
            )
        except Exception as e:
            logger.error("S3 upload failed for %s: %s", file.filename, str(e))
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

            await self.session.commit()
            await self._trigger_pipeline(created_doc.id)

            return TUploadResponse(document=created_doc, job=created_job)

        except Exception as e:
            logger.error(
                "Database commit failed for file %s. S3 key: %s. Error: %s",
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
                logger.info("Cleaned up S3 object after DB rollback: %s", s3_key)
            except Exception as cleanup_error:
                logger.error(
                    "Failed to cleanup S3 object after DB failure: %s. Error: %s",
                    s3_key,
                    str(cleanup_error),
                )

            raise e
        self.storage_service = storage_service
        self.document_repo = DocumentRepository(session)
        self.job_repo = ProcessingJobRepository(session)

    @staticmethod
    def _generate_s3_key(owner_id: uuid.UUID, file_id: uuid.UUID, filename: str) -> str:
        return f"{owner_id}/{file_id}/{filename}"

    async def upload_document(
        self, file: UploadFile, owner_id: uuid.UUID
    ) -> TUploadResponse:
        extension = os.path.splitext(file.filename)[1].lower().lstrip(".")

        EXTENSION_MAP = {
            "pdf": EFileType.PDF,
            "jpg": EFileType.IMAGE,
            "jpeg": EFileType.IMAGE,
            "png": EFileType.IMAGE,
            "txt": EFileType.TEXT,
        }

        if extension not in EXTENSION_MAP:
            raise ValueError(f"Unsupported file type: {extension}")

        file_type = EXTENSION_MAP[extension]

        file_id = uuid.uuid4()
        s3_key = self._generate_s3_key(owner_id, file_id, file.filename)

        if file.size and file.size > MAX_FILE_SIZE:
            raise ValueError(f"File too large. Maximum size is 50MB.")

        try:
            await run_in_threadpool(
                self.storage_service.upload_file,
                file_obj=file.file,
                s3_key=s3_key,
                content_type=file.content_type or "application/octet-stream",
            )
        except Exception as e:
            logger.error("S3 upload failed for %s: %s", file.filename, str(e))
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

            await self.session.commit()

            # Trigger Background Pipeline
            processing_pipeline = chain(
                extract_text_task.s(str(created_doc.id)),
                analyze_content_task.s(),  # Receives doc_id from previous task
                generate_embeddings_task.s(),  # Receives doc_id from previous task
            )
            processing_pipeline.apply_async()

            return TUploadResponse(document=created_doc, job=created_job)

        except Exception as e:
            logger.error(
                "Database commit failed for file %s. S3 file is now orphaned: %s. Error: %s",
                file.filename,
                s3_key,
                str(e),
            )
            await self.session.rollback()
            raise e

    async def get_all_summaries(self) -> list[TSummaryRead]:
        """Fetch all documents with their latest AI summary."""
        rows = await self.document_repo.get_all_with_summaries()

        summaries = []
        for doc, version in rows:
            summaries.append(
                TSummaryRead(
                    document_id=doc.id,
                    filename=doc.filename,
                    summary=version.data.get("summary") if version else None,
                    tags=version.data.get("tags", []) if version else [],
                    created_at=doc.created_at,
                )
            )

        return summaries

    async def get_summary(self, document_id: uuid.UUID) -> TSummaryRead | None:
        row = await self.document_repo.get_summary(document_id)

        if not row:
            return None

        doc, version = row
        return TSummaryRead(
            document_id=doc.id,
            filename=doc.filename,
            summary=version.data.get("summary") if version else None,
            tags=version.data.get("tags", []) if version else [],
            created_at=doc.created_at,
        )

    async def delete_document(self, document_id: uuid.UUID) -> None:
        doc = await self.document_repo.get_by_id(document_id)
        if not doc:
            raise ValueError("Document not found")

        s3_key = doc.s3_key

        doc.current_version_id = None
        await self.session.flush()

        await self.document_repo.delete_summary(doc)
        await self.session.commit()

        try:
            await run_in_threadpool(self.storage_service.delete_file, s3_key=s3_key)
        except Exception as e:
            logger.error("Failed to delete S3 file %s: %s", s3_key, e)
