import logging
from uuid import UUID

import litellm
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.modules.search.constants import (
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_SEARCH_OFFSET,
    MAX_SEARCH_LIMIT,
    SearchError,
)
from app.modules.search.repositories import SearchRepository
from app.modules.search.schemas import TSearchResponse, TSearchResult

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.search_repo = SearchRepository(session)

    async def _generate_query_embedding(self, query: str) -> list[float]:
        """Generate embedding for the search query using LiteLLM."""
        try:
            response = litellm.embedding(
                model=settings.LITELLM_EMBEDDING_MODEL,
                input=query,
                timeout=settings.MODEL_EMBEDDING_TIMEOUT_SECONDS,
            )
            embeddings = [r["embedding"] for r in response.data]
            return embeddings[0]
        except Exception as e:
            logger.error("Failed to generate query embedding: %s", str(e))
            raise ValueError(SearchError.EMBEDDING_FAILED)

    async def search(
        self,
        query: str,
        owner_id: UUID | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        offset: int = DEFAULT_SEARCH_OFFSET,
    ) -> TSearchResponse:
        """
        Perform semantic search across document chunks.

        Args:
            query: The search query text
            owner_id: Filter by owner (optional)
            limit: Maximum results to return
            offset: Number of results to skip

        Returns:
            TSearchResponse with ranked results
        """
        if not query or not query.strip():
            raise ValueError(SearchError.EMPTY_QUERY)

        if limit < 1 or limit > MAX_SEARCH_LIMIT:
            raise ValueError(SearchError.INVALID_LIMIT)

        if offset < 0:
            offset = DEFAULT_SEARCH_OFFSET

        query_embedding = await self._generate_query_embedding(query)

        results, total = await self.search_repo.semantic_search(
            query_embedding=query_embedding,
            owner_id=owner_id,
            limit=limit,
            offset=offset,
        )

        search_results = [
            TSearchResult(
                document_id=r["document_id"],
                filename=r["filename"],
                file_type=r["file_type"],
                chunk_content=r["chunk_content"],
                chunk_index=r["chunk_index"],
                similarity_score=r["similarity_score"],
                summary=r["summary"],
                created_at=r["created_at"],
            )
            for r in results
        ]

        return TSearchResponse(
            results=search_results,
            total=total,
            query=query,
            limit=limit,
            offset=offset,
        )
