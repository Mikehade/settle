from src.domain.entities.users import User
from src.domain.exceptions import BusinessRuleError, ConflictError, NotFoundError
from src.domain.interfaces.repositories.users import UserRepositoryInterface
from src.domain.interfaces.services import PasswordHasherInterface
from src.domain.interfaces.uow import UnitOfWorkFactory
from src.shared.errors import ErrorCode
from src.shared.logging import get_logger

logger = get_logger(__name__)

MIN_PASSWORD_LENGTH = 8


class UserService:
    def __init__(
        self,
        users: UserRepositoryInterface,
        hasher: PasswordHasherInterface,
        uow: UnitOfWorkFactory,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._uow = uow

    async def create_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str | None = None,
        is_superuser: bool = False,
    ) -> User:
        email = email.strip().lower()
        self._check_password(password)
        async with self._uow():
            if await self._users.get_by_email(email):
                raise ConflictError(ErrorCode.USER_EMAIL_TAKEN, "A user with this email already exists")
            user = await self._users.create(
                email=email,
                hashed_password=self._hasher.hash(password),
                full_name=full_name,
                is_superuser=is_superuser,
            )
        logger.info("User created", extra={"event": "user.created", "user_id": str(user["id"]), "is_superuser": is_superuser})
        return user

    async def get_by_merchant_id(self, merchant_id: str) -> User | None:
        """Resolve the seller that owns a PayPal merchant/payee id (webhook path)."""
        if not merchant_id:
            return None
        return await self._users.get_by_merchant_id(merchant_id)

    async def change_password(self, *, email: str, new_password: str) -> None:
        self._check_password(new_password)
        async with self._uow():
            user = await self._users.get_by_email(email.strip().lower())
            if user is None:
                raise NotFoundError(ErrorCode.USER_NOT_FOUND, "User not found")
            await self._users.set_password(user["id"], self._hasher.hash(new_password))
        logger.info("Password changed", extra={"event": "user.password_changed", "user_id": str(user["id"])})

    @staticmethod
    def _check_password(password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise BusinessRuleError(
                ErrorCode.USER_WEAK_PASSWORD, f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
            )
