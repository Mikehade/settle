from dependency_injector.wiring import inject
from fastapi import APIRouter, Query

from src.api.audit.schemas import AuditEntryListItem, AuditEntryResponse
from src.api.deps import AuditServiceDep, CurrentUser, DisputeServiceDep, Pagination
from src.shared.responses import Envelope, paginated, success

router = APIRouter(prefix="/audit", tags=["Audit Trail"])


@router.get("", response_model=Envelope[list[AuditEntryListItem]])
@inject
async def list_audit(
    pagination: Pagination,
    user: CurrentUser,
    service: AuditServiceDep,
    outcome: str | None = Query(None, description="Filter by outcome"),
    gate: str | None = Query(None, description="Filter by gate (execute | escalate)"),
):
    """This seller's mediation decisions — lean rows (no raw payloads)."""
    return paginated(await service.get_page(
        page=pagination.page, page_size=pagination.page_size, seller_id=user["id"], outcome=outcome, gate=gate,
    ))


@router.get("/dispute/{dispute_id}", response_model=Envelope[list[AuditEntryResponse]])
@inject
async def audit_for_dispute(
    dispute_id: str,
    user: CurrentUser,
    service: AuditServiceDep,
    disputes: DisputeServiceDep,
):
    """Full audit entries for one dispute, by internal UUID or PayPal id.
    Owner-scoped: resolving the dispute first enforces ownership."""
    dispute = await disputes.get_by_any_id(dispute_id, seller_id=user["id"])
    return success(await service.list_for_dispute(dispute["id"], seller_id=user["id"]))
