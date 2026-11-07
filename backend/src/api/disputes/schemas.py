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
    case_file: dict = {}          # tracking, item, transaction, prior refunds — no audit lookup needed
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class OpenDisputeSummary(BaseModel):
    dispute_id: str
    status: str
    reason: str | None = None
    source: str | None = None
    amount: float | None = None
    currency: str | None = None
    item: str | None = None
    dispute_type: str | None = None
    updated_at: datetime | None = None
    resolved_at: datetime | None = None


class DisputePreviewResponse(BaseModel):
    dispute_id: str
    status: str
    case_file: dict


class MediationSummaryResponse(BaseModel):
    dispute_id: str
    gate: str | None = None
    executed: bool = False
    action_taken: str = ""
    rationale: str | None = None
    recommendation: str | None = None
    decision: dict | None = None
    error: str | None = None


class ActionResultResponse(BaseModel):
    """Result of a money-moving seller action (approve/reject) over REST."""
    dispute_id: str
    executed: bool = False
    action_taken: str = ""
    rationale: str | None = None
    decision: dict | None = None
