import uuid
from datetime import UTC, datetime

from src.domain.core.constants.statuses import TERMINAL
from src.domain.entities.case_file import CaseFile
from src.domain.entities.common import Page
from src.domain.entities.dispute import Dispute
from src.domain.exceptions import NotFoundError
from src.domain.interfaces.repositories.disputes import DisputeRepositoryInterface
from src.domain.interfaces.uow import UnitOfWorkFactory
from src.shared.errors import ErrorCode
from src.shared.logging import get_logger

logger = get_logger(__name__)


def _parse_uuid(value: str | uuid.UUID) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _assert_owned(dispute: Dispute | None, seller_id: uuid.UUID | None) -> Dispute:
    """Return the dispute only if the caller owns it; otherwise 404 (we don't
    leak the existence of another seller's case)."""
    if dispute is None:
        raise NotFoundError(ErrorCode.DISPUTE_NOT_FOUND, "Dispute not found")
    if seller_id is not None and dispute.get("seller_id") is not None and dispute.get("seller_id") != seller_id:
        raise NotFoundError(ErrorCode.DISPUTE_NOT_FOUND, "Dispute not found")
    return dispute


class DisputeService:
    def __init__(self, disputes: DisputeRepositoryInterface, uow: UnitOfWorkFactory) -> None:
        self._disputes = disputes
        self._uow = uow

    async def record_from_case_file(self, case_file: CaseFile, *, seller_id: uuid.UUID | None, source: str, claim: bool = False) -> Dispute | None:
        """Record (or claim) a dispute as `mediating`.

        When `claim=True`, the write only succeeds if the case isn't already
        mediating/resolved/rejected; otherwise None is returned so the caller can
        raise a conflict instead of starting a second run on the same case."""
        fields: dict = {
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
        # Only (re)assign the seller when we actually have one, so a webhook that
        # can't resolve a seller never clears an existing owner.
        if seller_id is not None:
            fields["seller_id"] = seller_id
        only_if = {"open", "escalated", "failed"} if claim else None
        async with self._uow():
            dispute = await self._disputes.upsert(paypal_dispute_id=case_file["dispute_id"], fields=fields, only_if_status_in=only_if)
        if dispute is None:
            return None
        logger.info("Dispute recorded", extra={"event": "dispute.recorded", "dispute_id": str(dispute["id"]), "type": dispute["dispute_type"]})
        return dispute

    async def get(self, dispute_id: uuid.UUID, *, seller_id: uuid.UUID | None = None) -> Dispute:
        return _assert_owned(await self._disputes.get(dispute_id), seller_id)

    async def get_by_paypal(self, paypal_dispute_id: str, *, seller_id: uuid.UUID | None = None) -> Dispute:
        return _assert_owned(await self._disputes.get_by_paypal_id(paypal_dispute_id), seller_id)

    async def get_by_any_id(self, identifier: str, *, seller_id: uuid.UUID | None = None) -> Dispute:
        """Resolve a dispute by either its internal UUID or its PayPal/fixture id.

        The PayPal id is the canonical public identifier (the only one that
        exists before a case has ever been persisted); the UUID is accepted too
        for callers that already hold it."""
        as_uuid = _parse_uuid(identifier)
        dispute = await self._disputes.get(as_uuid) if as_uuid is not None else None
        if dispute is None:
            dispute = await self._disputes.get_by_paypal_id(str(identifier))
        return _assert_owned(dispute, seller_id)

    async def find_by_paypal(self, paypal_dispute_id: str) -> Dispute | None:
        """Unscoped best-effort lookup (used to reconcile the open list / webhooks)."""
        return await self._disputes.get_by_paypal_id(paypal_dispute_id)

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
        return await self._disputes.get_page(
            page=page, page_size=page_size, seller_id=seller_id,
            status=status, dispute_type=dispute_type, search=search, sort=sort, order=order,
        )

    async def set_status(
        self,
        dispute_id: uuid.UUID,
        *,
        status: str,
        outcome: str | None = None,
        refund_amount: float | None = None,
        confidence: float | None = None,
    ) -> None:
        """Move a dispute to a new status. `resolved_at` is stamped only for
        terminal states, so an `escalated` case waiting on the seller stays
        undated and is distinguishable from a `rejected` one."""
        fields: dict = {"status": status, "outcome": outcome, "refund_amount": refund_amount, "confidence": confidence}
        fields["resolved_at"] = datetime.now(UTC) if status in TERMINAL else None
        async with self._uow():
            await self._disputes.update(dispute_id, fields)
        logger.info("Dispute status set", extra={"event": "dispute.status", "dispute_id": str(dispute_id), "status": status, "outcome": outcome})

    # Backwards-compatible alias.
    async def mark_resolved(self, dispute_id: uuid.UUID, *, status: str, outcome: str | None, refund_amount: float | None, confidence: float | None) -> None:
        await self.set_status(dispute_id, status=status, outcome=outcome, refund_amount=refund_amount, confidence=confidence)
