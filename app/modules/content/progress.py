import asyncio
import logging
from collections.abc import Callable

from app.common.sse_manager import SSEManager

logger = logging.getLogger(__name__)


def create_progress_callback(
    progress_manager: SSEManager | None,
    document_id: str,
    max_progress: int = 40,
    total_bytes: int | None = None,
) -> Callable[[int], None] | None:
    """Creates a thread-safe sync callback that schedules an async SSE task."""
    if not progress_manager:
        return None

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error(
            "Cannot create progress callback: No event loop is running in this thread."
        )
        return None

    def callback(bytes_transferred: int) -> None:
        if total_bytes and total_bytes > 0:
            progress_value = min(
                int(bytes_transferred * max_progress / total_bytes), max_progress
            )
        else:
            progress_value = max_progress

        coroutine = progress_manager.publish(
            str(document_id),
            progress_value,
            stage="uploading",
        )

        future = asyncio.run_coroutine_threadsafe(coroutine, loop)

        future.add_done_callback(
            lambda f: (
                logger.error(f"SSE publish failed: {f.exception()}")
                if f.exception()
                else None
            )
        )

    return callback
