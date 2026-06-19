import asyncio
import contextlib
import hashlib
import json
import logging
import os
import uuid
import zipfile
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

from celery import chain, group
from fastapi import HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import cache_invalidate, cached
from app.common.cache.connection import CacheConnectionManager
from app.common.cache.constants import CACHE_CONTENT_TTL, ECacheKeyPrefix
from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.progress_events import progress_channel_name
from app.common.sse_manager import SSEManager, sse_manager
from app.common.storage import StorageService
from app.models.document import Document, DocumentVersion
from app.models.job import ProcessingJob
from app.modules.content.constants import (
    FILE_MAGIC_SIGNATURES,
    INVALID_FILE_CONTENT_MESSAGE,
    MAGIC_BYTE_READ_SIZE,
    MAX_FILE_SIZE,
)
from app.modules.content.exceptions import StorageError
from app.modules.content.progress import create_progress_callback
from app.modules.content.repositories import (
    DocumentRepository,
    DocumentVersionRepository,
    ProcessingJobRepository,
)
from app.modules.content.schemas import (
    TPaginatedSummariesResponse,
    TSummaryRead,
    TUploadResponse,
)
from app.modules.processing.tasks import (
    analyze_content_task,
    extract_text_task,
    generate_embeddings_task,
    validate_and_finalize_job_task,
)

logger = logging.getLogger(__name__)


async def _cleanup_s3_file(
    storage_service: StorageService, s3_key: str, context: str = ""
) -> None:
    try:
        await run_in_threadpool(
            storage_service.delete_file,
            s3_key=s3_key,
        )
    except Exception as cleanup_error:
        logger.error(
            "Failed to cleanup S3 object%s: %s. Error: %s",
            f" after {context}" if context else "",
            s3_key,
            cleanup_error,
        )


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
        print(f"file size: {file.size}")
        if file.size is not None and file.size > MAX_FILE_SIZE:
            raise ValueError("validated early: File too large. Maximum size is 50MB.")

    @staticmethod
    def _validate_magic_bytes(file_bytes: bytes, file_type: EFileType) -> None:
        signatures = FILE_MAGIC_SIGNATURES.get(file_type, [])
        if not signatures:
            return
        for offset, magic in signatures:
            if len(file_bytes) >= offset + len(magic):
                if file_bytes[offset : offset + len(magic)] == magic:
                    return
        raise ValueError(INVALID_FILE_CONTENT_MESSAGE.format(file_type=file_type.value))

    @staticmethod
    def _validate_docx(file_path: str) -> None:
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                if "word/document.xml" not in zf.namelist():
                    raise ValueError(
                        INVALID_FILE_CONTENT_MESSAGE.format(
                            file_type=EFileType.DOCX.value
                        )
                    )
        except zipfile.BadZipFile:
            raise ValueError(
                INVALID_FILE_CONTENT_MESSAGE.format(file_type=EFileType.DOCX.value)
            )

    async def get_job_by_document_id(
        self, document_id: uuid.UUID
    ) -> ProcessingJob | None:
        return await self.job_repo.get_by_document_id(document_id)

    async def stream_job_progress(
        self, document_id: uuid.UUID
    ) -> AsyncGenerator[str, None]:
        job = await self.get_job_by_document_id(document_id)
        if not job:
            error_payload = {"error": "Job not found"}
            yield f"data: {json.dumps(error_payload)}\n\n"
            return

        document_id_str = str(document_id)

        await sse_manager.publish(
            document_id_str,
            progress=job.progress,
            stage=job.stage.value if job.stage else None,
            status=job.status.value,
            error_log=job.error_log,
        )

        redis_mirror_task = asyncio.create_task(
            self._mirror_redis_progress_to_sse(document_id_str)
        )

        yield f"data: {json.dumps({'type': 'connected', 'document_id': document_id_str, 'stage': job.stage.value if job.stage else None, 'status': job.status.value, 'progress': job.progress})}\n\n"

        logger.info(
            "SSE stream starting for %s (status=%s, progress=%d)",
            document_id_str,
            job.status.value,
            job.progress,
        )

        try:
            async for event in sse_manager.subscribe(document_id_str):
                logger.info(
                    "SSE stream yielding event for %s: status=%s, progress=%d, stage=%s",
                    document_id_str,
                    event.get("status"),
                    event.get("progress"),
                    event.get("stage"),
                )
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("status") in {
                    EJobStatus.COMPLETED.value,
                    EJobStatus.FAILED.value,
                }:
                    while True:
                        try:
                            await asyncio.sleep(30)
                            yield ": keepalive\n\n"
                        except asyncio.CancelledError:
                            logger.info(
                                "SSE client disconnected for document %s", document_id
                            )
                            return
        except asyncio.CancelledError:
            logger.info("SSE client disconnected for document %s", document_id)
            raise
        finally:
            redis_mirror_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await redis_mirror_task

    async def _publish_terminal_state_from_db(self, document_id: str) -> bool:
        try:
            job = await self.job_repo.get_by_document_id(uuid.UUID(document_id))
            if job and job.status in (EJobStatus.COMPLETED, EJobStatus.FAILED):
                await sse_manager.publish(
                    document_id,
                    progress=job.progress,
                    stage=job.stage.value if job.stage else None,
                    status=job.status.value,
                    error_log=job.error_log,
                )
                return True
        except Exception as e:
            logger.debug("Failed to check terminal state for %s: %s", document_id, e)
        return False

    async def _mirror_redis_progress_to_sse(self, document_id: str) -> None:
        terminal = await self._publish_terminal_state_from_db(document_id)
        if terminal:
            return

        redis_client = await CacheConnectionManager.get_connection()
        if redis_client is None:
            logger.debug("Redis unavailable for SSE mirroring: %s", document_id)
            return

        pubsub = redis_client.pubsub()
        channel = progress_channel_name(document_id)

        try:
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue

                try:
                    payload = json.loads(message.get("data", "{}"))
                except json.JSONDecodeError:
                    logger.debug(
                        "Ignoring malformed progress payload for %s", document_id
                    )
                    continue

                if payload.get("document_id") != document_id:
                    continue

                await sse_manager.publish(
                    document_id,
                    progress=int(payload.get("progress", 0)),
                    stage=payload.get("stage"),
                    status=payload.get("status"),
                    error_log=payload.get("error_log"),
                )

                if payload.get("status") in {
                    EJobStatus.COMPLETED.value,
                    EJobStatus.FAILED.value,
                }:
                    break
        except asyncio.CancelledError:
            raise
        finally:
            try:
                await pubsub.unsubscribe(channel)
            except Exception:
                logger.debug("Redis pubsub unsubscribe failed for %s", document_id)
            await pubsub.close()

    async def _trigger_pipeline(self, document_id: uuid.UUID) -> None:
        """Triggers the background processing pipeline for a document."""
        job = await self.job_repo.get_by_document_id(document_id)
        if job and job.status == EJobStatus.COMPLETED:
            logger.info(
                "Pipeline already completed for document %s, skipping", document_id
            )
            return
        if job and job.status == EJobStatus.PROCESSING:
            logger.info(
                "Pipeline already in progress for document %s, skipping", document_id
            )
            return

        try:
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

    async def _return_existing_or_raise(
        self, existing_doc: Document
    ) -> TUploadResponse:
        existing_job = await self.job_repo.get_by_document_id(existing_doc.id)
        if not existing_job:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate file found but job is missing.",
            )
        return TUploadResponse(document=existing_doc, job=existing_job)

    async def _save_and_validate_upload(
        self,
        file: UploadFile,
        file_type: EFileType,
        upload_dir: Path,
    ) -> tuple[str, str]:
        hasher = hashlib.sha256()
        temp_path = str(upload_dir / f"{uuid.uuid4()}.tmp")
        with open(temp_path, "wb") as temp_file:
            first_chunk = await file.read(MAGIC_BYTE_READ_SIZE)
            if not first_chunk:
                raise ValueError("Empty file")
            self._validate_magic_bytes(first_chunk, file_type)
            hasher.update(first_chunk)
            temp_file.write(first_chunk)
            total_bytes = len(first_chunk)
            while chunk := await file.read(65536):
                hasher.update(chunk)
                temp_file.write(chunk)
                total_bytes += len(chunk)
                if total_bytes > MAX_FILE_SIZE:
                    raise ValueError("File too large. Maximum size is 50MB.")
        file_hash = hasher.hexdigest()
        if file_type == EFileType.DOCX:
            self._validate_docx(temp_path)
        return temp_path, file_hash

    async def _handle_dedup_race(
        self,
        file_hash: str,
        owner_id: uuid.UUID,
        s3_key: str,
    ) -> TUploadResponse:
        logger.info(
            "Race condition on dedup for hash %s, fetching existing document",
            file_hash,
        )
        await _cleanup_s3_file(self.storage_service, s3_key, "dedup race")
        await self.session.rollback()

        existing_doc = await self.document_repo.get_by_file_hash(file_hash, owner_id)
        if not existing_doc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate file found but document is missing.",
            )
        return await self._return_existing_or_raise(existing_doc)

    @cache_invalidate(ECacheKeyPrefix.CONTENT_SUMMARIES.value)
    @cache_invalidate(ECacheKeyPrefix.SEARCH_RESULTS.value)
    async def upload_document(
        self,
        file: UploadFile,
        owner_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
    ) -> TUploadResponse:
        self._validate_file_size_early(file)

        safe_filename = Path(file.filename).name
        extension = safe_filename.split(".")[-1].lower()
        file_type = self._get_file_type(f"file.{extension}")

        file_id = document_id or uuid.uuid4()
        s3_key = f"{owner_id}/{file_id}.{extension}"

        temp_path = None
        upload_dir = Path("/tmp/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        try:
            temp_path, file_hash = await self._save_and_validate_upload(
                file, file_type, upload_dir
            )

            existing_doc = await self.document_repo.get_by_file_hash(
                file_hash, owner_id
            )
            if existing_doc:
                logger.info(
                    "Duplicate file detected with hash %s, reusing existing document %s",
                    file_hash,
                    existing_doc.id,
                )
                return await self._return_existing_or_raise(existing_doc)

            total_bytes = os.path.getsize(temp_path)
            progress_callback = create_progress_callback(
                self.progress_manager,
                str(file_id),
                max_progress=40,
                total_bytes=total_bytes,
            )

            content_type = file.content_type or "application/octet-stream"

            try:
                with open(temp_path, "rb") as f:
                    await run_in_threadpool(
                        self.storage_service.upload_file,
                        file_obj=f,
                        s3_key=s3_key,
                        content_type=content_type,
                        max_size=MAX_FILE_SIZE,
                        progress_callback=progress_callback,
                    )
            except Exception as e:
                logger.error("Failed to upload to S3: %s", e)
                raise

            document = Document(
                id=file_id,
                owner_id=owner_id,
                filename=safe_filename,
                s3_key=s3_key,
                file_hash=file_hash,
                file_type=file_type,
            )

            try:
                async with self.session.begin_nested():
                    created_doc = await self.document_repo.create(document)
            except IntegrityError as e:
                pgcode = getattr(e.orig, "pgcode", None)
                if pgcode != "23505":
                    raise
                return await self._handle_dedup_race(file_hash, owner_id, s3_key)

            job = ProcessingJob(
                document_id=created_doc.id,
                status=EJobStatus.PENDING,
                progress=0,
            )
            created_job = await self.job_repo.create(job)

            await self.session.commit()
            await self._trigger_pipeline(created_doc.id)

            return TUploadResponse(
                document=created_doc,
                job=created_job,
            )

        except Exception as e:
            logger.error(
                "Upload failed for file %s. S3 key: %s. Error: %s",
                file.filename,
                s3_key,
                str(e),
            )
            await self.session.rollback()
            await _cleanup_s3_file(self.storage_service, s3_key, "upload failure")

            raise

        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    async def get_all_summaries(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "-created_at",
        owner_id: uuid.UUID | None = None,
        search_query: str | None = None,
        file_types: list[EFileType] | None = None,
    ) -> TPaginatedSummariesResponse:
        doc_service = ContentDocumentService(self.session)
        return await doc_service.get_all_summaries(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            owner_id=owner_id,
            search_query=search_query,
            file_types=file_types,
        )

    async def get_summary(self, document_id: uuid.UUID) -> TSummaryRead | None:
        doc_service = ContentDocumentService(self.session)
        return await doc_service.get_summary(document_id)

    async def delete_document(self, document_id: uuid.UUID) -> None:
        doc_service = ContentDocumentService(self.session, self.storage_service)
        await doc_service.delete_document(document_id)


class ContentDocumentService:
    def __init__(
        self, session: AsyncSession, storage_service: StorageService | None = None
    ) -> None:
        self.session = session
        self.storage_service = storage_service
        self.document_repo = DocumentRepository(session)
        self.version_repo = DocumentVersionRepository(session)

    async def get_document(self, document_id: uuid.UUID) -> Document | None:
        return await self.document_repo.get_by_id(document_id)

    async def get_version(self, version_id: uuid.UUID) -> DocumentVersion | None:
        return await self.version_repo.get_by_id(version_id)

    async def get_versions_by_document_id(
        self, document_id: uuid.UUID, limit: int = 10, offset: int = 0
    ) -> tuple[list[DocumentVersion], int]:
        return await self.version_repo.get_all_by_document_id(
            document_id, limit, offset
        )

    async def get_latest_version(
        self, document_id: uuid.UUID
    ) -> DocumentVersion | None:
        return await self.version_repo.get_latest_by_document_id(document_id)

    async def create_version(self, version: DocumentVersion) -> DocumentVersion:
        return await self.version_repo.create(version)

    async def update_version(self, version: DocumentVersion) -> DocumentVersion:
        return await self.version_repo.update(version)

    async def delete_version(self, version: DocumentVersion) -> None:
        await self.session.delete(version)
        await self.session.flush()

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

        if not self.storage_service:
            raise ValueError("Storage service not configured")

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
