import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import redis

from app.config.settings import settings

logger = logging.getLogger(__name__)

PROGRESS_CHANNEL_PREFIX = "aipcpp:progress"


def progress_channel_name(document_id: str | uuid.UUID) -> str:
    return f"{PROGRESS_CHANNEL_PREFIX}:{document_id}"


def build_progress_event(
    document_id: str | uuid.UUID,
    progress: int,
    stage: str | None = None,
    status: str | None = None,
    error_log: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "progress",
        "document_id": str(document_id),
        "progress": progress,
        "stage": stage,
        "status": status,
        "error_log": error_log,
        "timestamp": datetime.now(UTC).isoformat() + "Z",
    }


def publish_progress_event_sync(
    document_id: uuid.UUID,
    progress: int,
    stage: str | None = None,
    status: str | None = None,
    error_log: dict[str, Any] | None = None,
) -> None:
    event = build_progress_event(
        document_id=document_id,
        progress=progress,
        stage=stage,
        status=status,
        error_log=error_log,
    )

    try:
        client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        client.publish(progress_channel_name(document_id), json.dumps(event))
        client.close()
    except Exception as e:
        logger.debug("Redis progress publish skipped for %s: %s", document_id, e)
