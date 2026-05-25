import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class SSEManager:
    def __init__(self) -> None:
        self._subscriptions: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._last_events: dict[
            str, dict[str, Any]
        ] = {}  # Cache last event per document

    async def subscribe(self, document_id: str) -> AsyncIterator[dict[str, Any]]:
        """
        Subscribe to progress updates for a document.

        When a client connects via SSE, this generator sends progress updates.
        It sends the last known event immediately, then waits for new events.
        """
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscriptions[document_id] = queue

        try:
            # Send the last known event if it exists (helps clients catch up)
            if document_id in self._last_events:
                yield self._last_events[document_id]

            # Wait for new events
            while True:
                event = await queue.get()
                yield event
        finally:
            self._subscriptions.pop(document_id, None)

    async def publish(
        self, document_id: str, progress: int, stage: str | None = None
    ) -> None:
        """
        Publish a progress update to all subscribers of this document.
        """
        event = {
            "type": "progress",
            "document_id": document_id,
            "progress": progress,
            "stage": stage,
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
