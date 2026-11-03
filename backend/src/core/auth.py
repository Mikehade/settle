import uuid

from src.domain.entities.users import AccessToken, User
from src.domain.exceptions import AuthenticationError
from src.domain.interfaces.repositories.users import UserRepositoryInterface
from src.domain.interfaces.services import PasswordHasherInterface, TokenServiceInterface
from src.shared.errors import ErrorCode
from src.shared.logging import get_logger

logger = get_logger(__name__)


class AuthService:
    def __init__(
        self,
        users: UserRepositoryInterface,
        hasher: PasswordHasherInterface,
        tokens: TokenServiceInterface,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        # Verified against when the email is unknown, so response time does not reveal it.
        self._dummy_hash = hasher.hash("dummy-password-for-timing")

    async def login(self, *, email: str, password: str) -> AccessToken:
        user = await self._users.get_with_password(email.strip().lower())
        valid = self._hasher.verify(password, user["hashed_password"] if user else self._dummy_hash)
        if user is None or not valid:
            logger.warning("Login failed", extra={"event": "auth.login_failed"})
            raise AuthenticationError(ErrorCode.AUTH_INVALID_CREDENTIALS, "Invalid email or password")
        if not user["is_active"]:
            raise AuthenticationError(ErrorCode.USER_INACTIVE, "User is inactive")

        logger.info("Login succeeded", extra={"event": "auth.login", "user_id": str(user["id"])})
        return AccessToken(
            access_token=self._tokens.create_access_token(str(user["id"])),
            token_type="bearer",
            expires_in=self._tokens.access_ttl_seconds,
        )

    async def resolve_token(self, token: str) -> User:
        claims = self._tokens.decode(token)
        try:
            user_id = uuid.UUID(str(claims.get("sub")))
        except ValueError as exc:
            raise AuthenticationError(ErrorCode.AUTH_TOKEN_INVALID, "Invalid token") from exc
        user = await self._users.get(user_id)
        if user is None or not user["is_active"]:
            raise AuthenticationError(ErrorCode.AUTH_TOKEN_INVALID, "Invalid token")
        return user
