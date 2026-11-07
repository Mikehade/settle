import uuid

from sqlalchemy import select, update

from src.domain.entities.users import User, UserWithPassword
from src.infrastructure.db.models.users import UserModel
from src.infrastructure.repositories.base import BaseRepository


class SqlUserRepository(BaseRepository):
    async def get(self, user_id: uuid.UUID) -> User | None:
        async with self.session() as s:
            row = await s.get(UserModel, user_id)
            return self._to_dict(row) if row else None

    async def get_by_email(self, email: str) -> User | None:
        async with self.session() as s:
            row = await s.scalar(select(UserModel).where(UserModel.email == email))
            return self._to_dict(row) if row else None

    async def get_by_merchant_id(self, merchant_id: str) -> User | None:
        async with self.session() as s:
            row = await s.scalar(select(UserModel).where(UserModel.paypal_merchant_id == merchant_id))
            return self._to_dict(row) if row else None

    async def get_with_password(self, email: str) -> UserWithPassword | None:
        async with self.session() as s:
            row = await s.scalar(select(UserModel).where(UserModel.email == email))
            if row is None:
                return None
            return UserWithPassword(**self._to_dict(row), hashed_password=row.hashed_password)

    async def create(
        self,
        *,
        email: str,
        hashed_password: str,
        full_name: str | None = None,
        is_superuser: bool = False,
    ) -> User:
        async with self.session() as s:
            row = UserModel(
                email=email,
                hashed_password=hashed_password,
                full_name=full_name,
                is_superuser=is_superuser,
                is_active=True,
            )
            s.add(row)
            await s.flush()
            return self._to_dict(row)

    async def set_password(self, user_id: uuid.UUID, hashed_password: str) -> None:
        async with self.session() as s:
            await s.execute(update(UserModel).where(UserModel.id == user_id).values(hashed_password=hashed_password))

    @staticmethod
    def _to_dict(row: UserModel) -> User:
        return User(
            id=row.id,
            email=row.email,
            full_name=row.full_name,
            is_active=row.is_active,
            is_superuser=row.is_superuser,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
