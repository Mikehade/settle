from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Model


class UserModel(Model):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    # The seller's PayPal merchant/payee id — lets an inbound webhook resolve
    # which seller a dispute belongs to (so their policy applies and it shows
    # up on their dashboard). Nullable: not every account has one wired yet.
    paypal_merchant_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, default=None)
