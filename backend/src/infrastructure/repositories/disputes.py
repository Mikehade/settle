import uuid

from sqlalchemy import or_, select

from src.domain.entities.common import Page
from src.domain.entities.dispute import Dispute, DisputeUpdate
from src.infrastructure.db.models.dispute import DisputeModel
from src.infrastructure.repositories.base import BaseRepository

_SORTABLE = {"created_at", "updated_at", "disputed_amount", "status", "resolved_at"}


class SqlDisputeRepository(BaseRepository):
    async def upsert(self, *, paypal_dispute_id: str, fields: dict, only_if_status_in: set[str] | None = None) -> Dispute | None:
        """Create or update a dispute row.

        If `only_if_status_in` is given, an existing row is updated only when its
        current status is in that set; otherwise the row is left untouched and
        None is returned (the caller treats that as a claim conflict). The select
        takes a row lock on databases that support it, so the check-and-set is
        atomic — this is the concurrency guard against two runs of one case.
        """
        async with self.session() as s:
            stmt = select(DisputeModel).where(DisputeModel.paypal_dispute_id == paypal_dispute_id)
            if not str(s.bind.dialect.name).startswith("sqlite"):
                stmt = stmt.with_for_update()
            row = (await s.execute(stmt)).scalar_one_or_none()
            if row is None:
                row = DisputeModel(paypal_dispute_id=paypal_dispute_id)
                s.add(row)
            elif only_if_status_in is not None and row.status not in only_if_status_in:
                return None
            for key, value in fields.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            await s.flush()
            return self._to_dict(row)

    async def get(self, dispute_id: uuid.UUID) -> Dispute | None:
        async with self.session() as s:
            row = await s.get(DisputeModel, dispute_id)
            return self._to_dict(row) if row else None

    async def get_by_paypal_id(self, paypal_dispute_id: str) -> Dispute | None:
        async with self.session() as s:
            row = (await s.execute(select(DisputeModel).where(DisputeModel.paypal_dispute_id == paypal_dispute_id))).scalar_one_or_none()
            return self._to_dict(row) if row else None

    async def get_page(
        self,
        *,
        page: int,
        page_size: int,
        seller_id: uuid.UUID | None = None,
        status: str | None = None,
        dispute_type: str | None = None,
        search: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> Page[Dispute]:
        async with self.session() as s:
            stmt = select(DisputeModel)
            if seller_id is not None:
                stmt = stmt.where(DisputeModel.seller_id == seller_id)
            if status:
                stmt = stmt.where(DisputeModel.status == status)
            if dispute_type:
                stmt = stmt.where(DisputeModel.dispute_type == dispute_type)
            if search:
                like = f"%{search}%"
                stmt = stmt.where(or_(DisputeModel.paypal_dispute_id.ilike(like), DisputeModel.buyer_complaint.ilike(like)))
            sort_col = getattr(DisputeModel, sort if sort in _SORTABLE else "created_at")
            stmt = stmt.order_by(sort_col.asc() if order == "asc" else sort_col.desc())
            rows, total = await self._paginate(s, stmt, page=page, page_size=page_size)
            return Page(items=[self._to_dict(r) for r in rows], total=total, page=page, page_size=page_size)

    async def update(self, dispute_id: uuid.UUID, fields: DisputeUpdate) -> Dispute | None:
        async with self.session() as s:
            row = await s.get(DisputeModel, dispute_id)
            if row is None:
                return None
            for key, value in fields.items():
                setattr(row, key, value)
            await s.flush()
            return self._to_dict(row)

    @staticmethod
    def _to_dict(row: DisputeModel) -> Dispute:
        return Dispute(
            id=row.id,
            seller_id=row.seller_id,
            paypal_dispute_id=row.paypal_dispute_id,
            status=row.status,
            dispute_type=row.dispute_type,
            reason_code=row.reason_code,
            disputed_amount=row.disputed_amount,
            currency=row.currency,
            buyer_complaint=row.buyer_complaint,
            seller_response=row.seller_response,
            outcome=row.outcome,
            refund_amount=row.refund_amount,
            confidence=row.confidence,
            source=row.source,
            case_file=row.case_file or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
            resolved_at=row.resolved_at,
        )
