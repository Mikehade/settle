"""Core tested with fakes: no database, no container. This is what DI buys."""
import uuid
from datetime import UTC, datetime

import pytest

from src.core.auth import AuthService
from src.core.users import UserService
from src.domain.entities.users import User, UserWithPassword
from src.domain.exceptions import AuthenticationError, BusinessRuleError, ConflictError
from src.shared.errors import ErrorCode


class FakeUserRepository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, UserWithPassword] = {}

    async def get(self, user_id):
        row = self.rows.get(user_id)
        return self._public(row) if row else None

    async def get_by_email(self, email):
        row = next((r for r in self.rows.values() if r["email"] == email), None)
        return self._public(row) if row else None

    async def get_with_password(self, email):
        return next((r for r in self.rows.values() if r["email"] == email), None)

    async def create(self, *, email, hashed_password, full_name=None, is_superuser=False) -> User:
        now = datetime.now(UTC)
        row = UserWithPassword(
            id=uuid.uuid4(), email=email, full_name=full_name, is_active=True,
            is_superuser=is_superuser, created_at=now, updated_at=now, hashed_password=hashed_password,
        )
        self.rows[row["id"]] = row
        return self._public(row)

    async def set_password(self, user_id, hashed_password):
        self.rows[user_id]["hashed_password"] = hashed_password

    @staticmethod
    def _public(row) -> User:
        return User(**{k: v for k, v in row.items() if k != "hashed_password"})


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, hashed: str) -> bool:
        return hashed == f"hashed:{password}"


class FakeTokens:
    access_ttl_seconds = 60

    def create_access_token(self, subject, claims=None):
        return f"token:{subject}"

    def decode(self, token):
        if not token.startswith("token:"):
            raise AuthenticationError(ErrorCode.AUTH_TOKEN_INVALID)
        return {"sub": token.removeprefix("token:")}


class FakeUnitOfWork:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def users(repo) -> UserService:
    return UserService(users=repo, hasher=FakeHasher(), uow=FakeUnitOfWork)


@pytest.fixture
def auth(repo) -> AuthService:
    return AuthService(users=repo, hasher=FakeHasher(), tokens=FakeTokens())


async def test_create_user_normalises_email_and_hashes_password(users, repo):
    user = await users.create_user(email="  Ada@Example.com ", password="s3cret-pass")
    assert user["email"] == "ada@example.com"
    assert repo.rows[user["id"]]["hashed_password"] == "hashed:s3cret-pass"
    assert "hashed_password" not in user


async def test_create_user_rejects_duplicate_email(users):
    await users.create_user(email="ada@example.com", password="s3cret-pass")
    with pytest.raises(ConflictError) as err:
        await users.create_user(email="ADA@example.com", password="s3cret-pass")
    assert err.value.code == ErrorCode.USER_EMAIL_TAKEN


async def test_create_user_rejects_short_password(users):
    with pytest.raises(BusinessRuleError):
        await users.create_user(email="ada@example.com", password="short")


async def test_login_and_resolve_token(users, auth):
    created = await users.create_user(email="ada@example.com", password="s3cret-pass")
    token = await auth.login(email="ada@example.com", password="s3cret-pass")
    assert (await auth.resolve_token(token["access_token"]))["id"] == created["id"]


async def test_login_wrong_password(users, auth):
    await users.create_user(email="ada@example.com", password="s3cret-pass")
    with pytest.raises(AuthenticationError) as err:
        await auth.login(email="ada@example.com", password="wrong-pass")
    assert err.value.code == ErrorCode.AUTH_INVALID_CREDENTIALS
