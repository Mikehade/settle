import uuid
from typing import Protocol

from src.domain.entities.common import Page
from src.domain.entities.__domain__ import __Entity__, __Entity__Update


class __Entity__RepositoryInterface(Protocol):
    async def create(self, *, name: str) -> __Entity__: ...

    async def get(self, __entity___id: uuid.UUID) -> __Entity__ | None: ...

    async def get_page(self, *, page: int, page_size: int) -> Page[__Entity__]: ...

    async def update(self, __entity___id: uuid.UUID, fields: __Entity__Update) -> __Entity__ | None: ...

    async def delete(self, __entity___id: uuid.UUID) -> bool: ...
