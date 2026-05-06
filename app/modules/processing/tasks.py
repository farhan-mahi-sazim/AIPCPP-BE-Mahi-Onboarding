import uuid
from app.config.celery import celery_app
from app.modules.processing.services import ProcessingService
from app.config.db import SyncSessionLocal
import logging

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def extract_text_task(self, document_id_str: str):
    """Stage 1: Text Extraction from S3 file (Sync)."""
    document_id = uuid.UUID(document_id_str)

    with SyncSessionLocal() as session:
        try:
            service = ProcessingService(session)
            return service.process_extraction(document_id)
        except Exception as exc:
            session.rollback()
            logger.error("Extraction task failed for %s: %s", document_id, exc)
            raise


@celery_app.task(
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def analyze_content_task(self, document_id_str: str):
    """Stage 2: AI Analysis (Sync)."""
    document_id = uuid.UUID(document_id_str)

    with SyncSessionLocal() as session:
        try:
            service = ProcessingService(session)
            return service.process_ai_analysis(document_id)
        except Exception as exc:
            session.rollback()
            logger.error("AI Analysis task failed for %s: %s", document_id, exc)
            raise


@celery_app.task(
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def generate_embeddings_task(self, document_id_str: str):
    """Stage 3: Vector Embedding generation (Sync)."""
    document_id = uuid.UUID(document_id_str)

    with SyncSessionLocal() as session:
        try:
            service = ProcessingService(session)
            return service.process_embeddings(document_id)
        except Exception as exc:
            session.rollback()
            logger.error("Embedding task failed for %s: %s", document_id, exc)
            raise
