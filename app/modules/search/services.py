import hashlib
import logging
import re
import uuid

import litellm
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import cached
from app.common.cache.constants import CACHE_SEARCH_TTL, ECacheKeyPrefix
from app.common.embedding import LocalEmbeddingService
from app.config.settings import settings
from app.modules.search.constants import (
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_SEARCH_OFFSET,
    MAX_SEARCH_LIMIT,
    STOP_WORDS,
    SYNTHESIS_PROMPT_TEMPLATE,
    SearchError,
)
from app.modules.search.repositories import SearchRepository
from app.modules.search.schemas import (
    TSearchDocumentResult,
    TSearchMatchChunk,
    TSearchResponse,
)

logger = logging.getLogger(__name__)


def _build_search_cache_key(
    prefix: str,
    query: str,
    owner_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> str:
    normalized_query = " ".join(query.strip().lower().split())
    key_string = (
        f"{prefix}:q={normalized_query}:owner={owner_id}:limit={limit}:offset={offset}"
    )

    if len(key_string) > 200:
        hash_suffix = hashlib.md5(key_string.encode()).hexdigest()
        return f"{prefix}:{hash_suffix}"

    return key_string


class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.search_repo = SearchRepository(session)

    async def _generate_query_embedding(self, query: str) -> list[float]:
        try:
            service = LocalEmbeddingService()
            return await run_in_threadpool(service.embed_query, query)
        except Exception as e:
            logger.error("Failed to generate query embedding: %s", str(e))
            raise ValueError(SearchError.EMBEDDING_FAILED)

    def _build_highlight(
        self, content: str | None, query_terms: list[str], max_length: int = 300
    ) -> str:
        if not content:
            return ""

        content = content.strip()
        content_lower = content.lower()

        # Try to find best position from any query term
        best_pos = 0
        for term in query_terms:
            pos = content_lower.find(term.lower())
            if pos >= 0:
                best_pos = max(0, pos - 50)
                break
        else:
            # No term matched literally — show middle section as fallback
            mid = len(content) // 2
            best_pos = max(0, mid - max_length // 2)

        snippet = content[best_pos : best_pos + max_length]

        if best_pos > 0:
            snippet = "..." + snippet
        if len(content) > best_pos + max_length:
            snippet = snippet + "..."

        for term in query_terms:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            snippet = pattern.sub(lambda m: f"<em>{m.group(0)}</em>", snippet)

        return snippet

    def _relevance_from_score(self, score: float) -> str:
        if score >= 0.75:
            return "high"
        if score >= 0.60:
            return "medium"
        return "low"

    def _extract_query_terms(self, query: str) -> list[str]:
        words = re.split(r"\s+", query.strip())
        return [w for w in words if w.lower() not in STOP_WORDS and len(w) > 2]

    async def _synthesize(
        self,
        query: str,
        chunks: list[dict],
    ) -> str | None:
        if not chunks:
            logger.debug("Synthesis skipped: no chunks provided")
            return None

        excerpts = []
        for chunk in chunks[: settings.SYNTHESIS_MAX_CHUNKS]:
            content = chunk.get("chunk_content", "")
            if not SearchRepository.is_valid_chunk_content(content):
                continue
            filename = chunk.get("filename", "Unknown")
            excerpts.append(f"[Document: {filename}]\n{content.strip()}")

        if not excerpts:
            logger.debug("Synthesis skipped: all chunks had invalid content")
            return None

        joined = "\n\n---\n\n".join(excerpts)
        joined = joined.replace("{", "{{").replace("}", "}}")

        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(query=query, excerpts=joined)

        models_to_try = [
            settings.SEARCH_SYNTHESIS_MODEL,
            settings.LITELLM_MODEL,
            "gemini/gemini-2.5-flash",
            "gemini/gemini-2.0-flash",
        ]

        for model in models_to_try:
            try:
                response = await litellm.acompletion(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful assistant. Answer directly and concisely "
                            "based only on the provided document excerpts.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=500,
                    timeout=settings.SYNTHESIS_TIMEOUT_SECONDS,
                )

                answer = response.choices[0].message.content
                if answer and answer.strip():
                    logger.info(
                        "Synthesis generated for query '%s' using %s", query, model
                    )
                    return answer.strip()

            except Exception as e:
                logger.warning(
                    "Synthesis model %s failed for query '%s': %s",
                    model,
                    query,
                    str(e),
                )
                continue

        logger.warning("All synthesis models exhausted for query: %s", query)
        return None

    async def _cleanup_chunk_content(
        self,
        chunk: dict,
        query_terms: list[str],
    ) -> dict:
        content = chunk.get("chunk_content", "")
        chunk_index = chunk.get("chunk_index", 0)
        doc_id = chunk.get("document_id")

        if not SearchRepository.is_valid_chunk_content(content):
            if doc_id:
                valid_chunks = await self.search_repo.get_nearest_valid_chunks(
                    doc_id, chunk_index
                )
                if valid_chunks:
                    best = valid_chunks[0]
                    chunk["chunk_content"] = best.content
                    chunk["chunk_index"] = best.chunk_index
                    logger.debug(
                        "Replaced invalid chunk %d for doc %s with chunk %d",
                        chunk_index,
                        doc_id,
                        best.chunk_index,
                    )

        return chunk

    @cached(
        prefix=ECacheKeyPrefix.SEARCH_RESULTS.value,
        ttl=CACHE_SEARCH_TTL,
        key_builder=lambda *args, **kwargs: _build_search_cache_key(
            ECacheKeyPrefix.SEARCH_RESULTS.value,
            kwargs.get("query") if "query" in kwargs else args[1],
            kwargs.get("owner_id") if "owner_id" in kwargs else args[2],
            kwargs.get("limit") if "limit" in kwargs else args[3],
            kwargs.get("offset") if "offset" in kwargs else args[4],
        ),
    )
    async def search(
        self,
        query: str,
        owner_id: uuid.UUID | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        offset: int = DEFAULT_SEARCH_OFFSET,
    ) -> TSearchResponse:
        if not query or not query.strip():
            raise ValueError(SearchError.EMPTY_QUERY)

        if limit < 1:
            raise ValueError(SearchError.INVALID_LIMIT)

        limit = min(limit, MAX_SEARCH_LIMIT)

        if offset < 0:
            offset = DEFAULT_SEARCH_OFFSET

        query_embedding = await self._generate_query_embedding(query)
        query_terms = self._extract_query_terms(query)

        raw_results, total = await self.search_repo.get_best_chunk_per_document(
            query_embedding=query_embedding,
            owner_id=owner_id,
            limit=limit,
            offset=offset,
        )

        cleaned: list[dict] = []
        for chunk in raw_results:
            cleaned_chunk = await self._cleanup_chunk_content(chunk, query_terms)
            cleaned.append(cleaned_chunk)

        synthesis_chunks = cleaned[: settings.SYNTHESIS_MAX_CHUNKS]
        synthesis_answer = await self._synthesize(query, synthesis_chunks)

        search_results: list[TSearchDocumentResult] = []
        for chunk in cleaned:
            highlight = self._build_highlight(
                chunk.get("chunk_content", ""),
                query_terms,
            )

            search_results.append(
                TSearchDocumentResult(
                    document_id=chunk["document_id"],
                    filename=chunk["filename"],
                    file_type=chunk["file_type"],
                    summary=chunk.get("summary"),
                    created_at=chunk["created_at"],
                    relevance=self._relevance_from_score(chunk["similarity_score"]),
                    match_count=chunk.get("match_count", 1),
                    best_chunk=TSearchMatchChunk(
                        chunk_index=chunk["chunk_index"],
                        highlight=highlight,
                        similarity_score=round(chunk["similarity_score"], 3),
                    ),
                )
            )

        return TSearchResponse(
            results=search_results,
            synthesis_answer=synthesis_answer,
            total=total,
            query=query,
            limit=limit,
            offset=offset,
        )
