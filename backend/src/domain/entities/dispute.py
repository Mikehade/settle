"""Persisted dispute case record (one row per dispute Settle has seen)."""
import uuid
from datetime import datetime
from typing import Any, TypedDict


class Dispute(TypedDict, total=False):
    id: uuid.UUID
    seller_id: uuid.UUID | None     # owning AuthProfile (the seller)
    paypal_dispute_id: str          # PayPal dispute id / seeded fixture id
    status: str                     # open | mediating | resolved | escalated | rejected | failed (see constants.statuses)
    dispute_type: str               # DisputeType value
    reason_code: str | None
    disputed_amount: float
    currency: str
    buyer_complaint: str
    seller_response: str
    outcome: str | None             # final Outcome value once resolved
    refund_amount: float | None
    confidence: float | None
    source: str                     # "paypal" | "fixture"
    case_file: dict[str, Any]       # the assembled CaseFile (snapshot)
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class DisputeUpdate(TypedDict, total=False):
    seller_id: uuid.UUID | None
    status: str
    outcome: str | None
    refund_amount: float | None
    confidence: float | None
    seller_response: str
    resolved_at: datetime | None
