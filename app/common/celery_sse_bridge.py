"""
Bridge to publish SSE events from synchronous Celery workers to async subscribers.

Since Celery workers run in a separate process/thread without an event loop,
we update the database directly and rely on the frontend to poll for updates,
or use a message queue to communicate progress.
"""

import logging
import uuid

from app.common.enums.job_status import EJobStatus
from app.common.enums.pipeline_stage import EPipelineStage
from app.common.sse_manager import sse_manager
from app.config.db import SyncSessionLocal
from app.modules.content.repositories import ProcessingJobRepositorySync

logger = logging.getLogger(__name__)


def publish_progress_to_db(
    document_id: uuid.UUID,
    progress: int,
    stage: EPipelineStage | None = None,
    status: EJobStatus | None = None,
) -> None:
    """
    Update job progress in the database.

    This is called from Celery workers (sync context) and updates the DB directly.
    The database becomes the source of truth for progress.

    Args:
        document_id: ID of the document being processed
        progress: Progress percentage (0-100)
        stage: Current pipeline stage
        status: Current job status
    """
    try:
        with SyncSessionLocal() as session:
            job_repo = ProcessingJobRepositorySync(session)
            job = job_repo.get_by_document_id(document_id)

            if job:
                job.progress = progress
                if stage:
                    job.stage = stage
                if status:
                    job.status = status

                session.commit()

                if status in {EJobStatus.COMPLETED, EJobStatus.FAILED}:
                    sse_manager._last_events.pop(str(document_id), None)

                logger.info(
                    "Updated job progress for %s: progress=%d, stage=%s, status=%s",
                    document_id,
                    progress,
                    stage,
                    status,
                )
            else:
                logger.warning("Job not found for document %s", document_id)
    except Exception as e:
        logger.error("Failed to update job progress for %s: %s", document_id, e)


def publish_progress_update(
    document_id: uuid.UUID,
    progress: int,
    stage: EPipelineStage | None = None,
    status: EJobStatus | None = None,
) -> None:
    """
    Publish progress update (currently updates DB only).

    In the future, this can be enhanced to:
    - Publish to Redis pub/sub
    - Send webhook notifications
    - Update WebSocket connections

    For now, we rely on clients polling the progress endpoint.
    """
    publish_progress_to_db(document_id, progress, stage, status)
