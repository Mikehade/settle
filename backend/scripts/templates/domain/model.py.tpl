from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Model


class __Entity__Model(Model):
    __tablename__ = "__table__"

    name: Mapped[str] = mapped_column(String(255))
