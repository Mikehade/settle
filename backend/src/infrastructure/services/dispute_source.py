"""
DisputeSource — the one interface the mediator reads disputes through.

Behind it: the real Customer Disputes API where the sandbox allows, and
a seeded fixture where it doesn't (creating a realistic test dispute in
sandbox is the project's known friction point). Mode is configurable:
  - "paypal"  : always the real API
  - "fixture" : always seeded (great for an offline demo / CI)
  - "auto"    : real API, falling back to fixtures on any failure, and
                always resolving FIXTURE-* ids from the seed set.

`get_case_file` assembles the full CaseFile (dispute + capture + tracking)
so the mediator is handed one clean, complete record.
"""
from typing import Any

from src.domain.core.constants.dispute_types import classify_reason
from src.domain.entities.case_file import CaseFile
from src.infrastructure.services.dispute_fixtures import DEMO_FIXTURES
from src.infrastructure.services.paypal_client import PayPalClient
from src.shared.logging import get_logger

logger = get_logger(__name__)


class DisputeSource:
    def __init__(self, paypal_client: PayPalClient, mode: str = "auto") -> None:
        self._client = paypal_client
        self._mode = mode

    async def list_open(self) -> list[dict[str, Any]]:
        if self._mode == "fixture":
            return [self._summary(cf) for cf in DEMO_FIXTURES.values()]
        try:
            raw = await self._client.list_disputes()
            items = raw.get("items", [])
            real = [
                {
                    "dispute_id": d.get("dispute_id"),
                    "status": (d.get("status") or "open").lower(),
                    "reason": d.get("reason"),
                    "source": "paypal",
                    "amount": float((d.get("dispute_amount", {}) or {}).get("value", 0) or 0),
                    "currency": (d.get("dispute_amount", {}) or {}).get("currency_code", "USD"),
                    "item": None,
                    "dispute_type": None,
                }
                for d in items
            ]
            if self._mode == "paypal":
                return real
            return real + [self._summary(cf) for cf in DEMO_FIXTURES.values()]
        except Exception as e:  # noqa: BLE001
            if self._mode == "paypal":
                raise
            logger.warning("list_disputes failed — fixtures only", extra={"event": "dispute_source.fallback", "error": str(e)})
            return [self._summary(cf) for cf in DEMO_FIXTURES.values()]

    async def get_case_file(self, dispute_id: str) -> CaseFile:
        if self._mode == "fixture" or dispute_id in DEMO_FIXTURES or dispute_id.startswith("FIXTURE-"):
            fixture = DEMO_FIXTURES.get(dispute_id)
            if fixture is None:
                raise KeyError(f"Unknown fixture dispute id: {dispute_id}")
            return CaseFile(**fixture)  # type: ignore[arg-type]
        try:
            return await self._assemble_from_paypal(dispute_id)
        except Exception as e:  # noqa: BLE001
            if self._mode == "paypal":
                raise
            logger.warning("assemble from PayPal failed — no fixture match", extra={"event": "dispute_source.assemble_error", "error": str(e)})
            raise

    # ---- Internals ---------------------------------------------------------
    @staticmethod
    def _summary(cf: dict[str, Any]) -> dict[str, Any]:
        return {
            "dispute_id": cf["dispute_id"],
            "status": "open",  # the source's view; MediationService overlays the DB status
            "reason": cf.get("reason_code"),
            "source": "fixture",
            "amount": cf.get("disputed_amount"),
            "currency": cf.get("currency", "USD"),
            "item": cf.get("item_name"),
            "dispute_type": cf.get("dispute_type"),
        }

    async def _assemble_from_paypal(self, dispute_id: str) -> CaseFile:
        dispute = await self._client.get_dispute(dispute_id)

        reason = dispute.get("reason")
        amount = dispute.get("dispute_amount", {}) or {}
        disputed_amount = float(amount.get("value", 0) or 0)
        currency = amount.get("currency_code", "USD")

        # Messages → buyer/seller complaint text + counts.
        buyer_msgs = [m["content"] for m in dispute.get("messages", []) if m.get("posted_by") == "BUYER"]
        seller_msgs = [m["content"] for m in dispute.get("messages", []) if m.get("posted_by") == "SELLER"]

        # Linked transaction / capture.
        txns = dispute.get("disputed_transactions", []) or []
        transaction_id = txns[0].get("seller_transaction_id") if txns else None
        capture_id = transaction_id  # in sandbox these commonly coincide; adjust if your flow differs

        # Tracking (best effort — missing is a valid, informative signal).
        tracking_status = "unknown"
        carrier = None
        tracking_number = None
        if transaction_id:
            try:
                tracking = await self._client.get_tracking(transaction_id)
                status_raw = (tracking.get("status") or "").upper()
                tracking_status = {"DELIVERED": "delivered", "SHIPPED": "in_transit", "ON_HOLD": "in_transit"}.get(status_raw, "unknown")
                carrier = tracking.get("carrier")
                tracking_number = tracking.get("tracking_number")
            except Exception:  # noqa: BLE001
                tracking_status = "none"

        return CaseFile(
            dispute_id=dispute_id,
            dispute_type=classify_reason(reason).value,
            reason_code=reason,
            buyer_complaint="\n".join(buyer_msgs) or dispute.get("reason", ""),
            seller_response="\n".join(seller_msgs),
            item_name=None,
            item_value=disputed_amount,
            disputed_amount=disputed_amount,
            currency=currency,
            transaction_id=transaction_id,
            capture_id=capture_id,
            tracking_status=tracking_status,  # type: ignore[arg-type]
            tracking_carrier=carrier,
            tracking_number=tracking_number,
            prior_refunds=0.0,
            buyer_message_count=len(buyer_msgs),
            seller_message_count=len(seller_msgs),
            raw={"dispute": dispute},
        )
