import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PolicyUpdateRequest(BaseModel):
    rules_text: str = Field(default="", max_length=4000, description="Plain-English fairness rules the mediator applies verbatim.")
    confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    human_in_loop_amount: float | None = Field(default=None, ge=0.0)
    partial_refund_ceiling: float | None = Field(default=None, ge=0.0)
    auto_accept_max: float | None = Field(default=None, ge=0.0)
    always_refund_under: float | None = Field(default=None, ge=0.0)


class PolicyResponse(BaseModel):
    id: uuid.UUID
    seller_id: uuid.UUID
    rules_text: str
    confidence_threshold: float | None = None
    human_in_loop_amount: float | None = None
    partial_refund_ceiling: float | None = None
    auto_accept_max: float | None = None
    always_refund_under: float | None = None
    created_at: datetime
    updated_at: datetime
