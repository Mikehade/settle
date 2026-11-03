"""
Generic base WebSocket consumer.

Owns the lifecycle only: accept, authenticate (bearer token via the
`token` query param or the `Authorization` header), register in the
connection registry, run the receive loop, and clean up. Streaming and
broadcast helpers are provided; subclasses implement `channel`,
`on_connect`, `on_disconnect`, and `handle_message`.

Deliberately free of any payment/quota/feedback machinery — that was
app-specific in the source consumer and has no place in a reusable base.
"""
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from src.api.ws.events import CloseCode, OutboundEvent
from src.api.ws.registry import registry
from src.core.auth import AuthService
from src.domain.entities.users import User
from src.domain.exceptions import AuthenticationError
from src.shared.logging import bind_user, get_logger

logger = get_logger(__name__)


class BaseWebSocketConsumer(ABC):
    def __init__(self, websocket: WebSocket, auth_service: AuthService) -> None:
        self.websocket = websocket
        self._auth = auth_service
        self.user: User | None = None

    # ---- Lifecycle ---------------------------------------------------------
    async def _authenticate(self) -> bool:
        token = self.websocket.query_params.get("token")
        if not token:
            header = self.websocket.headers.get("authorization", "")
            if header.lower().startswith("bearer "):
                token = header[7:]
        if not token:
            await self.websocket.close(code=CloseCode.NOT_AUTHENTICATED)
            return False
        try:
            self.user = await self._auth.resolve_token(token)
            bind_user(self.user["id"])
            return True
        except AuthenticationError:
            await self.websocket.close(code=CloseCode.INVALID_TOKEN)
            return False

    async def handle_connection(self) -> None:
        await self.websocket.accept()
        if not await self._authenticate():
            return
        channel = self.channel
        await registry.register(channel, self)
        try:
            await self.on_connect()
            await self.send_event(OutboundEvent.CONNECTED, {"channel": channel})
            while True:
                try:
                    message = await self.websocket.receive_json()
                except WebSocketDisconnect:
                    break
                except Exception as e:  # noqa: BLE001  — bad frame; report and continue
                    logger.warning("WS bad frame", extra={"event": "ws.bad_frame", "error": str(e)})
                    await self.send_event(OutboundEvent.ERROR, {"message": "Invalid message format"})
                    continue
                await self.handle_message(message)
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            logger.error("WS handler error", extra={"event": "ws.handler_error", "error": str(e)}, exc_info=True)
        finally:
            await registry.unregister(channel, self)
            await self.on_disconnect()
            if self.websocket.client_state != WebSocketState.DISCONNECTED:
                await self.websocket.close(code=CloseCode.NORMAL)

    # ---- Sending -----------------------------------------------------------
    def _envelope(self, event: str, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "event": event,
            "message_id": str(uuid.uuid4()),
            "data": data,
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    async def send_json(self, message: dict[str, Any]) -> None:
        if self.websocket.client_state != WebSocketState.CONNECTED:
            return
        try:
            await self.websocket.send_json(message)
        except Exception as e:  # noqa: BLE001
            logger.debug("WS send failed", extra={"event": "ws.send_error", "error": str(e)})

    async def send_event(self, event: str, data: dict[str, Any] | None = None) -> None:
        await self.send_json(self._envelope(str(event), data or {}))

    async def broadcast_event(self, event: str, data: dict[str, Any] | None = None) -> None:
        await registry.broadcast(self.channel, self._envelope(str(event), data or {}))

    # ---- Contract ----------------------------------------------------------
    @property
    @abstractmethod
    def channel(self) -> str:
        """Scope key for the registry, e.g. 'mediation:<seller_id>'."""
        ...

    @abstractmethod
    async def on_connect(self) -> None: ...

    @abstractmethod
    async def on_disconnect(self) -> None: ...

    @abstractmethod
    async def handle_message(self, message: dict[str, Any]) -> None: ...
