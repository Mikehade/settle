"""
PayPalClient — typed access to the PayPal REST APIs Settle uses.

Reads (for the Gather step): Disputes v1 (show dispute), Payments v2
(show capture), Shipment Tracking v1 (tracking status).
Writes (performed only by the executor): refund a capture, make an
offer / resolve a dispute, accept a claim, provide evidence.

Every money movement in Settle crosses one of the write methods here;
the AI chooses, this client executes against PayPal.
"""
from typing import Any

from src.infrastructure.clients.paypal_http import PayPalHttpClient
from src.shared.logging import get_logger

logger = get_logger(__name__)


class PayPalClient:
    def __init__(self, http: PayPalHttpClient) -> None:
        self._http = http

    # ---- Reads -------------------------------------------------------------
    async def list_disputes(self) -> dict[str, Any]:
        """List disputes (Customer Disputes v1)."""
        return await self._http.request("GET", "/v1/customer-disputes/disputes")

    async def get_dispute(self, dispute_id: str) -> dict[str, Any]:
        """Show dispute details (reason, messages, disputed amount, linked txn)."""
        return await self._http.request("GET", f"/v1/customer-disputes/disputes/{dispute_id}")

    async def get_transaction(self, capture_id: str) -> dict[str, Any]:
        """Show captured payment details (Payments v2)."""
        return await self._http.request("GET", f"/v2/payments/captures/{capture_id}")

    async def get_tracking(self, transaction_id: str, tracking_number: str | None = None) -> dict[str, Any]:
        """Show shipment tracking (Shipment Tracking v1)."""
        tid = f"{transaction_id}-{tracking_number}" if tracking_number else transaction_id
        return await self._http.request("GET", f"/v1/shipping/trackers/{tid}")

    async def verify_webhook_signature(self, *, webhook_id: str, headers: dict[str, str], event_body: dict[str, Any]) -> bool:
        """Verify an inbound webhook against PayPal (Notifications v1).

        Returns True only when PayPal reports verification_status == SUCCESS."""
        def h(name: str) -> str:
            return headers.get(name) or headers.get(name.lower()) or ""

        body = {
            "transmission_id": h("paypal-transmission-id"),
            "transmission_time": h("paypal-transmission-time"),
            "cert_url": h("paypal-cert-url"),
            "auth_algo": h("paypal-auth-algo"),
            "transmission_sig": h("paypal-transmission-sig"),
            "webhook_id": webhook_id,
            "webhook_event": event_body,
        }
        resp = await self._http.request("POST", "/v1/notifications/verify-webhook-signature", json=body)
        return resp.get("verification_status") == "SUCCESS"

    # ---- Writes (executor only) -------------------------------------------
    async def refund_capture(self, capture_id: str, amount: float, currency: str) -> dict[str, Any]:
        """Refund a captured payment, full or partial (Payments v2)."""
        body = {"amount": {"value": f"{amount:.2f}", "currency_code": currency}}
        return await self._http.request("POST", f"/v2/payments/captures/{capture_id}/refund", json=body)

    async def accept_claim(self, dispute_id: str, note: str = "") -> dict[str, Any]:
        """Accept the buyer's claim on the seller's behalf (Disputes actions)."""
        body = {"note": note or "Accepting the claim to resolve the dispute fairly."}
        return await self._http.request("POST", f"/v1/customer-disputes/disputes/{dispute_id}/accept-claim", json=body)

    async def make_offer(self, dispute_id: str, amount: float, currency: str, note: str, offer_type: str) -> dict[str, Any]:
        """Make a resolution offer to the buyer (refund or replacement) (Disputes actions).

        offer_type: REFUND | REFUND_WITH_RETURN | REFUND_WITH_REPLACEMENT.
        """
        body: dict[str, Any] = {"note": note, "offer_type": offer_type}
        if offer_type != "REFUND_WITH_REPLACEMENT":
            body["offer_amount"] = {"value": f"{amount:.2f}", "currency_code": currency}
        return await self._http.request("POST", f"/v1/customer-disputes/disputes/{dispute_id}/make-offer", json=body)

    async def provide_evidence(self, dispute_id: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        """Provide evidence to PayPal for a dispute (Disputes actions)."""
        return await self._http.request(
            "POST", f"/v1/customer-disputes/disputes/{dispute_id}/provide-evidence", json={"evidences": evidence}
        )
