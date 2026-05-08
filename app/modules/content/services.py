import logging
import os
import uuid

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.storage import StorageService
from app.models.document import Document
from app.models.job import ProcessingJob
from app.modules.content.constants import MAX_FILE_SIZE
from app.modules.content.repositories import DocumentRepository, ProcessingJobRepository
from app.modules.content.schemas import TUploadResponse

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
