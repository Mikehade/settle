"""
Mediation WebSocket consumer.

One socket per seller. It streams the live reasoning trace for a case
(reasoning steps + rationale tokens + decision) and takes the seller's
inbound actions — trigger a mediation, approve/reject an escalation,
answer the mediator in the chat lane, or update the fairness policy.

Reasoning is broadcast to the seller's whole channel (every open tab)
rather than sent to one socket, so a second device follows along too.
"""
import asyncio
from typing import Any

from fastapi import WebSocket

from src.api.mediation.stream import run_and_broadcast
from src.api.ws.consumer import BaseWebSocketConsumer
from src.api.ws.events import InboundEvent, OutboundEvent
from src.core.auth import AuthService
from src.core.mediation import MediationService
from src.core.policy import FairnessPolicyService
from src.shared.logging import get_logger

logger = get_logger(__name__)


class MediationConsumer(BaseWebSocketConsumer):
    def __init__(
        self,
        websocket: WebSocket,
        auth_service: AuthService,
        mediation_service: MediationService,
        policy_service: FairnessPolicyService,
    ) -> None:
        super().__init__(websocket, auth_service)
        self._mediation = mediation_service
        self._policies = policy_service

    @property
    def channel(self) -> str:
        return f"mediation:{self.user['id']}" if self.user else "mediation:anon"

    async def on_connect(self) -> None:
        logger.info("Mediation WS connected", extra={"event": "mediation.ws_connect", "user": str(self.user["id"]) if self.user else None})

    async def on_disconnect(self) -> None:
        pass

    async def handle_message(self, message: dict[str, Any]) -> None:
        event = message.get("event")
        data = message.get("data", message)
        seller_id = self.user["id"] if self.user else None

        if event == InboundEvent.PING.value:
            await self.send_event(OutboundEvent.AGENT_TYPING, {"typing": False})
            return

        if event == InboundEvent.MEDIATE.value:
            dispute_id = data.get("dispute_id")
            if not dispute_id:
                await self.send_event(OutboundEvent.CASE_ERROR, {"error": "dispute_id is required"})
                return
            # Run in the background so the socket stays responsive to approve/reject.
            asyncio.create_task(
                run_and_broadcast(self._mediation, dispute_id, seller_id=seller_id, channel=self.channel, envelope=self._envelope)
            )
            return

        if event == InboundEvent.APPROVE.value:
            summary = await self._mediation.approve(data.get("dispute_id"), seller_id=seller_id)
            await self.broadcast_event(OutboundEvent.CASE_EXECUTED, summary)
            return

        if event == InboundEvent.REJECT.value:
            summary = await self._mediation.reject(data.get("dispute_id"), seller_id=seller_id)
            await self.broadcast_event(OutboundEvent.CASE_EXPLAINED, summary)
            return

        if event == InboundEvent.SET_POLICY.value and seller_id:
            policy = await self._policies.set_policy(seller_id, {k: v for k, v in data.items() if k != "event"})
            await self.send_event(OutboundEvent.AGENT_MESSAGE, {"message": "Fairness policy updated.", "policy": {"rules_text": policy.get("rules_text", "")}})
            return

        if event == InboundEvent.MESSAGE.value:
            # Chat lane: the seller answers a mediator question. For the hackathon
            # this acknowledges and echoes; a full chat agent would route here.
            await self.send_event(OutboundEvent.AGENT_MESSAGE, {"message": "Noted. Re-run mediation to apply new information.", "echo": data.get("text", "")})
            return

        await self.send_event(OutboundEvent.CASE_ERROR, {"error": f"Unknown event: {event}"})
