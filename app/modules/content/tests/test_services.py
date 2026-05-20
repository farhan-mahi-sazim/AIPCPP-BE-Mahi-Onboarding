from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile

from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.sse_manager import SSEManager
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
        mock_file.read.return_value = TEST_CONTENT
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
        mock_file.read.return_value = b"mock content"
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
        mock_file.read.return_value = TEST_CONTENT
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
