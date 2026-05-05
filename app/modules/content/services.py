import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile
from app.modules.content.repositories import DocumentRepository, ProcessingJobRepository
from app.models.document import Document
from app.models.job import ProcessingJob
from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.storage import storage_service
from app.modules.content.schemas import TUploadResponse
from starlette.concurrency import run_in_threadpool
import os


class ContentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.document_repo = DocumentRepository(session)
        self.job_repo = ProcessingJobRepository(session)

    async def upload_document(
        self, file: UploadFile, owner_id: uuid.UUID
    ) -> TUploadResponse:
        extension = os.path.splitext(file.filename)[1].lower().lstrip(".")
        try:
            file_type = EFileType(extension)
        except ValueError:
            if extension in ["jpg", "jpeg", "png"]:
                file_type = EFileType.IMAGE
            elif extension == "pdf":
                file_type = EFileType.PDF
            elif extension == "txt":
                file_type = EFileType.TEXT
            else:
                raise ValueError(f"Unsupported file type: {extension}")

        content = await file.read()
        file_id = uuid.uuid4()
        s3_key = f"{owner_id}/{file_id}/{file.filename}"

        # from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(
            storage_service.upload_file,
            file_content=content,
            s3_key=s3_key,
            content_type=file.content_type or "application/octet-stream",
        )

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
