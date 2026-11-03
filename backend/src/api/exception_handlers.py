"""Maps exceptions to the response envelope. Raise errors; never build error responses by hand."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.domain.exceptions import (
    AppError,
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    ServiceUnavailableError,
)
from src.shared.errors import ErrorCode
from src.shared.logging import get_logger, get_request_id
from src.shared.responses import error_body

logger = get_logger(__name__)

STATUS_BY_ERROR: dict[type[AppError], int] = {
    BusinessRuleError: 400,
    AuthenticationError: 401,
    PermissionDeniedError: 403,
    NotFoundError: 404,
    ConflictError: 409,
    RateLimitedError: 429,
    ServiceUnavailableError: 503,
}

CODE_BY_HTTP_STATUS = {
    400: ErrorCode.COMMON_BAD_REQUEST,
    401: ErrorCode.AUTH_NOT_AUTHENTICATED,
    403: ErrorCode.AUTH_PERMISSION_DENIED,
    404: ErrorCode.COMMON_NOT_FOUND,
    405: ErrorCode.COMMON_METHOD_NOT_ALLOWED,
    409: ErrorCode.COMMON_CONFLICT,
    429: ErrorCode.COMMON_RATE_LIMITED,
}


def _status_for(exc: AppError) -> int:
    for cls in type(exc).__mro__:
        if cls in STATUS_BY_ERROR:
            return STATUS_BY_ERROR[cls]
    return 400


def _meta() -> dict:
    return {"request_id": get_request_id()}


def register_exception_handlers(app: FastAPI, *, expose_errors: bool = False) -> None:
    """`expose_errors` puts the real exception text in 500 responses (development only)."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        status = _status_for(exc)
        logger.log(
            40 if status >= 500 else 30,
            exc.message,
            extra={"event": "http.app_error", "code": exc.code, "status": status},
        )
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
        return JSONResponse(
            status_code=status,
            content=error_body(exc.code, exc.message, errors=exc.errors, meta=_meta()),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"], "code": e["type"]}
            for e in exc.errors()
        ]
        logger.warning("Validation error", extra={"event": "http.validation_error", "code": ErrorCode.COMMON_VALIDATION_ERROR, "errors": errors})
        return JSONResponse(
            status_code=422,
            content=error_body(ErrorCode.COMMON_VALIDATION_ERROR, "Validation error", errors=errors, meta=_meta()),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = CODE_BY_HTTP_STATUS.get(exc.status_code, ErrorCode.COMMON_INTERNAL_ERROR if exc.status_code >= 500 else ErrorCode.COMMON_BAD_REQUEST)
        message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, message, meta=_meta()),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", extra={"event": "http.unhandled_error", "code": ErrorCode.COMMON_INTERNAL_ERROR})
        message = f"{type(exc).__name__}: {exc}" if expose_errors else "An internal error occurred"
        request_id = get_request_id()
        return JSONResponse(
            status_code=500,
            content=error_body(ErrorCode.COMMON_INTERNAL_ERROR, message, meta={"request_id": request_id}),
            headers={"X-Request-ID": request_id} if request_id else None,
        )
