import uuid

from sqlalchemy import select

from src.domain.entities.policy import FairnessPolicy, FairnessPolicyUpdate
from src.infrastructure.db.models.policy import FairnessPolicyModel
from src.infrastructure.repositories.base import BaseRepository


class SqlFairnessPolicyRepository(BaseRepository):
    async def get_by_seller(self, seller_id: uuid.UUID) -> FairnessPolicy | None:
        async with self.session() as s:
            row = (await s.execute(select(FairnessPolicyModel).where(FairnessPolicyModel.seller_id == seller_id))).scalar_one_or_none()
            return self._to_dict(row) if row else None

    async def upsert(self, *, seller_id: uuid.UUID, fields: FairnessPolicyUpdate) -> FairnessPolicy:
        async with self.session() as s:
            row = (await s.execute(select(FairnessPolicyModel).where(FairnessPolicyModel.seller_id == seller_id))).scalar_one_or_none()
            if row is None:
                row = FairnessPolicyModel(seller_id=seller_id)
                s.add(row)
            for key, value in fields.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            await s.flush()
            return self._to_dict(row)

    @staticmethod
    def _to_dict(row: FairnessPolicyModel) -> FairnessPolicy:
        return FairnessPolicy(
            id=row.id,
            seller_id=row.seller_id,
            rules_text=row.rules_text,
            confidence_threshold=row.confidence_threshold,
            human_in_loop_amount=row.human_in_loop_amount,
            partial_refund_ceiling=row.partial_refund_ceiling,
            auto_accept_max=row.auto_accept_max,
            always_refund_under=row.always_refund_under,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
