import uuid
from datetime import datetime
from typing import TypedDict


class User(TypedDict):
    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


class UserWithPassword(User):
    """Only for credential checks. Never returned to the API."""

    hashed_password: str


class AccessToken(TypedDict):
    access_token: str
    token_type: str
    expires_in: int
