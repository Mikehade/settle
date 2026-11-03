import uuid
from datetime import datetime
from typing import TypedDict


class __Entity__(TypedDict):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class __Entity__Update(TypedDict, total=False):
    name: str
