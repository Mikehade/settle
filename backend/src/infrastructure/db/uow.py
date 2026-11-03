from types import TracebackType
from typing import Self

from src.infrastructure.db.session import Database, current_session


class UnitOfWork:
    """One transaction across every repository call inside `async with`.

    Nested use joins the outer transaction; only the outermost block commits.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self._session = None
        self._token = None
        self._nested = False

    async def __aenter__(self) -> Self:
        if current_session.get() is not None:
            self._nested = True
            return self
        self._session = self._db.session_factory()
        self._token = current_session.set(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if self._nested:
            return False
        try:
            if exc_type is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            current_session.reset(self._token)
            await self._session.close()
        return False
