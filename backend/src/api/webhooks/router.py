"""
PayPal dispute webhooks (the Detect step, autonomous path).

PayPal POSTs a `CUSTOMER.DISPUTE.*` event here; Settle acknowledges
immediately and runs the mediation in the background, broadcasting the
live trace to the `mediation:auto` channel (any dashboard listening to
it sees autonomous resolutions happen). Signature verification against
PAYPAL_WEBHOOK_ID is stubbed for the hackathon — wire it in before any
real deployment.

A poll fallback (for when webhooks aren't configured in sandbox) is
available via `python manage.py` / the DisputeSource.list_open feed.
"""
import asyncio
from typing import Any

from dependency_injector.wiring import inject
from fastapi import APIRouter, Request

from src.api.deps import MediationServiceDep
from src.api.mediation.stream import default_envelope, run_and_broadcast
from src.shared.logging import get_logger
from src.shared.responses import Envelope, success

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

_DISPUTE_EVENT_PREFIX = "CUSTOMER.DISPUTE"
AUTO_CHANNEL = "mediation:auto"


@router.post("/paypal", response_model=Envelope[dict])
@inject
async def paypal_webhook(request: Request, mediation: MediationServiceDep) -> Any:
    """Receive a PayPal webhook. Triggers autonomous mediation on dispute events."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}

    event_type = payload.get("event_type", "")
    resource = payload.get("resource", {}) or {}
    dispute_id = resource.get("dispute_id") or resource.get("id")

    logger.info("PayPal webhook received", extra={"event": "webhook.paypal", "event_type": event_type, "dispute_id": dispute_id})

    if event_type.startswith(_DISPUTE_EVENT_PREFIX) and dispute_id:
        # Fire-and-forget: acknowledge PayPal fast, mediate in the background.
        asyncio.create_task(
            run_and_broadcast(mediation, dispute_id, seller_id=None, channel=AUTO_CHANNEL, envelope=default_envelope)
        )
        return success({"accepted": True, "dispute_id": dispute_id, "mediating": True})

    return success({"accepted": True, "ignored_event": event_type})
