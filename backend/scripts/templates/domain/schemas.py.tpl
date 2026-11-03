import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class __Entity__CreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class __Entity__UpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class __Entity__Response(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
