"""
Bridge to publish SSE events from synchronous Celery workers to async subscribers.

Since Celery workers run in a separate process/thread without an event loop,
we update the database directly and rely on the frontend to poll for updates,
or use a message queue to communicate progress.
"""

import json
import logging
import uuid

import redis

from app.common.enums.job_status import EJobStatus
from app.common.enums.pipeline_stage import EPipelineStage
from app.common.progress_events import build_progress_event, progress_channel_name
from app.config.db import SyncSessionLocal
from app.config.settings import settings
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
                _publish_progress_to_redis(
                    build_progress_event(
                        document_id=document_id,
                        progress=progress,
                        stage=stage.value if stage else None,
                        status=status.value if status else None,
                        error_log=job.error_log,
                    )
                )

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


def _publish_progress_to_redis(event: dict[str, object]) -> None:
    try:
        client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        client.publish(
            progress_channel_name(str(event["document_id"])),
            json.dumps(event),
        )
        client.close()
    except Exception as e:
        logger.debug("Redis progress publish skipped: %s", e)


def publish_progress_update(
    document_id: uuid.UUID,
    progress: int,
    stage: EPipelineStage | None = None,
    status: EJobStatus | None = None,
) -> None:
    """
    Publish progress update to the database and Redis event bus.

    The database remains the source of truth for job state.
    Redis is used to fan out live progress events to the SSE stream.
    """
    publish_progress_to_db(document_id, progress, stage, status)
