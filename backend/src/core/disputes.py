import uuid
from datetime import UTC, datetime

from src.domain.entities.case_file import CaseFile
from src.domain.entities.common import Page
from src.domain.entities.dispute import Dispute
from src.domain.exceptions import NotFoundError
from src.domain.interfaces.repositories.disputes import DisputeRepositoryInterface
from src.domain.interfaces.uow import UnitOfWorkFactory
from src.shared.errors import ErrorCode
from src.shared.logging import get_logger

logger = get_logger(__name__)


class DisputeService:
    def __init__(self, disputes: DisputeRepositoryInterface, uow: UnitOfWorkFactory) -> None:
        self._disputes = disputes
        self._uow = uow

    async def record_from_case_file(self, case_file: CaseFile, *, seller_id: uuid.UUID | None, source: str) -> Dispute:
        fields = {
            "seller_id": seller_id,
            "status": "mediating",
            "dispute_type": case_file.get("dispute_type"),
            "reason_code": case_file.get("reason_code"),
            "disputed_amount": case_file.get("disputed_amount", 0.0),
            "currency": case_file.get("currency", "USD"),
            "buyer_complaint": case_file.get("buyer_complaint", ""),
            "seller_response": case_file.get("seller_response", ""),
            "source": source,
            "case_file": dict(case_file),
        }
        async with self._uow():
            dispute = await self._disputes.upsert(paypal_dispute_id=case_file["dispute_id"], fields=fields)
        logger.info("Dispute recorded", extra={"event": "dispute.recorded", "dispute_id": str(dispute["id"]), "type": dispute["dispute_type"]})
        return dispute

    async def get(self, dispute_id: uuid.UUID) -> Dispute:
        dispute = await self._disputes.get(dispute_id)
        if dispute is None:
            raise NotFoundError(ErrorCode.DISPUTE_NOT_FOUND, "Dispute not found")
        return dispute

    async def get_by_paypal(self, paypal_dispute_id: str) -> Dispute:
        dispute = await self._disputes.get_by_paypal_id(paypal_dispute_id)
        if dispute is None:
            raise NotFoundError(ErrorCode.DISPUTE_NOT_FOUND, "Dispute not found")
        return dispute

    async def get_page(self, *, page: int, page_size: int, seller_id: uuid.UUID | None = None) -> Page[Dispute]:
        return await self._disputes.get_page(page=page, page_size=page_size, seller_id=seller_id)

    async def mark_resolved(self, dispute_id: uuid.UUID, *, status: str, outcome: str | None, refund_amount: float | None, confidence: float | None) -> None:
        async with self._uow():
            await self._disputes.update(
                dispute_id,
                {"status": status, "outcome": outcome, "refund_amount": refund_amount, "confidence": confidence, "resolved_at": datetime.now(UTC)},
            )
        logger.info("Dispute resolved", extra={"event": "dispute.resolved", "dispute_id": str(dispute_id), "status": status, "outcome": outcome})
