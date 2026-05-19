import uuid

import pytest
from httpx import AsyncClient
from sqlmodel import select

from app.models.document import Document
from tests.content.constants import (
    EXE_CONTENT,
    EXE_FILENAME,
    PDF_CONTENT,
    PDF_FILENAME,
    SUCCESS_STATUS,
    SUMMARY_NOT_FOUND_ERROR,
    UNSUPPORTED_TYPE_ERROR,
)
from tests.content.helpers import (
    create_document_with_summary,
    create_document_without_summary,
    ensure_user_exists,
)


@pytest.mark.asyncio
class TestUploadEndpoint:
    async def test_upload_pdf_success(self, client: AsyncClient, db_session):
        await ensure_user_exists(db_session)

        files = {"file": (PDF_FILENAME, PDF_CONTENT, "application/pdf")}
        response = await client.post("/api/v1/content/upload", files=files)

        assert response.status_code == 201
        data = response.json()
        assert data["document"]["filename"] == PDF_FILENAME
        assert data["document"]["file_type"] == "PDF"
        assert data["job"]["status"] == SUCCESS_STATUS

    async def test_upload_unsupported_type(self, client: AsyncClient, db_session):
        await ensure_user_exists(db_session)

        files = {"file": (EXE_FILENAME, EXE_CONTENT, "application/octet-stream")}
        response = await client.post("/api/v1/content/upload", files=files)

        assert response.status_code == 400
        assert UNSUPPORTED_TYPE_ERROR in response.json()["detail"]

    async def test_upload_missing_file(self, client: AsyncClient):
        response = await client.post("/api/v1/content/upload")
        assert response.status_code == 422


@pytest.mark.asyncio
class TestGetSummariesEndpoint:
    """Test GET /summaries endpoint - retrieve all summaries."""

    async def test_get_summaries_success(self, client: AsyncClient, db_session):
        """Should return all documents with their summaries."""
        await ensure_user_exists(db_session)

        # Create test documents with summaries
        doc1, _ = await create_document_with_summary(
            db_session,
            filename="doc1.pdf",
            summary_text="First summary",
            tags=["important", "reviewed"],
        )
        doc2, _ = await create_document_with_summary(
            db_session,
            filename="doc2.txt",
            summary_text="Second summary",
            tags=["urgent"],
        )

        response = await client.get("/api/v1/content/summaries")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["data"]) == 2
        assert data["data"][0]["filename"] == doc2.filename  # Most recent first
        assert data["data"][0]["summary"] == "Second summary"
        assert data["data"][0]["tags"] == ["urgent"]
        assert data["data"][1]["filename"] == doc1.filename
        assert data["data"][1]["summary"] == "First summary"
        assert data["data"][1]["tags"] == ["important", "reviewed"]

    async def test_get_summaries_empty(self, client: AsyncClient, db_session):
        """Should return empty list when no summaries exist."""
        await ensure_user_exists(db_session)

        response = await client.get("/api/v1/content/summaries")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["data"] == []

    async def test_get_summaries_with_documents_without_summaries(
        self, client: AsyncClient, db_session
    ):
        """Should include documents without summaries (summary=None)."""
        await ensure_user_exists(db_session)

        doc_with_summary, _ = await create_document_with_summary(
            db_session, filename="with_summary.pdf"
        )
        _doc_without_summary = await create_document_without_summary(
            db_session, filename="without_summary.txt"
        )

        response = await client.get("/api/v1/content/summaries")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["data"]) == 2
        # Find the one without summary
        item_without = next(
            (
                item
                for item in data["data"]
                if item["filename"] == "without_summary.txt"
            ),
            None,
        )
        assert item_without is not None
        assert item_without["summary"] is None
        assert item_without["tags"] == []


@pytest.mark.asyncio
class TestGetSummaryByIdEndpoint:
    """Test GET /summaries/{document_id} endpoint - retrieve single summary by ID."""

    async def test_get_summary_success(self, client: AsyncClient, db_session):
        """Should return summary for existing document with summary."""
        await ensure_user_exists(db_session)

        doc, version = await create_document_with_summary(
            db_session,
            filename="my_summary.pdf",
            summary_text="Detailed summary content",
            tags=["priority", "completed"],
        )

        response = await client.get(f"/api/v1/content/summaries/{doc.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == str(doc.id)
        assert data["filename"] == "my_summary.pdf"
        assert data["summary"] == "Detailed summary content"
        assert set(data["tags"]) == {"priority", "completed"}
        assert data["created_at"] is not None

    async def test_get_summary_not_found(self, client: AsyncClient, db_session):
        """Should return 404 when document doesn't exist."""
        await ensure_user_exists(db_session)

        non_existent_id = uuid.uuid4()
        response = await client.get(f"/api/v1/content/summaries/{non_existent_id}")

        assert response.status_code == 404
        assert SUMMARY_NOT_FOUND_ERROR in response.json()["detail"]

    async def test_get_summary_without_summary_data(
        self, client: AsyncClient, db_session
    ):
        """Should return document with null summary if no version exists."""
        await ensure_user_exists(db_session)

        doc = await create_document_without_summary(
            db_session, filename="pending_summary.pdf"
        )

        response = await client.get(f"/api/v1/content/summaries/{doc.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == str(doc.id)
        assert data["filename"] == "pending_summary.pdf"
        assert data["summary"] is None
        assert data["tags"] == []

    async def test_get_summary_invalid_uuid(self, client: AsyncClient, db_session):
        """Should return 422 for invalid UUID format."""
        await ensure_user_exists(db_session)

        response = await client.get("/api/v1/content/summaries/invalid-uuid")

        assert response.status_code == 422


@pytest.mark.asyncio
class TestDeleteDocumentEndpoint:
    """Test DELETE /summaries/{document_id} endpoint - delete a document."""

    async def test_delete_document_success(self, client: AsyncClient, db_session):
        """Should delete document and return 204."""
        await ensure_user_exists(db_session)

        doc, _ = await create_document_with_summary(
            db_session, filename="to_delete.pdf"
        )
        doc_id = doc.id

        # Verify document exists
        response = await client.get(f"/api/v1/content/summaries/{doc_id}")
        assert response.status_code == 200

        # Delete document
        response = await client.delete(f"/api/v1/content/{doc_id}")
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]

        # Verify document is deleted
        response = await client.get(f"/api/v1/content/summaries/{doc_id}")
        assert response.status_code == 404

        # Verify deletion from database
        result = await db_session.execute(select(Document).where(Document.id == doc_id))
        assert result.scalar_one_or_none() is None

    async def test_delete_document_not_found(self, client: AsyncClient, db_session):
        """Should return 404 when trying to delete non-existent document."""
        await ensure_user_exists(db_session)

        non_existent_id = uuid.uuid4()
        response = await client.delete(f"/api/v1/content/{non_existent_id}")

        assert response.status_code == 404
        detail = response.json()["detail"]
        assert "not found" in detail.lower()

    async def test_delete_document_without_summary(
        self, client: AsyncClient, db_session
    ):
        """Should delete document even if no summary exists."""
        await ensure_user_exists(db_session)

        doc = await create_document_without_summary(
            db_session, filename="delete_no_summary.txt"
        )
        doc_id = doc.id

        response = await client.delete(f"/api/v1/content/{doc_id}")
        assert response.status_code == 200

        # Verify deletion
        result = await db_session.execute(select(Document).where(Document.id == doc_id))
        assert result.scalar_one_or_none() is None

    async def test_delete_document_invalid_uuid(self, client: AsyncClient, db_session):
        """Should return 422 for invalid UUID format."""
        await ensure_user_exists(db_session)

        response = await client.delete("/api/v1/content/invalid-uuid")

        assert response.status_code == 422

    async def test_delete_document_twice(self, client: AsyncClient, db_session):
        """Should return 404 on second delete attempt."""
        await ensure_user_exists(db_session)

        doc, _ = await create_document_with_summary(
            db_session, filename="delete_twice.pdf"
        )
        doc_id = doc.id

        # First delete
        response = await client.delete(f"/api/v1/content/{doc_id}")
        assert response.status_code == 200

        # Second delete (should fail)
        response = await client.delete(f"/api/v1/content/{doc_id}")
        assert response.status_code == 404
