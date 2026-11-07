"""Map the MediationService's neutral event dicts onto the `case.*` wire
events, and a helper to run a mediation and broadcast it to a channel.

Keeping this mapping in the api layer is what lets core stay free of any
WebSocket vocabulary — core yields {"type": ...}; the api decides the
wire name."""
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.api.ws.events import OutboundEvent
from src.api.ws.registry import registry
from src.core.mediation import MediationService
from src.domain.exceptions import AppError
from src.shared.logging import get_logger

# Channel autonomous (webhook) runs broadcast to when no seller could be resolved.
# A connected superuser/ops client subscribes to it; resolved runs go to the
# seller's own channel instead.
AUTO_CHANNEL = "mediation:auto"


def default_envelope(event: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": event,
        "message_id": str(uuid.uuid4()),
        "data": data,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

logger = get_logger(__name__)

_EVENT_MAP: dict[str, OutboundEvent] = {
    "detected": OutboundEvent.CASE_DETECTED,
    "gathering": OutboundEvent.CASE_GATHERING,
    "gathered": OutboundEvent.CASE_GATHERING,
    "reasoning_step": OutboundEvent.CASE_REASONING_STEP,
    "token": OutboundEvent.CASE_TOKEN,
    "tool_call": OutboundEvent.CASE_TOOL_CALL,
    "tool_result": OutboundEvent.CASE_TOOL_RESULT,
    "decision": OutboundEvent.CASE_DECISION,
    "escalated": OutboundEvent.CASE_ESCALATED,
    "executed": OutboundEvent.CASE_EXECUTED,
    "explained": OutboundEvent.CASE_EXPLAINED,
    "error": OutboundEvent.CASE_ERROR,
}


def map_event(ev: dict[str, Any]) -> tuple[OutboundEvent, dict[str, Any]]:
    t = ev.get("type", "")
    wire = _EVENT_MAP.get(t, OutboundEvent.CASE_ERROR)
    data = {k: v for k, v in ev.items() if k != "type"}
    return wire, data


async def run_and_broadcast(
    mediation_service: MediationService,
    dispute_id: str,
    *,
    seller_id: UUID | None,
    channel: str,
    envelope,
    force_escalate: bool = False,
) -> None:
    """Drive a full mediation, broadcasting each mapped event to `channel`.
    `envelope` builds the wire message (consumer._envelope)."""
    try:
        async for ev in mediation_service.mediate_stream(dispute_id, seller_id=seller_id, force_escalate=force_escalate):
            wire, data = map_event(ev)
            await registry.broadcast(channel, envelope(str(wire), data))
    except AppError as e:
        logger.info("Mediation stream rejected", extra={"event": "mediation.stream_rejected", "dispute": dispute_id, "code": e.code})
        await registry.broadcast(channel, envelope(str(OutboundEvent.CASE_ERROR), {"dispute_id": dispute_id, "error": e.message, "code": e.code}))
    except Exception as e:  # noqa: BLE001
        logger.error("Mediation stream crashed", extra={"event": "mediation.stream_crash", "dispute": dispute_id, "error": str(e)}, exc_info=True)
        await registry.broadcast(channel, envelope(str(OutboundEvent.CASE_ERROR), {"dispute_id": dispute_id, "error": str(e)}))
