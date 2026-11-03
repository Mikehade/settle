"""One Database per physical database. Repositories get the Database, never an engine or URL."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.shared.logging import get_logger

logger = get_logger(__name__)

# The session of the active UnitOfWork, if any. Repositories join it automatically.
current_session: ContextVar[AsyncSession | None] = ContextVar("current_session", default=None)


class Database:
    name = "database"

    def __init__(
        self,
        url: str,
        *,
        echo: bool = False,
        pool_size: int = 10,
        max_overflow: int = 10,
        **engine_kwargs: Any,
    ) -> None:
        options: dict[str, Any] = {"echo": echo, "pool_pre_ping": True}
        if not url.startswith("sqlite"):
            options.update(pool_size=pool_size, max_overflow=max_overflow, pool_recycle=1800)
        options.update(engine_kwargs)

        self._engine = create_async_engine(url, **options)
        self._session_factory = async_sessionmaker(
            bind=self._engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """A standalone session: commits on success, rolls back on error."""
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def ping(self) -> bool:
        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    async def dispose(self) -> None:
        await self._engine.dispose()
        logger.info("Database engine disposed", extra={"event": "db.disposed"})
