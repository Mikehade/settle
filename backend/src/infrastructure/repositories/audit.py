import uuid

from sqlalchemy import select

from src.domain.entities.audit import AuditEntry
from src.domain.entities.common import Page
from src.infrastructure.db.models.audit import AuditEntryModel
from src.infrastructure.repositories.base import BaseRepository


class SqlAuditRepository(BaseRepository):
    async def create(self, *, fields: dict) -> AuditEntry:
        async with self.session() as s:
            row = AuditEntryModel(**{k: v for k, v in fields.items() if hasattr(AuditEntryModel, k)})
            s.add(row)
            await s.flush()
            return self._to_dict(row)

    async def get_page(
        self,
        *,
        page: int,
        page_size: int,
        seller_id: uuid.UUID | None = None,
        outcome: str | None = None,
        gate: str | None = None,
    ) -> Page[AuditEntry]:
        async with self.session() as s:
            stmt = select(AuditEntryModel)
            if seller_id is not None:
                stmt = stmt.where(AuditEntryModel.seller_id == seller_id)
            if outcome:
                stmt = stmt.where(AuditEntryModel.outcome == outcome)
            if gate:
                stmt = stmt.where(AuditEntryModel.gate == gate)
            stmt = stmt.order_by(AuditEntryModel.created_at.desc())
            rows, total = await self._paginate(s, stmt, page=page, page_size=page_size)
            return Page(items=[self._to_dict(r) for r in rows], total=total, page=page, page_size=page_size)

    async def list_for_dispute(self, dispute_id: uuid.UUID, *, seller_id: uuid.UUID | None = None) -> list[AuditEntry]:
        async with self.session() as s:
            stmt = select(AuditEntryModel).where(AuditEntryModel.dispute_id == dispute_id)
            if seller_id is not None:
                stmt = stmt.where(AuditEntryModel.seller_id == seller_id)
            rows = (await s.execute(stmt.order_by(AuditEntryModel.created_at.desc()))).scalars().all()
            return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: AuditEntryModel) -> AuditEntry:
        return AuditEntry(
            id=row.id,
            dispute_id=row.dispute_id,
            seller_id=row.seller_id,
            paypal_dispute_id=row.paypal_dispute_id,
            case_file=row.case_file or {},
            decision=row.decision or {},
            outcome=row.outcome,
            confidence=row.confidence,
            gate=row.gate,
            action_taken=row.action_taken,
            executed=row.executed,
            paypal_result=row.paypal_result or {},
            engine=row.engine,
            served_by=row.served_by,
            created_at=row.created_at,
        )
