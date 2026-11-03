import uuid

from sqlalchemy import select

from src.domain.entities.common import Page
from src.domain.entities.__domain__ import __Entity__, __Entity__Update
from src.infrastructure.db.models.__domain__ import __Entity__Model
from src.infrastructure.repositories.base import BaseRepository


class Sql__Entity__Repository(BaseRepository):
    async def create(self, *, name: str) -> __Entity__:
        async with self.session() as s:
            row = __Entity__Model(name=name)
            s.add(row)
            await s.flush()
            return self._to_dict(row)

    async def get(self, __entity___id: uuid.UUID) -> __Entity__ | None:
        async with self.session() as s:
            row = await s.get(__Entity__Model, __entity___id)
            return self._to_dict(row) if row else None

    async def get_page(self, *, page: int, page_size: int) -> Page[__Entity__]:
        async with self.session() as s:
            stmt = select(__Entity__Model).order_by(__Entity__Model.created_at.desc())
            rows, total = await self._paginate(s, stmt, page=page, page_size=page_size)
            return Page(items=[self._to_dict(r) for r in rows], total=total, page=page, page_size=page_size)

    async def update(self, __entity___id: uuid.UUID, fields: __Entity__Update) -> __Entity__ | None:
        async with self.session() as s:
            row = await s.get(__Entity__Model, __entity___id)
            if row is None:
                return None
            for key, value in fields.items():
                setattr(row, key, value)
            await s.flush()
            return self._to_dict(row)

    async def delete(self, __entity___id: uuid.UUID) -> bool:
        async with self.session() as s:
            row = await s.get(__Entity__Model, __entity___id)
            if row is None:
                return False
            await s.delete(row)
            return True

    @staticmethod
    def _to_dict(row: __Entity__Model) -> __Entity__:
        return __Entity__(id=row.id, name=row.name, created_at=row.created_at, updated_at=row.updated_at)
