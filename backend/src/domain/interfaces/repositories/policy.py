import uuid
from typing import Protocol

from src.domain.entities.policy import FairnessPolicy, FairnessPolicyUpdate


class FairnessPolicyRepositoryInterface(Protocol):
    async def get_by_seller(self, seller_id: uuid.UUID) -> FairnessPolicy | None: ...

    async def upsert(self, *, seller_id: uuid.UUID, fields: FairnessPolicyUpdate) -> FairnessPolicy: ...
