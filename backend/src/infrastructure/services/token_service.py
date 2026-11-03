from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from src.domain.exceptions import AuthenticationError
from src.shared.errors import ErrorCode


class JwtTokenService:
    def __init__(self, *, secret_key: str, algorithm: str = "HS256", access_ttl_seconds: int = 1800) -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._access_ttl_seconds = access_ttl_seconds

    @property
    def access_ttl_seconds(self) -> int:
        return self._access_ttl_seconds

    def create_access_token(self, subject: str, claims: dict[str, Any] | None = None) -> str:
        now = datetime.now(UTC)
        payload = {
            **(claims or {}),
            "sub": subject,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(seconds=self._access_ttl_seconds),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def decode(self, token: str) -> dict[str, Any]:
        try:
            claims = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError(ErrorCode.AUTH_TOKEN_EXPIRED, "Token expired") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationError(ErrorCode.AUTH_TOKEN_INVALID, "Invalid token") from exc
        if claims.get("type") != "access":
            raise AuthenticationError(ErrorCode.AUTH_TOKEN_INVALID, "Invalid token")
        return claims
