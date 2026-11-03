import uuid
from datetime import datetime

from pydantic import BaseModel


class DisputeResponse(BaseModel):
    id: uuid.UUID
    seller_id: uuid.UUID | None = None
    paypal_dispute_id: str
    status: str
    dispute_type: str
    reason_code: str | None = None
    disputed_amount: float
    currency: str
    buyer_complaint: str
    seller_response: str
    outcome: str | None = None
    refund_amount: float | None = None
    confidence: float | None = None
    source: str
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class OpenDisputeSummary(BaseModel):
    dispute_id: str
    status: str
    reason: str | None = None
    source: str | None = None


class MediationSummaryResponse(BaseModel):
    dispute_id: str
    gate: str | None = None
    executed: bool = False
    action_taken: str = ""
    rationale: str | None = None
    recommendation: str | None = None
    decision: dict | None = None
    error: str | None = None
