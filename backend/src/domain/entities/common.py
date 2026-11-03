from typing import Generic, TypedDict, TypeVar

T = TypeVar("T")


class Page(TypedDict, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
