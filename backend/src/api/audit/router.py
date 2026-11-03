import uuid

from dependency_injector.wiring import inject
from fastapi import APIRouter

from src.api.audit.schemas import AuditEntryResponse
from src.api.deps import AuditServiceDep, CurrentUser, Pagination
from src.shared.responses import Envelope, paginated, success

router = APIRouter(prefix="/audit", tags=["Audit Trail"])


@router.get("", response_model=Envelope[list[AuditEntryResponse]])
@inject
async def list_audit(pagination: Pagination, user: CurrentUser, service: AuditServiceDep):
    """Every mediation decision, fully explainable after the fact."""
    return paginated(await service.get_page(page=pagination.page, page_size=pagination.page_size))


@router.get("/dispute/{dispute_id}", response_model=Envelope[list[AuditEntryResponse]])
@inject
async def audit_for_dispute(dispute_id: uuid.UUID, user: CurrentUser, service: AuditServiceDep):
    return success(await service.list_for_dispute(dispute_id))
