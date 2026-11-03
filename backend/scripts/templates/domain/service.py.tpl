import uuid

from src.domain.entities.common import Page
from src.domain.entities.__domain__ import __Entity__, __Entity__Update
from src.domain.exceptions import NotFoundError
from src.domain.interfaces.repositories.__domain__ import __Entity__RepositoryInterface
from src.domain.interfaces.uow import UnitOfWorkFactory
from src.shared.errors import ErrorCode
from src.shared.logging import get_logger

logger = get_logger(__name__)


class __Entity__Service:
    def __init__(self, __domain__: __Entity__RepositoryInterface, uow: UnitOfWorkFactory) -> None:
        self.___domain__ = __domain__
        self._uow = uow

    async def create(self, *, name: str) -> __Entity__:
        async with self._uow():
            __entity__ = await self.___domain__.create(name=name)
        logger.info("__Entity__ created", extra={"event": "__entity__.created", "__entity___id": str(__entity__["id"])})
        return __entity__

    async def get(self, __entity___id: uuid.UUID) -> __Entity__:
        __entity__ = await self.___domain__.get(__entity___id)
        if __entity__ is None:
            raise NotFoundError(ErrorCode.__ENTITY___NOT_FOUND, "__Entity__ not found")
        return __entity__

    async def get_page(self, *, page: int, page_size: int) -> Page[__Entity__]:
        return await self.___domain__.get_page(page=page, page_size=page_size)

    async def update(self, __entity___id: uuid.UUID, fields: __Entity__Update) -> __Entity__:
        async with self._uow():
            __entity__ = await self.___domain__.update(__entity___id, fields)
        if __entity__ is None:
            raise NotFoundError(ErrorCode.__ENTITY___NOT_FOUND, "__Entity__ not found")
        return __entity__

    async def delete(self, __entity___id: uuid.UUID) -> None:
        async with self._uow():
            deleted = await self.___domain__.delete(__entity___id)
        if not deleted:
            raise NotFoundError(ErrorCode.__ENTITY___NOT_FOUND, "__Entity__ not found")
        logger.info("__Entity__ deleted", extra={"event": "__entity__.deleted", "__entity___id": str(__entity___id)})
