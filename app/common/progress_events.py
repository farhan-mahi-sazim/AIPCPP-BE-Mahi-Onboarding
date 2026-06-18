import logging
import uuid
from datetime import UTC, datetime
from typing import Any

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
