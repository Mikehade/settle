"""Typed errors raised by any layer. They know nothing about HTTP;
api/exception_handlers.py maps each class to a status code."""
from typing import Any

from src.shared.errors import ErrorCode


class AppError(Exception):
    default_code: str = ErrorCode.COMMON_BAD_REQUEST
    default_message: str = "Bad request"

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        *,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = str(code or self.default_code)
        self.message = message or self.default_message
        self.errors = errors
        super().__init__(self.message)


class BusinessRuleError(AppError):
    default_code = ErrorCode.COMMON_BAD_REQUEST
    default_message = "Request breaks a business rule"


class AuthenticationError(AppError):
    default_code = ErrorCode.AUTH_NOT_AUTHENTICATED
    default_message = "Not authenticated"


class PermissionDeniedError(AppError):
    default_code = ErrorCode.AUTH_PERMISSION_DENIED
    default_message = "Permission denied"


class NotFoundError(AppError):
    default_code = ErrorCode.COMMON_NOT_FOUND
    default_message = "Not found"


class ConflictError(AppError):
    default_code = ErrorCode.COMMON_CONFLICT
    default_message = "Conflict"


class RateLimitedError(AppError):
    default_code = ErrorCode.COMMON_RATE_LIMITED
    default_message = "Too many requests"


class ServiceUnavailableError(AppError):
    default_code = ErrorCode.COMMON_SERVICE_UNAVAILABLE
    default_message = "Service unavailable"
