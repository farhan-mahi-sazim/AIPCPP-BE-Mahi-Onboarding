from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.models.user import User
from app.modules.search.services import SearchService
from app.modules.search.tests.constants import (
    DUMMY_USER_ID,
    MOCK_DOCUMENT_ID,
    MOCK_DOCUMENT_ID_2,
    MOCK_EMBEDDING_RESPONSE_DATA,
    TEST_QUERY,
)
from app.modules.search.tests.helpers import (
    create_document_with_chunks,
    ensure_user_exists,
)


@pytest.mark.asyncio
class TestSearchService:
    async def test_search_success(self, db_session):
        await ensure_user_exists(db_session)

        chunks_content = [
            "This is an invoice for payment terms and conditions",
            "The payment should be made within 30 days",
            "Product description and pricing details",
        ]
        embeddings = [
            [0.1] * 3072,
            [0.2] * 3072,
            [0.3] * 3072,
        ]
        await create_document_with_chunks(
            db_session,
            owner_id=DUMMY_USER_ID,
            document_id=MOCK_DOCUMENT_ID,
            filename="invoice.pdf",
            chunks_content=chunks_content,
            embeddings=embeddings,
        )

        with patch("app.modules.search.services.litellm.embedding") as mock_embedding:
            mock_embedding.return_value = MagicMock(data=MOCK_EMBEDDING_RESPONSE_DATA)

            service = SearchService(db_session)
            response = await service.search(
                query=TEST_QUERY,
                owner_id=DUMMY_USER_ID,
                limit=10,
                offset=0,
            )

            assert response.total == 1
            assert len(response.results) == 1
            assert response.results[0].document_id == MOCK_DOCUMENT_ID
            assert response.results[0].filename == "invoice.pdf"

    async def test_search_empty_results(self, db_session):
        await ensure_user_exists(db_session)

        with patch("app.modules.search.services.litellm.embedding") as mock_embedding:
            mock_embedding.return_value = MagicMock(data=MOCK_EMBEDDING_RESPONSE_DATA)

            service = SearchService(db_session)
            response = await service.search(
                query="nonexistent search term",
                owner_id=DUMMY_USER_ID,
                limit=10,
                offset=0,
            )

            assert response.total == 0
            assert len(response.results) == 0

    async def test_search_empty_query_raises_error(self, db_session):
        await ensure_user_exists(db_session)

        service = SearchService(db_session)

        with pytest.raises(ValueError, match="Search query cannot be empty"):
            await service.search(
                query="",
                owner_id=DUMMY_USER_ID,
                limit=10,
                offset=0,
            )

    async def test_search_whitespace_query_raises_error(self, db_session):
        await ensure_user_exists(db_session)

        service = SearchService(db_session)

        with pytest.raises(ValueError, match="Search query cannot be empty"):
            await service.search(
                query="   ",
                owner_id=DUMMY_USER_ID,
                limit=10,
                offset=0,
            )

    async def test_search_invalid_limit_raises_error(self, db_session):
        await ensure_user_exists(db_session)

        service = SearchService(db_session)

        with pytest.raises(ValueError, match="Limit must be between"):
            await service.search(
                query=TEST_QUERY,
                owner_id=DUMMY_USER_ID,
                limit=0,
                offset=0,
            )

    async def test_search_limit_exceeds_max_raises_error(self, db_session):
        await ensure_user_exists(db_session)

        service = SearchService(db_session)

        with pytest.raises(ValueError, match="Limit must be between"):
            await service.search(
                query=TEST_QUERY,
                owner_id=DUMMY_USER_ID,
                limit=200,
                offset=0,
            )

    async def test_search_embedding_failure_raises_error(self, db_session):
        await ensure_user_exists(db_session)

        service = SearchService(db_session)

        with patch("app.modules.search.services.litellm.embedding") as mock_embedding:
            mock_embedding.side_effect = Exception("API Error")

            with pytest.raises(ValueError, match="Failed to generate embedding"):
                await service.search(
                    query=TEST_QUERY,
                    owner_id=DUMMY_USER_ID,
                    limit=10,
                    offset=0,
                )

    async def test_search_multiple_documents(self, db_session):
        await ensure_user_exists(db_session)

        chunks_content_1 = ["Invoice payment terms and conditions"]
        chunks_content_2 = ["Contract agreement terms"]

        await create_document_with_chunks(
            db_session,
            owner_id=DUMMY_USER_ID,
            document_id=MOCK_DOCUMENT_ID,
            filename="invoice.pdf",
            chunks_content=chunks_content_1,
            embeddings=[[0.9] * 3072],
        )

        await create_document_with_chunks(
            db_session,
            owner_id=DUMMY_USER_ID,
            document_id=MOCK_DOCUMENT_ID_2,
            filename="contract.pdf",
            chunks_content=chunks_content_2,
            embeddings=[[0.1] * 3072],
        )

        with patch("app.modules.search.services.litellm.embedding") as mock_embedding:
            mock_embedding.return_value = MagicMock(data=[{"embedding": [0.85] * 3072}])

            service = SearchService(db_session)
            response = await service.search(
                query="invoice payment",
                owner_id=DUMMY_USER_ID,
                limit=10,
                offset=0,
            )

            assert response.total == 2
            assert len(response.results) == 2

    async def test_search_pagination(self, db_session):
        await ensure_user_exists(db_session)

        chunks = [f"Document chunk {i} with content" for i in range(10)]
        embeddings = [[float(i) / 10] * 3072 for i in range(10)]

        await create_document_with_chunks(
            db_session,
            owner_id=DUMMY_USER_ID,
            document_id=MOCK_DOCUMENT_ID,
            filename="test.pdf",
            chunks_content=chunks,
            embeddings=embeddings,
        )

        with patch("app.modules.search.services.litellm.embedding") as mock_embedding:
            mock_embedding.return_value = MagicMock(data=MOCK_EMBEDDING_RESPONSE_DATA)

            service = SearchService(db_session)
            response = await service.search(
                query=TEST_QUERY,
                owner_id=DUMMY_USER_ID,
                limit=5,
                offset=5,
            )

            assert response.total == 1
            assert len(response.results) == 1
            assert response.limit == 5
            assert response.offset == 5

    async def test_search_filters_by_owner(self, db_session):
        await ensure_user_exists(db_session)

        other_user_id = uuid4()
        other_user = User(
            id=other_user_id,
            email="other@example.com",
            hashed_password="hashed-password",
            full_name="Other User",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.commit()

        await create_document_with_chunks(
            db_session,
            owner_id=other_user_id,
            document_id=MOCK_DOCUMENT_ID,
            filename="other_user_doc.pdf",
            chunks_content=["This is another user's document"],
            embeddings=[[0.5] * 3072],
        )

        with patch("app.modules.search.services.litellm.embedding") as mock_embedding:
            mock_embedding.return_value = MagicMock(data=MOCK_EMBEDDING_RESPONSE_DATA)

            service = SearchService(db_session)
            response = await service.search(
                query=TEST_QUERY,
                owner_id=DUMMY_USER_ID,
                limit=10,
                offset=0,
            )

            assert response.total == 0
            assert len(response.results) == 0
