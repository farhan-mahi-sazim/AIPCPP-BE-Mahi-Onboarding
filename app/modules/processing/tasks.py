import logging
import uuid
from typing import Any

from celery import Task

from app.common.celery_sse_bridge import publish_progress_update
from app.common.enums.job_status import EJobStatus
from app.common.enums.pipeline_stage import EPipelineStage
from app.config.celery import celery_app
from app.config.db import SyncSessionLocal
from app.modules.processing.services import ProcessingService

logger = logging.getLogger(__name__)


def _mark_job_failed(document_id: uuid.UUID, reason: str = "") -> None:
    """Mark a job as FAILED in the database and publish via Redis/SSE."""
    try:
        publish_progress_update(
            document_id,
            progress=0,
            stage=EPipelineStage.PERSISTENCE,
            status=EJobStatus.FAILED,
        )
        logger.info(
            "Marked job FAILED for %s%s", document_id, f": {reason}" if reason else ""
        )
    except Exception as e:
        logger.error("Failed to mark job FAILED for %s: %s", document_id, e)


def _mark_job_failed_on_failure(
    self: Task,
    exc: Exception,
    task_id: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    einfo: Any,
) -> None:
    """Callback to mark job as FAILED when a task fails after all retries."""
    retries = self.request.retries
    max_retries = self.max_retries
    if retries < max_retries:
        logger.debug(
            "Task %s still has retries (%d/%d), not marking failed",
            self.name,
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

    _mark_job_failed(document_id, str(exc)[:200])


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
    """Stage 1: Text Extraction from S3 file (Sync).

    Returns the document_id_str on success, or an error indicator on failure.
    Never raises — errors are caught internally so the chain always continues.
    """
    document_id = uuid.UUID(document_id_str)

    with SyncSessionLocal() as session:
        try:
            service = ProcessingService(session)
            return service.process_extraction(document_id)
        except Exception as exc:
            session.rollback()
            logger.error("Extraction task failed for %s: %s", document_id, exc)
            _mark_job_failed(document_id, str(exc)[:200])
            return f"__error__:{document_id_str}:{exc.__class__.__name__}"


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
    """Stage 2: AI Analysis (Sync).

    Returns the document_id_str on success, or an error indicator on failure.
    Never raises — errors are caught internally so the chord always completes.
    """
    document_id = uuid.UUID(document_id_str)

    with SyncSessionLocal() as session:
        try:
            service = ProcessingService(session)
            return service.process_ai_analysis(document_id)
        except Exception as exc:
            session.rollback()
            logger.error("AI Analysis task failed for %s: %s", document_id, exc)
            _mark_job_failed(document_id, str(exc)[:200])
            return f"__error__:{document_id_str}:{exc.__class__.__name__}"


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
    """Stage 3: Vector Embedding generation (Sync).

    Returns the document_id_str on success, or an error indicator on failure.
    Never raises — errors are caught internally so the chord always completes.
    """
    document_id = uuid.UUID(document_id_str)

    with SyncSessionLocal() as session:
        try:
            service = ProcessingService(session)
            return service.process_embeddings(document_id)
        except Exception as exc:
            session.rollback()
            logger.error("Embedding task failed for %s: %s", document_id, exc)
            _mark_job_failed(document_id, str(exc)[:200])
            return f"__error__:{document_id_str}:{exc.__class__.__name__}"


ERROR_PREFIX = "__error__:"


def _extract_document_id_str(args: tuple, kwargs: dict) -> str | None:
    raw = kwargs.get("document_id_str")
    if raw:
        return raw
    if not args:
        return None
    group_result = args[0]
    if isinstance(group_result, str) and not group_result.startswith(ERROR_PREFIX):
        return group_result
    if isinstance(group_result, list) and group_result:
        for item in group_result:
            if isinstance(item, str) and not item.startswith(ERROR_PREFIX):
                return item
    return None


@celery_app.task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def validate_and_finalize_job_task(self: Any, *args: Any, **kwargs: Any) -> str | None:
    """Stage 4: Finalize Job and update status (Sync).

    Checks group results for error indicators first. If any parallel task
    failed, marks the job as FAILED instead of proceeding with validation.
    """
    document_id_str = _extract_document_id_str(args, kwargs)
    if not document_id_str:
        logger.error("No document_id_str provided to finalize task")
        return None

    document_id = uuid.UUID(document_id_str)

    # Check if any parallel task reported an error
    group_results = args[0] if args and isinstance(args[0], list) else []
    error_items = [
        r for r in group_results if isinstance(r, str) and r.startswith(ERROR_PREFIX)
    ]

    with SyncSessionLocal() as session:
        try:
            if error_items:
                error_descriptions = [r.split(":", 2)[-1] for r in error_items]
                logger.error(
                    "Parallel tasks failed for %s: %s",
                    document_id,
                    "; ".join(error_descriptions),
                )
                _mark_job_failed(document_id, "; ".join(error_descriptions))
                return None

            service = ProcessingService(session)
            service.validate_and_finalize_job(document_id)
            return str(document_id)
        except Exception as exc:
            session.rollback()
            logger.error("Finalization task failed for %s: %s", document_id, exc)
            _mark_job_failed(document_id, str(exc)[:200])
            return None
