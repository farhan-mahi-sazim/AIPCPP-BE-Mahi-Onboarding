import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.enums.pipeline_stage import EPipelineStage
from app.common.enums.version_source import EVersionSource
from app.models.document import Document
from app.models.job import ProcessingJob
from app.modules.processing.services import ProcessingService
from app.modules.processing.tests.constants import (
    MOCK_AI_RESPONSE,
    MOCK_DOCUMENT_ID,
    MOCK_EMBEDDING,
    MOCK_USER_ID,
    TEST_RAW_TEXT,
)
from app.modules.processing.tests.helpers import (
    ensure_user_exists_sync,
    get_sync_db_session,
)


class TestProcessingService:
    @pytest.fixture
    def session(self):
        gen = get_sync_db_session()
        session = next(gen)

        # Ensure clean state before test
        from app.models.document import DocumentChunk, DocumentVersion

        session.query(DocumentChunk).delete()
        session.query(DocumentVersion).delete()
        session.query(ProcessingJob).delete()
        session.query(Document).delete()
        session.commit()

        ensure_user_exists_sync(session)

        try:
            yield session
        finally:
            # Cleanup after test
            session.query(DocumentChunk).delete()
            session.query(DocumentVersion).delete()
            session.query(ProcessingJob).delete()
            session.query(Document).delete()
            session.commit()
            session.close()

    @pytest.fixture
    def service(self, session):
        with patch("app.modules.processing.services.StorageService") as mock_storage:
            svc = ProcessingService(session)
            svc.mock_storage = mock_storage.return_value
            yield svc

    @patch("app.modules.processing.services.PdfReader")
    def test_process_extraction_pdf_success(self, mock_pdf_reader, service, session):
        # Setup
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
        session.add(doc)

        job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=MOCK_DOCUMENT_ID,
            status=EJobStatus.PENDING,
            stage=EPipelineStage.EXTRACTION,
        )
        session.add(job)
        session.commit()

        # Execute
        result = service.process_extraction(MOCK_DOCUMENT_ID)

        # Assert
        assert result == str(MOCK_DOCUMENT_ID)
        session.refresh(doc)
        assert "Extracted Text from PDF" in doc.raw_text
        session.refresh(job)
        assert job.status == EJobStatus.PROCESSING

    @patch("app.modules.processing.services.litellm.completion")
    def test_process_ai_analysis_success(self, mock_completion, service, session):
        # Setup
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps(MOCK_AI_RESPONSE)))
        ]
        mock_response.usage.to_dict.return_value = {
            "prompt_tokens": 10,
            "completion_tokens": 20,
        }
        mock_completion.return_value = mock_response

        doc = Document(
            id=MOCK_DOCUMENT_ID,
            owner_id=MOCK_USER_ID,
            filename="test.pdf",
            file_type=EFileType.PDF,
            s3_key="key/test.pdf",
            raw_text=TEST_RAW_TEXT,
        )
        session.add(doc)

        job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=MOCK_DOCUMENT_ID,
            status=EJobStatus.PROCESSING,
            stage=EPipelineStage.AI_TASK,
        )
        session.add(job)
        session.commit()

        # Execute
        result = service.process_ai_analysis(MOCK_DOCUMENT_ID)

        # Assert
        assert result == str(MOCK_DOCUMENT_ID)
        session.refresh(doc)
        assert doc.current_version_id is not None

        from app.models.document import DocumentVersion

        version = session.get(DocumentVersion, doc.current_version_id)
        assert version is not None
        assert version.data["summary"] == MOCK_AI_RESPONSE["summary"]
        assert version.data["tags"] == MOCK_AI_RESPONSE["tags"]

    @patch("app.modules.processing.services.litellm.embedding")
    def test_process_embeddings_success(self, mock_embedding, service, session):
        # Setup
        mock_embedding.return_value = MagicMock(data=[{"embedding": MOCK_EMBEDDING}])

        doc = Document(
            id=MOCK_DOCUMENT_ID,
            owner_id=MOCK_USER_ID,
            filename="test.pdf",
            file_type=EFileType.PDF,
            s3_key="key/test.pdf",
            raw_text=TEST_RAW_TEXT,
        )
        session.add(doc)
        session.commit()

        # Execute
        result = service.process_embeddings(MOCK_DOCUMENT_ID)

        # Assert
        assert result == str(MOCK_DOCUMENT_ID)
        # Check if chunks are created
        from app.models.document import DocumentChunk

        chunks = (
            session.query(DocumentChunk).filter_by(document_id=MOCK_DOCUMENT_ID).all()
        )
        assert len(chunks) > 0
        # Compare as lists to avoid truth value ambiguity with numpy/pgvector arrays
        assert list(chunks[0].embedding) == MOCK_EMBEDDING

    def test_validate_and_finalize_job_success(self, service, session):
        # Setup
        doc = Document(
            id=MOCK_DOCUMENT_ID,
            owner_id=MOCK_USER_ID,
            filename="test.pdf",
            file_type=EFileType.PDF,
            s3_key="key/test.pdf",
            raw_text=TEST_RAW_TEXT,
        )
        session.add(doc)

        job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=MOCK_DOCUMENT_ID,
            status=EJobStatus.PROCESSING,
            stage=EPipelineStage.EMBEDDING,
        )
        session.add(job)
        session.commit()

        # We need to simulate that AI analysis is done by creating a version
        from app.models.document import DocumentVersion

        version = DocumentVersion(
            document_id=MOCK_DOCUMENT_ID,
            version_number=1,
            data={"summary": "Summary", "tags": ["test"]},
            source=EVersionSource.AI,
        )
        session.add(version)
        session.flush()
        doc.current_version_id = version.id

        # We need to simulate that embeddings are done by creating a chunk
        from app.models.document import DocumentChunk

        chunk = DocumentChunk(
            document_id=MOCK_DOCUMENT_ID,
            content="chunk",
            embedding=MOCK_EMBEDDING,
            chunk_index=0,
        )
        session.add(chunk)
        session.commit()

        service.validate_and_finalize_job(MOCK_DOCUMENT_ID)

        # Assert
        session.refresh(job)
        assert job.status == EJobStatus.COMPLETED
        assert job.stage == EPipelineStage.PERSISTENCE
