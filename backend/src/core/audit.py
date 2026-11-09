import uuid

from src.domain.entities.audit import AuditEntry
from src.domain.entities.common import Page
from src.domain.interfaces.repositories.audit import AuditRepositoryInterface
from src.domain.interfaces.uow import UnitOfWorkFactory
from src.shared.logging import get_logger

logger = get_logger(__name__)


class AuditService:
    def __init__(self, audit: AuditRepositoryInterface, uow: UnitOfWorkFactory) -> None:
        self._audit = audit
        self._uow = uow

    async def record(self, *, dispute_id: uuid.UUID, paypal_dispute_id: str, case_file: dict, decision: dict, result: dict, engine: str, served_by: str | None, seller_id: uuid.UUID | None = None) -> AuditEntry:
        fields = {
            "dispute_id": dispute_id,
            "seller_id": seller_id,
            "paypal_dispute_id": paypal_dispute_id,
            "case_file": case_file,
            "decision": decision,
            "outcome": decision.get("outcome"),
            "confidence": float(decision.get("confidence", 0.0)),
            "gate": result.get("gate", decision.get("gate", "escalate")),
            "action_taken": result.get("action_taken", ""),
            "executed": bool(result.get("executed", False)),
            "paypal_result": result.get("paypal_result", {}),
            "engine": engine,
            "served_by": served_by,
        }
        async with self._uow():
            entry = await self._audit.create(fields=fields)
        logger.info("Audit entry recorded", extra={"event": "audit.recorded", "dispute_id": str(dispute_id), "gate": fields["gate"], "executed": fields["executed"]})
        return entry

    async def get_page(self, *, page: int, page_size: int, seller_id: uuid.UUID | None = None, outcome: str | None = None, gate: str | None = None) -> Page[AuditEntry]:
        return await self._audit.get_page(page=page, page_size=page_size, seller_id=seller_id, outcome=outcome, gate=gate)

    async def list_for_dispute(self, dispute_id: uuid.UUID, *, seller_id: uuid.UUID | None = None) -> list[AuditEntry]:
        return await self._audit.list_for_dispute(dispute_id, seller_id=seller_id)
