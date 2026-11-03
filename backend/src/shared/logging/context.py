"""Per-request context carried by every log line without passing it around."""
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)


def get_request_id() -> str | None:
    return request_id_var.get()


def bind_user(user_id: object) -> None:
    """Attach the authenticated user to the current request's logs."""
    user_id_var.set(str(user_id) if user_id is not None else None)
