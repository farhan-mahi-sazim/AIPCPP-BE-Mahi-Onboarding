import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.enums.pipeline_stage import EPipelineStage
from app.common.enums.version_source import EVersionSource
from app.models.document import Document, DocumentChunk, DocumentVersion
from app.models.job import ProcessingJob
from app.modules.processing.services import ProcessingService
from app.modules.processing.tests.constants import (
    MOCK_AI_RESPONSE,
    MOCK_DOCUMENT_ID,
    MOCK_EMBEDDING,
    MOCK_USER_ID,
    TEST_RAW_TEXT,
)
from app.modules.processing.tests.helpers import ensure_user_exists_sync


class TestProcessingService:
    @pytest.fixture
    def service(self, sync_db_session):
        ensure_user_exists_sync(sync_db_session)
        with patch("app.modules.processing.services.StorageService") as mock_storage:
            svc = ProcessingService(sync_db_session)
            svc.mock_storage = mock_storage.return_value
            yield svc

    @patch("app.modules.processing.services.PdfReader")
    def test_process_extraction_pdf_success(
        self, mock_pdf_reader, service, sync_db_session
    ):
        service.mock_storage.get_file_content.return_value = b"fake pdf content"

        mock_reader = mock_pdf_reader.return_value
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Extracted Text from PDF"
        mock_reader.pages = [mock_page]

        doc = Document(
            id=MOCK_DOCUMENT_ID,
            owner_id=MOCK_USER_ID,
            filename="test.pdf",
            file_type=EFileType.PDF,
            s3_key="key/test.pdf",
        )
        sync_db_session.add(doc)

        job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=MOCK_DOCUMENT_ID,
            status=EJobStatus.PENDING,
            stage=EPipelineStage.EXTRACTION,
        )
        sync_db_session.add(job)
        sync_db_session.commit()

        result = service.process_extraction(MOCK_DOCUMENT_ID)

        assert result == str(MOCK_DOCUMENT_ID)
        sync_db_session.refresh(doc)
        assert "Extracted Text from PDF" in doc.raw_text
        sync_db_session.refresh(job)
        assert job.status == EJobStatus.PROCESSING

    @patch("app.modules.processing.services.litellm.completion")
    def test_process_ai_analysis_success(
        self, mock_completion, service, sync_db_session
    ):
        mock_completion.return_value = self._make_mock_response(MOCK_AI_RESPONSE)

        doc = Document(
            id=MOCK_DOCUMENT_ID,
            owner_id=MOCK_USER_ID,
            filename="test.pdf",
            file_type=EFileType.PDF,
            s3_key="key/test.pdf",
            raw_text=TEST_RAW_TEXT,
        )
        sync_db_session.add(doc)

        job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=MOCK_DOCUMENT_ID,
            status=EJobStatus.PROCESSING,
            stage=EPipelineStage.AI_TASK,
        )
        sync_db_session.add(job)
        sync_db_session.commit()

        result = service.process_ai_analysis(MOCK_DOCUMENT_ID)

        assert result == str(MOCK_DOCUMENT_ID)
        sync_db_session.refresh(doc)
        assert doc.current_version_id is not None

        version = sync_db_session.get(DocumentVersion, doc.current_version_id)
        assert version is not None
        assert version.data["summary"] == MOCK_AI_RESPONSE["summary"]
        assert version.data["tags"] == MOCK_AI_RESPONSE["tags"]

    @patch("app.modules.processing.services.litellm.completion")
    def test_process_ai_analysis_fallback_success(
        self, mock_completion, service, sync_db_session
    ):
        mock_completion.side_effect = [
            Exception("Primary model failed"),
            self._make_mock_response(MOCK_AI_RESPONSE),
        ]

        doc = Document(
            id=MOCK_DOCUMENT_ID,
            owner_id=MOCK_USER_ID,
            filename="test.pdf",
            file_type=EFileType.PDF,
            s3_key="key/test.pdf",
            raw_text=TEST_RAW_TEXT,
        )
        sync_db_session.add(doc)

        job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=MOCK_DOCUMENT_ID,
            status=EJobStatus.PROCESSING,
            stage=EPipelineStage.AI_TASK,
        )
        sync_db_session.add(job)
        sync_db_session.commit()

        result = service.process_ai_analysis(MOCK_DOCUMENT_ID)

        assert result == str(MOCK_DOCUMENT_ID)
        sync_db_session.refresh(doc)
        assert doc.current_version_id is not None
        version = sync_db_session.get(DocumentVersion, doc.current_version_id)
        assert version.data["summary"] == MOCK_AI_RESPONSE["summary"]
        assert mock_completion.call_count == 2

    @patch("app.modules.processing.services.litellm.completion")
    def test_process_ai_analysis_all_models_fail(
        self, mock_completion, service, sync_db_session
    ):
        mock_completion.side_effect = [
            Exception("Primary model failed"),
            Exception("Fallback model 1 failed"),
            Exception("Fallback model 2 failed"),
        ]

        doc = Document(
            id=MOCK_DOCUMENT_ID,
            owner_id=MOCK_USER_ID,
            filename="test.pdf",
            file_type=EFileType.PDF,
            s3_key="key/test.pdf",
            raw_text=TEST_RAW_TEXT,
        )
        sync_db_session.add(doc)

        job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=MOCK_DOCUMENT_ID,
            status=EJobStatus.PROCESSING,
            stage=EPipelineStage.AI_TASK,
        )
        sync_db_session.add(job)
        sync_db_session.commit()

        with pytest.raises(Exception, match="Fallback model 2 failed"):
            service.process_ai_analysis(MOCK_DOCUMENT_ID)

        assert mock_completion.call_count == 3

    @staticmethod
    def _make_mock_response(ai_response: dict) -> MagicMock:
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps(ai_response)))
        ]
        mock_response.usage.to_dict.return_value = {
            "prompt_tokens": 10,
            "completion_tokens": 20,
        }
        return mock_response

    @patch("app.modules.processing.services.litellm.embedding")
    def test_process_embeddings_success(self, mock_embedding, service, sync_db_session):
        mock_embedding.return_value = MagicMock(data=[{"embedding": MOCK_EMBEDDING}])

        doc = Document(
            id=MOCK_DOCUMENT_ID,
            owner_id=MOCK_USER_ID,
            filename="test.pdf",
            file_type=EFileType.PDF,
            s3_key="key/test.pdf",
            raw_text=TEST_RAW_TEXT,
        )
        sync_db_session.add(doc)
        sync_db_session.commit()

        result = service.process_embeddings(MOCK_DOCUMENT_ID)

        assert result == str(MOCK_DOCUMENT_ID)
        chunks = (
            sync_db_session.query(DocumentChunk)
            .filter_by(document_id=MOCK_DOCUMENT_ID)
            .all()
        )
        assert len(chunks) > 0
        assert list(chunks[0].embedding) == MOCK_EMBEDDING

    def test_validate_and_finalize_job_success(self, service, sync_db_session):
        doc = Document(
            id=MOCK_DOCUMENT_ID,
            owner_id=MOCK_USER_ID,
            filename="test.pdf",
            file_type=EFileType.PDF,
            s3_key="key/test.pdf",
            raw_text=TEST_RAW_TEXT,
        )
        sync_db_session.add(doc)

        job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=MOCK_DOCUMENT_ID,
            status=EJobStatus.PROCESSING,
            stage=EPipelineStage.EMBEDDING,
        )
        sync_db_session.add(job)

        version = DocumentVersion(
            document_id=MOCK_DOCUMENT_ID,
            version_number=1,
            data={"summary": "Summary", "tags": ["test"]},
            source=EVersionSource.AI,
        )
        sync_db_session.add(version)
        sync_db_session.flush()
        doc.current_version_id = version.id

        chunk = DocumentChunk(
            document_id=MOCK_DOCUMENT_ID,
            content="chunk",
            embedding=MOCK_EMBEDDING,
            chunk_index=0,
        )
        sync_db_session.add(chunk)
        sync_db_session.commit()

        service.validate_and_finalize_job(MOCK_DOCUMENT_ID)

        sync_db_session.refresh(job)
        assert job.status == EJobStatus.COMPLETED
        assert job.stage == EPipelineStage.PERSISTENCE
