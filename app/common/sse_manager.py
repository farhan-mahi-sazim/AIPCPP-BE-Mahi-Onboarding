import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

MAX_SSE_POLLS_AFTER_DISCONNECT = 10
SSE_DISCONNECT_GRACE_SECONDS = 30


class SSEManager:
    def __init__(self) -> None:
        self._subscriptions: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._last_events: dict[str, dict[str, Any]] = {}
        self._disconnected_at: dict[str, datetime] = {}
        self._poll_count_after_disconnect: dict[str, int] = {}

    async def subscribe(self, document_id: str) -> AsyncIterator[dict[str, Any]]:
        """
        Subscribe to progress updates for a document.

        When a client connects via SSE, this generator sends progress updates.
        It sends the last known event immediately, then waits for new events.
        """
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscriptions[document_id] = queue
        self._disconnected_at.pop(document_id, None)
        self._poll_count_after_disconnect.pop(document_id, None)

        try:
            if document_id in self._last_events:
                yield self._last_events[document_id]

            while True:
                event = await queue.get()
                yield event
        finally:
            self._subscriptions.pop(document_id, None)
            self._disconnected_at[document_id] = datetime.now(UTC)
            self._poll_count_after_disconnect[document_id] = 0

    def is_connected(self, document_id: str) -> bool:
        """Return True if an SSE client is currently subscribed for this document."""
        return document_id in self._subscriptions

    def was_disconnected(self, document_id: str) -> bool:
        """Return True if an SSE client was previously subscribed but has disconnected."""
        return document_id in self._disconnected_at

    def record_poll(self, document_id: str) -> int:
        """Increment and return the poll count after SSE disconnect for this document."""
        count = self._poll_count_after_disconnect.get(document_id, 0) + 1
        self._poll_count_after_disconnect[document_id] = count
        return count

    def should_stop_polling(self, document_id: str) -> bool:
        """Return True if the polling for this document should stop.

        Stops when either the max poll count or grace period (post-SSE-disconnect) is exceeded.
        """
        if document_id not in self._disconnected_at:
            return False
        count = self._poll_count_after_disconnect.get(document_id, 0)
        if count >= MAX_SSE_POLLS_AFTER_DISCONNECT:
            return True
        elapsed = (
            datetime.now(UTC) - self._disconnected_at[document_id]
        ).total_seconds()
        if elapsed >= SSE_DISCONNECT_GRACE_SECONDS:
            return True
        return False

    async def publish(
        self,
        document_id: str,
        progress: int,
        stage: str | None = None,
        status: str | None = None,
        error_log: dict[str, Any] | None = None,
    ) -> None:
        """
        Publish a progress update to all subscribers of this document.
        """
        event = {
            "type": "progress",
            "document_id": document_id,
            "progress": progress,
            "stage": stage,
            "status": status,
            "error_log": error_log,
            "timestamp": datetime.now(UTC).isoformat() + "Z",
        }

        # Cache the last event
        self._last_events[document_id] = event

        # Send to all subscribers
        queue = self._subscriptions.get(document_id)
        if queue:
            await queue.put(event)
            logger.debug(
                "Published SSE event for %s: progress=%d, stage=%s",
                document_id,
                progress,
                stage,
            )
        else:
            logger.debug(
                "No active subscribers for %s (event cached for next connection)",
                document_id,
            )


sse_manager = SSEManager()
