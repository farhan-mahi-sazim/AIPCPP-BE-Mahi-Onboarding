import logging
import uuid
from typing import Any

from celery import Task

from app.common.enums.job_status import EJobStatus
from app.common.enums.pipeline_stage import EPipelineStage
from app.config.celery import celery_app
from app.config.db import SyncSessionLocal
from app.modules.content.repositories import ProcessingJobRepositorySync
from app.modules.processing.services import ProcessingService

logger = logging.getLogger(__name__)


def _mark_job_failed_on_failure(
    task: Task, exc: Exception, *args: Any, **kwargs: Any
) -> None:
    """Callback to mark job as FAILED when a task fails after all retries."""
    retries = task.request.retries
    max_retries = task.max_retries
    if retries < max_retries:
        logger.debug(
            "Task %s still has retries (%d/%d), not marking failed",
            task.name,
            retries,
            max_retries,
        )
        return

    document_id_str = args[0] if args else kwargs.get("document_id_str")
    if not document_id_str:
        logger.error("No document_id_str provided to failure callback")
        return
    try:
        document_id = uuid.UUID(document_id_str)
    except (ValueError, TypeError):
        logger.error("Invalid document_id_str: %s", document_id_str)
        return

    with SyncSessionLocal() as session:
        try:
            job_repo = ProcessingJobRepositorySync(session)
            job = job_repo.get_by_document_id(document_id)
            if job and job.status != EJobStatus.COMPLETED:
                job.status = EJobStatus.FAILED
                job.stage = EPipelineStage.PERSISTENCE
                session.commit()
                logger.info(
                    "Marked job FAILED after task exhausted retries: %s", document_id
                )
        except Exception as e:
            logger.error("Failed to mark job FAILED for %s: %s", document_id, e)


@celery_app.task(
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    on_failure=_mark_job_failed_on_failure,
)
def extract_text_task(self: Any, document_id_str: str) -> str:
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
    on_failure=_mark_job_failed_on_failure,
)
def analyze_content_task(self: Any, document_id_str: str) -> str:
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
    on_failure=_mark_job_failed_on_failure,
)
def generate_embeddings_task(self: Any, document_id_str: str) -> str:
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


@celery_app.task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def validate_and_finalize_job_task(self: Any, *args: Any, **kwargs: Any) -> str | None:
    """Stage 4: Finalize Job and update status (Sync)."""
    document_id_str = kwargs.get("document_id_str")
    if not document_id_str and args:
        group_result_or_id = args[0]
        if isinstance(group_result_or_id, list) and group_result_or_id:
            first_item = group_result_or_id[0]
            if first_item:
                document_id_str = first_item
        elif isinstance(group_result_or_id, str):
            document_id_str = group_result_or_id

    if not isinstance(document_id_str, str) or not document_id_str:
        logger.error("No document_id_str provided to finalize task")
        return None

    document_id = uuid.UUID(document_id_str)

    with SyncSessionLocal() as session:
        try:
            service = ProcessingService(session)
            service.validate_and_finalize_job(document_id)
            return str(document_id)
        except Exception as exc:
            session.rollback()
            logger.error("Finalization task failed for %s: %s", document_id, exc)
            raise
