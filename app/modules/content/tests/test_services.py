import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile

from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.enums.pipeline_stage import EPipelineStage
from app.common.sse_manager import SSEManager
from app.models.document import Document
from app.models.job import ProcessingJob
from app.modules.content.services import ContentService
from app.modules.content.tests.constants import (
    DUMMY_USER_ID,
    TEST_CONTENT,
    TEST_CONTENT_TYPE,
    TEST_FILENAME,
)
from app.modules.content.tests.helpers import ensure_user_exists


@pytest.mark.asyncio
class TestContentService:
    async def test_upload_document_success(self, db_session):
        await ensure_user_exists(db_session)

        mock_storage = MagicMock()
        mock_storage.upload_file.return_value = "s3_key"

        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = TEST_FILENAME
        mock_file.content_type = TEST_CONTENT_TYPE
        mock_file.read = AsyncMock(side_effect=[TEST_CONTENT, b""])
        mock_file.size = len(TEST_CONTENT)
        mock_file.file = MagicMock()
        mock_file.headers = {}

        service = ContentService(db_session, mock_storage)

        response = await service.upload_document(mock_file, owner_id=DUMMY_USER_ID)

        assert response.document.filename == TEST_FILENAME
        assert response.document.file_type == EFileType.PDF
        assert response.job.status == EJobStatus.PROCESSING

        mock_storage.upload_file.assert_called_once()

    async def test_upload_invalid_extension(self, db_session):
        await ensure_user_exists(db_session)

        mock_storage = MagicMock()
        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = "virus.exe"
        mock_file.content_type = "application/x-msdownload"
        mock_file.size = 100
        mock_file.read = AsyncMock(side_effect=[b"mock content", b""])
        mock_file.file = MagicMock()
        mock_file.headers = {}

        service = ContentService(db_session, mock_storage)

        with pytest.raises(ValueError, match="Unsupported file type"):
            await service.upload_document(mock_file, owner_id=DUMMY_USER_ID)

    async def test_upload_with_sse_manager(self, db_session):
        await ensure_user_exists(db_session)

        mock_storage = MagicMock()
        mock_storage.upload_file.return_value = "s3_key"

        mock_progress_manager = MagicMock(spec=SSEManager)

        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = TEST_FILENAME
        mock_file.content_type = TEST_CONTENT_TYPE
        mock_file.read = AsyncMock(side_effect=[TEST_CONTENT, b""])
        mock_file.size = len(TEST_CONTENT)
        mock_file.file = MagicMock()
        mock_file.headers = {}

        service = ContentService(db_session, mock_storage, mock_progress_manager)

        response = await service.upload_document(mock_file, owner_id=DUMMY_USER_ID)

        assert response.job is not None
        mock_storage.upload_file.assert_called_once()
        call_kwargs = mock_storage.upload_file.call_args.kwargs
        assert "progress_callback" in call_kwargs
        assert call_kwargs["progress_callback"] is not None

    async def test_stream_job_progress_uses_sse_manager(self, db_session, monkeypatch):
        await ensure_user_exists(db_session)

        mock_storage = MagicMock()
        local_manager = SSEManager()
        monkeypatch.setattr("app.modules.content.services.sse_manager", local_manager)
        monkeypatch.setattr(
            "app.modules.content.services.CacheConnectionManager.get_connection",
            AsyncMock(return_value=None),
        )

        document_id = uuid.uuid4()
        document = Document(
            id=document_id,
            owner_id=DUMMY_USER_ID,
            filename=TEST_FILENAME,
            s3_key=f"{DUMMY_USER_ID}/{document_id}.pdf",
            file_type=EFileType.PDF,
        )
        db_session.add(document)

        job = ProcessingJob(
            document_id=document_id,
            status=EJobStatus.PROCESSING,
            progress=12,
            stage=EPipelineStage.EXTRACTION,
        )
        db_session.add(job)
        await db_session.commit()

        service = ContentService(db_session, mock_storage)
        stream = service.stream_job_progress(document_id)

        first_payload = json.loads((await stream.__anext__()).removeprefix("data: "))
        assert first_payload["status"] == EJobStatus.PROCESSING.value
        assert first_payload["stage"] == EPipelineStage.EXTRACTION.value

        await local_manager.publish(
            str(document_id),
            progress=100,
            stage=EPipelineStage.PERSISTENCE.value,
            status=EJobStatus.COMPLETED.value,
        )

        final_payload = json.loads((await stream.__anext__()).removeprefix("data: "))
        assert final_payload["status"] == EJobStatus.COMPLETED.value
        assert final_payload["progress"] == 100

        with pytest.raises(StopAsyncIteration):
            await stream.__anext__()
