from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.session import Database, current_session


class BaseRepository:
    """Session handling for repositories.

    Inside a UnitOfWork the active session is reused (the UoW commits).
    Outside one, each call gets its own short-lived session that commits on exit.
    Repositories never call commit() themselves and never return ORM objects.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        active = current_session.get()
        if active is not None:
            yield active
            return
        async with self._db.session() as session:
            yield session

    @staticmethod
    async def _paginate(
        session: AsyncSession, stmt: Select[Any], *, page: int, page_size: int
    ) -> tuple[Sequence[Any], int]:
        total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
        rows = (await session.scalars(stmt.limit(page_size).offset((page - 1) * page_size))).all()
        return rows, int(total or 0)
