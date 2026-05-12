from unittest.mock import MagicMock, patch

from app.modules.processing.tasks import (
    analyze_content_task,
    extract_text_task,
    generate_embeddings_task,
    validate_and_finalize_job_task,
)
from app.modules.processing.tests.constants import MOCK_DOCUMENT_ID


class TestProcessingTasks:
    @patch("app.modules.processing.tasks.ProcessingService")
    @patch("app.modules.processing.tasks.SyncSessionLocal")
    def test_extract_text_task_success(self, mock_session_local, mock_service_class):
        # Setup
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        mock_service = mock_service_class.return_value
        mock_service.process_extraction.return_value = str(MOCK_DOCUMENT_ID)

        # Execute
        result = extract_text_task(str(MOCK_DOCUMENT_ID))

        # Assert
        assert result == str(MOCK_DOCUMENT_ID)
        mock_service.process_extraction.assert_called_once_with(MOCK_DOCUMENT_ID)

    @patch("app.modules.processing.tasks.ProcessingService")
    @patch("app.modules.processing.tasks.SyncSessionLocal")
    def test_analyze_content_task_success(self, mock_session_local, mock_service_class):
        # Setup
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        mock_service = mock_service_class.return_value
        mock_service.process_ai_analysis.return_value = str(MOCK_DOCUMENT_ID)

        # Execute
        result = analyze_content_task(str(MOCK_DOCUMENT_ID))

        # Assert
        assert result == str(MOCK_DOCUMENT_ID)
        mock_service.process_ai_analysis.assert_called_once_with(MOCK_DOCUMENT_ID)

    @patch("app.modules.processing.tasks.ProcessingService")
    @patch("app.modules.processing.tasks.SyncSessionLocal")
    def test_generate_embeddings_task_success(
        self, mock_session_local, mock_service_class
    ):
        # Setup
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        mock_service = mock_service_class.return_value
        mock_service.process_embeddings.return_value = str(MOCK_DOCUMENT_ID)

        # Execute
        result = generate_embeddings_task(str(MOCK_DOCUMENT_ID))

        # Assert
        assert result == str(MOCK_DOCUMENT_ID)
        mock_service.process_embeddings.assert_called_once_with(MOCK_DOCUMENT_ID)

    @patch("app.modules.processing.tasks.ProcessingService")
    @patch("app.modules.processing.tasks.SyncSessionLocal")
    def test_validate_and_finalize_job_task_success(
        self, mock_session_local, mock_service_class
    ):
        # Setup
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        mock_service = mock_service_class.return_value

        # Execute
        validate_and_finalize_job_task(document_id_str=str(MOCK_DOCUMENT_ID))

        # Assert
        mock_service.validate_and_finalize_job.assert_called_once_with(MOCK_DOCUMENT_ID)
