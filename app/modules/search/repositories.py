from uuid import UUID

from sqlalchemy import bindparam, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk, DocumentVersion
from app.modules.search.constants import DEFAULT_SEARCH_LIMIT, DEFAULT_SEARCH_OFFSET


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def semantic_search(
        self,
        query_embedding: list[float],
        owner_id: UUID | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        offset: int = DEFAULT_SEARCH_OFFSET,
    ) -> tuple[list[dict], int]:
        """
        Perform semantic search using cosine similarity with pgvector.

        Args:
            query_embedding: The embedding vector for the search query
            owner_id: Filter results by owner (optional)
            limit: Maximum number of results to return
            offset: Number of results to skip

        Returns:
            Tuple of (search results as dicts, total count)
        """
        query_embedding_param = bindparam(
            "query_embedding", value=query_embedding, type_=DocumentChunk.embedding.type
        )
        cosine_similarity = 1 - DocumentChunk.embedding.cosine_distance(
            query_embedding_param
        )

        base_stmt = (
            select(
                DocumentChunk,
                Document,
                DocumentVersion,
                cosine_similarity.label("similarity"),
            )
            .join(Document, DocumentChunk.document_id == Document.id)
            .join(
                DocumentVersion,
                Document.current_version_id == DocumentVersion.id,
                isouter=True,
            )
            .where(DocumentChunk.embedding.isnot(None))
        )

        if owner_id:
            base_stmt = base_stmt.where(Document.owner_id == owner_id)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        search_stmt = base_stmt.order_by(desc("similarity")).offset(offset).limit(limit)

        result = await self.session.execute(search_stmt)
        rows = result.all()

        results = []
        for chunk, doc, version, similarity in rows:
            results.append(
                {
                    "document_id": doc.id,
                    "filename": doc.filename,
                    "file_type": doc.file_type.value if doc.file_type else None,
                    "chunk_content": chunk.content,
                    "chunk_index": chunk.chunk_index,
                    "similarity_score": float(similarity),
                    "summary": version.data.get("summary") if version else None,
                    "created_at": doc.created_at,
                }
            )

        return results, total
