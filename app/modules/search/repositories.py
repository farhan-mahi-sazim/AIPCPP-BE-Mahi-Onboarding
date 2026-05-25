import re
from uuid import UUID

from sqlalchemy import bindparam, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk, DocumentVersion
from app.modules.search.constants import (
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_SEARCH_OFFSET,
)


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_document_chunks(
        self,
        document_id: UUID,
        chunk_index: int,
        neighborhood: int = 1,
    ) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.chunk_index.between(
                    max(0, chunk_index - neighborhood),
                    chunk_index + neighborhood,
                ),
            )
            .order_by(DocumentChunk.chunk_index)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_by_document(
        self,
        query_embedding: list[float],
        owner_id: UUID | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        offset: int = DEFAULT_SEARCH_OFFSET,
    ) -> tuple[list[dict], int]:
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

        search_stmt = (
            base_stmt.order_by(Document.id, desc("similarity"))
            .offset(offset)
            .limit(limit)
        )

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

    async def search_chunks(
        self,
        query_embedding: list[float],
        owner_id: UUID | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        offset: int = DEFAULT_SEARCH_OFFSET,
    ) -> tuple[list[dict], int]:
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

    async def get_best_chunk_per_document(
        self,
        query_embedding: list[float],
        owner_id: UUID | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        offset: int = DEFAULT_SEARCH_OFFSET,
    ) -> tuple[list[dict], int]:
        query_embedding_param = bindparam(
            "query_embedding", value=query_embedding, type_=DocumentChunk.embedding.type
        )
        cosine_similarity = 1 - DocumentChunk.embedding.cosine_distance(
            query_embedding_param
        )

        ranked = (
            select(
                DocumentChunk.document_id,
                cosine_similarity.label("similarity"),
            )
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(DocumentChunk.embedding.isnot(None))
        )

        if owner_id:
            ranked = ranked.where(Document.owner_id == owner_id)

        ranked_subq = (
            ranked.order_by(desc("similarity")).subquery().lateral("ranked_subq")
        )

        count_subq = (
            select(
                DocumentChunk.document_id,
                func.max(
                    1 - DocumentChunk.embedding.cosine_distance(query_embedding_param)
                ).label("max_sim"),
            )
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(
                DocumentChunk.embedding.isnot(None),
            )
            .group_by(DocumentChunk.document_id)
        )

        if owner_id:
            count_subq = count_subq.where(Document.owner_id == owner_id)

        count_result = await self.session.execute(count_subq)
        total = len(list(count_result.all()))

        best_per_doc = (
            select(
                DocumentChunk,
                Document,
                DocumentVersion,
                cosine_similarity.label("similarity"),
            )
            .join(
                ranked_subq,
                ranked_subq.c.document_id == DocumentChunk.document_id,
            )
            .join(Document, DocumentChunk.document_id == Document.id)
            .join(
                DocumentVersion,
                Document.current_version_id == DocumentVersion.id,
                isouter=True,
            )
            .where(
                DocumentChunk.document_id == ranked_subq.c.document_id,
                DocumentChunk.embedding.isnot(None),
            )
        )

        if owner_id:
            best_per_doc = best_per_doc.where(Document.owner_id == owner_id)

        ordered = best_per_doc.order_by(desc("similarity")).offset(offset).limit(limit)

        result = await self.session.execute(ordered)
        rows = result.all()

        doc_match_counts = {}
        for chunk, doc, version, similarity in rows:
            doc_match_counts[doc.id] = doc_match_counts.get(doc.id, 0) + 1

        results = []
        seen_docs: set[UUID] = set()
        for chunk, doc, version, similarity in rows:
            if doc.id in seen_docs:
                continue
            seen_docs.add(doc.id)
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
                    "match_count": doc_match_counts.get(doc.id, 1),
                }
            )

        return results, total

    @staticmethod
    def is_valid_chunk_content(content: str | None) -> bool:
        if not content or not content.strip():
            return False
        if re.match(r"^\s+$", content):
            return False
        ocr_patterns = [
            r"^\[OCR unavailable[^\]]*\]",
            r"^\[Image extraction failed[^\]]*\]",
            r"^\[.*extraction failed[^\]]*\]",
        ]
        for pattern in ocr_patterns:
            if re.match(pattern, content, re.IGNORECASE):
                return False
        return True

    async def get_nearest_valid_chunks(
        self,
        document_id: UUID,
        chunk_index: int,
        neighborhood: int = 2,
    ) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        result = await self.session.execute(stmt)
        all_chunks = list(result.scalars().all())

        if not all_chunks:
            return []

        if chunk_index < 0:
            chunk_index = 0

        candidates = []
        for delta in range(1, neighborhood + 2):
            for idx in (chunk_index - delta, chunk_index + delta):
                if 0 <= idx < len(all_chunks):
                    candidates.append(all_chunks[idx])

        valid = [c for c in candidates if self.is_valid_chunk_content(c.content)]
        if valid:
            return valid[:2]

        fallback = [c for c in all_chunks if self.is_valid_chunk_content(c.content)]
        return fallback[:2]
