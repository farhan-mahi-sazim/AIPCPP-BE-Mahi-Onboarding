import logging

from sentence_transformers import SentenceTransformer

from app.config.settings import settings

logger = logging.getLogger(__name__)


class LocalEmbeddingService:
    """Singleton wrapper around a sentence-transformers model.

    The model is loaded once on first use and reused for all subsequent calls.
    This is intentionally synchronous — sentence-transformers is a sync library.
    Use run_in_threadpool when calling from async contexts.
    """

    _instance: SentenceTransformer | None = None

    @classmethod
    def _get_model(cls) -> SentenceTransformer:
        if cls._instance is None:
            logger.info(
                "Loading local embedding model: %s", settings.LOCAL_EMBEDDING_MODEL
            )
            try:
                cls._instance = SentenceTransformer(settings.LOCAL_EMBEDDING_MODEL)
            except Exception as e:
                logger.warning(
                    "Failed to load model normally (possibly offline): %s. "
                    "Retrying with local_files_only=True...",
                    e,
                )
                cls._instance = SentenceTransformer(
                    settings.LOCAL_EMBEDDING_MODEL, local_files_only=True
                )
            logger.info("Local embedding model loaded successfully.")
        return cls._instance

    @classmethod
    def preload(cls) -> None:
        """Force load the model into memory. Call this at app startup."""
        cls._get_model()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns a list of embedding vectors."""
        model = self._get_model()
        embeddings = model.encode(texts, convert_to_numpy=True)
        return [emb.tolist() for emb in embeddings]

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string. Convenience wrapper around embed()."""
        return self.embed([query])[0]
