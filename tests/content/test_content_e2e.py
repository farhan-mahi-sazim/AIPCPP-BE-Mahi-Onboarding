import pytest
from httpx import AsyncClient
from tests.content.constants import (
    DUMMY_USER_ID,
    PDF_FILENAME,
    PDF_CONTENT,
    EXE_FILENAME,
    EXE_CONTENT,
    SUCCESS_STATUS,
    UNSUPPORTED_TYPE_ERROR,
)
from tests.content.helpers import ensure_user_exists


@pytest.mark.asyncio
class TestUploadEndpoint:
    async def test_upload_pdf_success(self, client: AsyncClient, db_session):
        await ensure_user_exists(db_session)

        files = {"file": (PDF_FILENAME, PDF_CONTENT, "application/pdf")}
        response = await client.post("/api/v1/content/upload", files=files)

        assert response.status_code == 201
        data = response.json()
        assert data["document"]["filename"] == PDF_FILENAME
        assert data["document"]["file_type"] == "pdf"
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
