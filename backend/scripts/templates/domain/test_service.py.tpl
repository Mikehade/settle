"""__Entity__Service tested with an in-memory fake repository: no database, no container."""
import uuid
from datetime import UTC, datetime

import pytest

from src.core.__domain__ import __Entity__Service
from src.domain.entities.common import Page
from src.domain.entities.__domain__ import __Entity__
from src.domain.exceptions import NotFoundError


class Fake__Entity__Repository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, __Entity__] = {}

    async def create(self, *, name):
        now = datetime.now(UTC)
        row = __Entity__(id=uuid.uuid4(), name=name, created_at=now, updated_at=now)
        self.rows[row["id"]] = row
        return row

    async def get(self, __entity___id):
        return self.rows.get(__entity___id)

    async def get_page(self, *, page, page_size):
        items = list(self.rows.values())
        start = (page - 1) * page_size
        return Page(items=items[start:start + page_size], total=len(items), page=page, page_size=page_size)

    async def update(self, __entity___id, fields):
        row = self.rows.get(__entity___id)
        if row is not None:
            row.update(fields)
        return row

    async def delete(self, __entity___id):
        return self.rows.pop(__entity___id, None) is not None


class FakeUnitOfWork:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def service() -> __Entity__Service:
    return __Entity__Service(__domain__=Fake__Entity__Repository(), uow=FakeUnitOfWork)


async def test_create_and_get(service):
    created = await service.create(name="first")
    assert (await service.get(created["id"]))["name"] == "first"


async def test_get_missing_raises_not_found(service):
    with pytest.raises(NotFoundError):
        await service.get(uuid.uuid4())


async def test_update(service):
    created = await service.create(name="first")
    updated = await service.update(created["id"], {"name": "second"})
    assert updated["name"] == "second"


async def test_delete(service):
    created = await service.create(name="first")
    await service.delete(created["id"])
    with pytest.raises(NotFoundError):
        await service.get(created["id"])
