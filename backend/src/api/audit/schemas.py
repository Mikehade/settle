import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditEntryResponse(BaseModel):
    """Full audit entry — includes the heavy case_file (with raw PayPal payloads)
    and the PayPal result. Used for a single dispute's trail / detail view."""
    id: uuid.UUID
    dispute_id: uuid.UUID
    seller_id: uuid.UUID | None = None
    paypal_dispute_id: str
    case_file: dict
    decision: dict
    outcome: str | None = None
    confidence: float
    gate: str
    action_taken: str
    executed: bool
    paypal_result: dict
    engine: str
    served_by: str | None = None
    created_at: datetime


class AuditEntryListItem(BaseModel):
    """Lean row for the audit list: omits case_file (raw PayPal payloads) and
    paypal_result so the list stays light. Fetch the full entry per dispute."""
    id: uuid.UUID
    dispute_id: uuid.UUID
    paypal_dispute_id: str
    outcome: str | None = None
    confidence: float
    gate: str
    action_taken: str
    executed: bool
    engine: str
    served_by: str | None = None
    created_at: datetime
