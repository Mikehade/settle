import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Model


class DisputeModel(Model):
    __tablename__ = "disputes"

    seller_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), index=True, default=None)
    paypal_dispute_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    dispute_type: Mapped[str] = mapped_column(String(32), default="unauthorized_or_other")
    reason_code: Mapped[str | None] = mapped_column(String(64), default=None)
    disputed_amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    buyer_complaint: Mapped[str] = mapped_column(Text, default="")
    seller_response: Mapped[str] = mapped_column(Text, default="")
    outcome: Mapped[str | None] = mapped_column(String(32), default=None)
    refund_amount: Mapped[float | None] = mapped_column(Float, default=None)
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    source: Mapped[str] = mapped_column(String(16), default="paypal")
    case_file: Mapped[dict] = mapped_column(JSON, default=dict)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
