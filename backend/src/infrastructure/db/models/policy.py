import uuid

from sqlalchemy import Float, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Model


class FairnessPolicyModel(Model):
    __tablename__ = "fairness_policies"

    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), unique=True, index=True)
    rules_text: Mapped[str] = mapped_column(Text, default="")
    confidence_threshold: Mapped[float | None] = mapped_column(Float, default=None)
    human_in_loop_amount: Mapped[float | None] = mapped_column(Float, default=None)
    partial_refund_ceiling: Mapped[float | None] = mapped_column(Float, default=None)
    auto_accept_max: Mapped[float | None] = mapped_column(Float, default=None)
    always_refund_under: Mapped[float | None] = mapped_column(Float, default=None)
