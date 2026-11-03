"""The envelope every JSON response uses: status, code, message, data, errors, meta."""
from collections.abc import Mapping
from math import ceil
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str
    code: str | None = None


class Envelope(BaseModel, Generic[T]):
    """Use as `response_model=Envelope[OrderResponse]` so OpenAPI shows the real shape."""

    status: Literal["success", "error"] = "success"
    code: str = "OK"
    message: str = "OK"
    data: T | None = None
    errors: list[ErrorDetail] | None = None
    meta: dict[str, Any] | None = None


def success(data: Any = None, *, message: str = "OK", meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": "success", "code": "OK", "message": message, "data": data, "errors": None, "meta": meta}


def paginated(page: Mapping[str, Any], *, message: str = "OK") -> dict[str, Any]:
    """`page` has items, total, page, page_size (the repositories' Page dict)."""
    meta = {
        "page": page["page"],
        "page_size": page["page_size"],
        "total": page["total"],
        "total_pages": ceil(page["total"] / page["page_size"]) if page["page_size"] else 0,
    }
    return success(page["items"], message=message, meta=meta)


def error_body(
    code: str,
    message: str,
    *,
    errors: list[dict[str, Any]] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"status": "error", "code": code, "message": message, "data": None, "errors": errors, "meta": meta}
