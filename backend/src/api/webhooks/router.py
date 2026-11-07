"""
PayPal dispute webhooks (the Detect step, autonomous path).

PayPal POSTs a `CUSTOMER.DISPUTE.*` event here; Settle verifies the
signature, resolves which seller the dispute belongs to (by PayPal
merchant id), acknowledges immediately, and runs the mediation in the
background — broadcasting the live trace to that seller's own channel so
it shows up on their dashboard.

When the seller can't be resolved (unmapped merchant, or a sandbox
payload missing the linkage), the case is recorded unassigned and
force-escalated — Settle never moves money for a case it can't attribute
— and the trace goes to the shared `mediation:auto` feed that an
ops/superuser client can follow.

Signature verification is skipped only when `PAYPAL_WEBHOOK_ID` is unset
(offline/fixture demo); configure it before any real deployment.
"""
import asyncio
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Request
from fastapi import Depends as FDepends

from src.api.mediation.stream import AUTO_CHANNEL, default_envelope, run_and_broadcast
from src.config.container import Container
from src.core.mediation import MediationService
from src.core.users import UserService
from src.domain.exceptions import AuthenticationError
from src.infrastructure.services.paypal_client import PayPalClient
from src.shared.errors import ErrorCode
from src.shared.logging import get_logger
from src.shared.responses import Envelope, success

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

_DISPUTE_EVENT_PREFIX = "CUSTOMER.DISPUTE"


def _extract_merchant_id(resource: dict[str, Any]) -> str | None:
    """Best-effort pull of the seller's PayPal merchant id from a dispute resource."""
    if not isinstance(resource, dict):
        return None
    candidates = [resource.get("seller_merchant_id"), resource.get("merchant_id")]
    seller = resource.get("seller")
    if isinstance(seller, dict):
        candidates.append(seller.get("merchant_id"))
    for txn in resource.get("disputed_transactions", []) or []:
        if isinstance(txn, dict):
            candidates.append(txn.get("seller_merchant_id"))
    return next((c for c in candidates if c), None)


@router.post("/paypal", response_model=Envelope[dict])
@inject
async def paypal_webhook(
    request: Request,
    mediation: MediationService = FDepends(Provide[Container.mediation_service]),
    users: UserService = FDepends(Provide[Container.user_service]),
    paypal: PayPalClient = FDepends(Provide[Container.paypal_client]),
    settings=FDepends(Provide[Container.config]),
) -> Any:
    """Receive a PayPal webhook. Verifies the signature, then triggers mediation."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}

    # ---- Signature verification -------------------------------------------
    webhook_id = getattr(settings, "PAYPAL_WEBHOOK_ID", "")
    if webhook_id:
        try:
            ok = await paypal.verify_webhook_signature(
                webhook_id=webhook_id, headers=dict(request.headers), event_body=payload
            )
        except Exception as e:  # noqa: BLE001 — treat a verifier failure as unverified
            logger.error("Webhook verify failed", extra={"event": "webhook.verify_error", "error": str(e)})
            ok = False
        if not ok:
            logger.warning("Webhook signature rejected", extra={"event": "webhook.signature_rejected"})
            raise AuthenticationError(ErrorCode.AUTH_TOKEN_INVALID, "Invalid webhook signature")
    else:
        logger.warning("Webhook signature NOT verified (PAYPAL_WEBHOOK_ID unset)", extra={"event": "webhook.unverified"})

    event_type = payload.get("event_type", "")
    resource = payload.get("resource", {}) or {}
    dispute_id = resource.get("dispute_id") or resource.get("id")

    logger.info("PayPal webhook received", extra={"event": "webhook.paypal", "event_type": event_type, "dispute_id": dispute_id})

    if not (event_type.startswith(_DISPUTE_EVENT_PREFIX) and dispute_id):
        return success({"accepted": True, "ignored_event": event_type})

    # ---- Resolve the owning seller ----------------------------------------
    merchant_id = _extract_merchant_id(resource)
    seller = await users.get_by_merchant_id(merchant_id) if merchant_id else None
    seller_id = seller["id"] if seller else None

    if seller_id is not None:
        # Attributed: run under the seller, apply their policy, show on their channel.
        channel = f"mediation:{seller_id}"
        force_escalate = False
    else:
        # Unattributed: never auto-move money; escalate and surface on the ops feed.
        channel = AUTO_CHANNEL
        force_escalate = True

    asyncio.create_task(
        run_and_broadcast(
            mediation, dispute_id, seller_id=seller_id, channel=channel,
            envelope=default_envelope, force_escalate=force_escalate,
        )
    )
    return success({"accepted": True, "dispute_id": dispute_id, "mediating": True, "attributed": seller_id is not None})
