import logging
import uuid

from fastapi.concurrency import run_in_threadpool

from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.storage import StorageService
from app.models.document import Document
from app.models.job import ProcessingJob
from app.modules.content.constants import (
    INVALID_FILE_TYPE_MESSAGE,
)
from app.modules.content.repositories import DocumentRepository, ProcessingJobRepository
from app.modules.content.schemas import TSummaryRead, TUploadResponse

logger = logging.getLogger(__name__)


class ContentService:
    def __init__(self, session, storage_service: StorageService) -> None:
        self.session = session
        self.storage_service = storage_service
        self.document_repo = DocumentRepository(session)
        self.job_repo = ProcessingJobRepository(session)

    async def upload_document(self, file, owner_id: uuid.UUID) -> TUploadResponse:
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

    async def _trigger_pipeline(self, document_id: uuid.UUID) -> None:
        try:
            from celery import chain, group

            from app.modules.processing.tasks import (
                analyze_content_task,
                extract_text_task,
                generate_embeddings_task,
            )

            # Optimization: Parallelize Analysis and Embedding after Extraction
            processing_pipeline = chain(
                extract_text_task.s(str(document_id)),
                group(analyze_content_task.s(), generate_embeddings_task.s()),
            )
            processing_pipeline.apply_async()
            logger.info("Background pipeline triggered for document %s", document_id)
        except ImportError:
            logger.debug("Celery tasks not yet implemented, skipping pipeline")

    async def get_all_summaries(
        self, limit: int = 10, offset: int = 0
    ) -> list[TSummaryRead]:
        """Fetch all documents with their latest summary (Paginated)."""
        rows = await self.document_repo.get_all_with_summaries(
            limit=limit, offset=offset
        )

        summaries = []
        for doc, version in rows:
            summaries.append(
                TSummaryRead(
                    document_id=doc.id,
                    filename=doc.filename,
                    summary=version.data.get("summary") if version else None,
                    tags=version.data.get("tags", []) if version else [],
                    category=version.data.get("category") if version else None,
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
            category=version.data.get("category") if version else None,
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
