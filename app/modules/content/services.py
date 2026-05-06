import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile
from app.modules.content.repositories import DocumentRepository, ProcessingJobRepository
from app.models.document import Document
from app.models.job import ProcessingJob
from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.storage import StorageService
from app.modules.content.schemas import TUploadResponse
from app.modules.content.constants import MAX_FILE_SIZE
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
