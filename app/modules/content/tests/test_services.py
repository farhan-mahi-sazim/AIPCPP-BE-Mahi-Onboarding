import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import UploadFile
from app.modules.content.services import ContentService
from app.modules.content.tests.constants import (
    DUMMY_USER_ID,
    TEST_FILENAME,
    TEST_CONTENT,
    TEST_CONTENT_TYPE,
)
from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus


@pytest.mark.asyncio
class TestContentService:
    @patch("app.modules.content.services.storage_service")
    @patch("app.modules.content.services.DocumentRepository")
    @patch("app.modules.content.services.ProcessingJobRepository")
    async def test_upload_document_success(
        self, MockJobRepo, MockDocRepo, mock_storage, db_session
    ):
        # Setup mocks
        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = TEST_FILENAME
        mock_file.content_type = TEST_CONTENT_TYPE
        mock_file.read.return_value = TEST_CONTENT

        doc_instance = MockDocRepo.return_value
        doc_instance.create = AsyncMock(side_effect=lambda x: x)

        job_instance = MockJobRepo.return_value
        job_instance.create = AsyncMock(side_effect=lambda x: x)

        service = ContentService(db_session)

        # Execute
        response = await service.upload_document(mock_file, owner_id=DUMMY_USER_ID)

        # Assertions
        assert response.document.filename == TEST_FILENAME
        assert response.document.file_type == EFileType.PDF
        assert response.job.status == EJobStatus.PENDING

        # Verify storage was called
        # Note: it's called via run_in_threadpool, so we verify the mock
        mock_storage.upload_file.assert_called_once()

        # Verify DB calls
        doc_instance.create.assert_called_once()
        job_instance.create.assert_called_once()

    @patch("app.modules.content.services.storage_service")
    async def test_upload_invalid_extension(self, mock_storage, db_session):
        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = "virus.exe"

        service = ContentService(db_session)

        with pytest.raises(ValueError, match="Unsupported file type"):
            await service.upload_document(mock_file, owner_id=DUMMY_USER_ID)
