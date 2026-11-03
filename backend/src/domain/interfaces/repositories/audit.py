import uuid
from typing import Protocol

from src.domain.entities.audit import AuditEntry
from src.domain.entities.common import Page


class AuditRepositoryInterface(Protocol):
    async def create(self, *, fields: dict) -> AuditEntry: ...

    async def get_page(self, *, page: int, page_size: int) -> Page[AuditEntry]: ...

    async def list_for_dispute(self, dispute_id: uuid.UUID) -> list[AuditEntry]: ...
