"""In-process WebSocket connection registry.

Keyed by channel (e.g. "mediation:<seller_id>"); a channel holds every
live connection in that scope so a case update broadcasts to all of a
seller's open tabs/devices. In-memory and single-process — fine for the
hackathon. A multi-process deployment would back this with Redis pub/sub
(the interface would not change).
"""
import asyncio
from typing import Any

from src.shared.logging import get_logger

logger = get_logger(__name__)


class ConnectionRegistry:
    def __init__(self) -> None:
        self._channels: dict[str, set[Any]] = {}
        self._lock = asyncio.Lock()

    async def register(self, channel: str, consumer: Any) -> None:
        async with self._lock:
            self._channels.setdefault(channel, set()).add(consumer)
        logger.debug("WS registered", extra={"event": "ws.register", "channel": channel, "count": self.count(channel)})

    async def unregister(self, channel: str, consumer: Any) -> None:
        async with self._lock:
            conns = self._channels.get(channel)
            if conns:
                conns.discard(consumer)
                if not conns:
                    self._channels.pop(channel, None)
        logger.debug("WS unregistered", extra={"event": "ws.unregister", "channel": channel})

    def count(self, channel: str) -> int:
        return len(self._channels.get(channel, ()))

    async def broadcast(self, channel: str, message: dict[str, Any]) -> None:
        for consumer in list(self._channels.get(channel, ())):
            try:
                await consumer.send_json(message)
            except Exception as e:  # noqa: BLE001  — one dead socket must not block the rest
                logger.warning("WS broadcast send failed", extra={"event": "ws.broadcast_error", "channel": channel, "error": str(e)})


# Single shared instance for the process.
registry = ConnectionRegistry()
