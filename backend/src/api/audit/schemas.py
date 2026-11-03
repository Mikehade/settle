import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditEntryResponse(BaseModel):
    id: uuid.UUID
    dispute_id: uuid.UUID
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
