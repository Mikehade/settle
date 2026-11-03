"""The structured case file the mediator reasons over.

The backend assembles this from PayPal data BEFORE the model reasons —
the model never fetches ad hoc, it is handed one clean, complete record.
A TypedDict so it crosses layers without pulling in ORM or pydantic.
"""
from typing import Any, Literal, TypedDict

TrackingStatus = Literal["delivered", "in_transit", "not_shipped", "none", "unknown"]


class CaseFile(TypedDict, total=False):
    dispute_id: str                 # PayPal dispute id (or seeded fixture id)
    dispute_type: str               # DisputeType value (best-effort pre-classification)
    reason_code: str | None         # raw PayPal reason code
    buyer_complaint: str            # the buyer's written complaint
    seller_response: str            # the seller's written response (may be empty)
    item_name: str | None
    item_value: float | None
    disputed_amount: float          # the amount in dispute
    currency: str                   # ISO 4217, e.g. "USD"
    transaction_id: str | None
    capture_id: str | None          # the capture a refund would target
    tracking_status: TrackingStatus
    tracking_carrier: str | None
    tracking_number: str | None
    prior_refunds: float            # total already refunded on this transaction
    buyer_message_count: int
    seller_message_count: int
    raw: dict[str, Any]             # the untouched PayPal payloads, for the audit trail
