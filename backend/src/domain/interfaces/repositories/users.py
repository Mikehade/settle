import uuid
from typing import Protocol

from src.domain.entities.users import User, UserWithPassword


class UserRepositoryInterface(Protocol):
    async def get(self, user_id: uuid.UUID) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...

    async def get_with_password(self, email: str) -> UserWithPassword | None: ...

    async def create(
        self,
        *,
        email: str,
        hashed_password: str,
        full_name: str | None = None,
        is_superuser: bool = False,
    ) -> User: ...

    async def set_password(self, user_id: uuid.UUID, hashed_password: str) -> None: ...
