import uuid
from typing import Protocol

from src.domain.entities.common import Page
from src.domain.entities.dispute import Dispute, DisputeUpdate


class DisputeRepositoryInterface(Protocol):
    async def upsert(self, *, paypal_dispute_id: str, fields: dict) -> Dispute: ...

    async def get(self, dispute_id: uuid.UUID) -> Dispute | None: ...

    async def get_by_paypal_id(self, paypal_dispute_id: str) -> Dispute | None: ...

    async def get_page(self, *, page: int, page_size: int, seller_id: uuid.UUID | None = None) -> Page[Dispute]: ...

    async def update(self, dispute_id: uuid.UUID, fields: DisputeUpdate) -> Dispute | None: ...
