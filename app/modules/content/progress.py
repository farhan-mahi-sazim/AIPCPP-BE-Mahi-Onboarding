import asyncio
import logging
from collections.abc import Callable

from app.common.sse_manager import SSEManager

logger = logging.getLogger(__name__)


def create_progress_callback(
    progress_manager: SSEManager | None,
    document_id: str,
    max_progress: int = 50,
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

    def callback(current_progress: int) -> None:
        progress_value = current_progress if current_progress > 0 else max_progress

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
