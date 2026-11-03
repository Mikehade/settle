import uuid

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Model


class AuditEntryModel(Model):
    __tablename__ = "audit_entries"

    dispute_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("disputes.id"), index=True)
    paypal_dispute_id: Mapped[str] = mapped_column(String(128), index=True)
    case_file: Mapped[dict] = mapped_column(JSON, default=dict)
    decision: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[str | None] = mapped_column(String(32), default=None)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    gate: Mapped[str] = mapped_column(String(16), default="escalate")
    action_taken: Mapped[str] = mapped_column(String(255), default="")
    executed: Mapped[bool] = mapped_column(Boolean, default=False)
    paypal_result: Mapped[dict] = mapped_column(JSON, default=dict)
    engine: Mapped[str] = mapped_column(String(16), default="llm_tools")
    served_by: Mapped[str | None] = mapped_column(String(255), default=None)
