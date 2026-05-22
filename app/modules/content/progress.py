import asyncio
from collections.abc import Callable

from app.common.sse_manager import SSEManager


def create_progress_callback(
    progress_manager: SSEManager | None,
    document_id: str,
    max_progress: int = 50,
) -> Callable[[int], None] | None:
    if not progress_manager:
        return None

    async def _send_progress_async() -> None:
        await progress_manager.publish(
            str(document_id),
            50,
            stage="uploading",
        )

    def callback(_bytes_transferred: int) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_send_progress_async()))

    return callback
