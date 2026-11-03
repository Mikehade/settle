from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self


class UnitOfWorkInterface(Protocol):
    """`async with uow():` - every repository call inside shares one transaction."""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


UnitOfWorkFactory = Callable[[], UnitOfWorkInterface]
