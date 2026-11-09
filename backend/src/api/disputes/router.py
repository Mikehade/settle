from dependency_injector.wiring import inject
from fastapi import APIRouter, Query

from src.api.deps import CurrentUser, DisputeServiceDep, MediationServiceDep, Pagination
from src.api.disputes.schemas import (
    ActionResultResponse,
    DisputePreviewResponse,
    DisputeResponse,
    MediationSummaryResponse,
    OpenDisputeSummary,
)
from src.shared.responses import Envelope, paginated, success

router = APIRouter(prefix="/disputes", tags=["Disputes"])


@router.get("", response_model=Envelope[list[DisputeResponse]])
@inject
async def list_disputes(
    pagination: Pagination,
    user: CurrentUser,
    service: DisputeServiceDep,
    status: str | None = Query(None, description="Filter by status"),
    dispute_type: str | None = Query(None, description="Filter by dispute type"),
    search: str | None = Query(None, description="Search PayPal id / buyer complaint"),
    sort: str = Query("created_at", description="created_at | updated_at | disputed_amount | status | resolved_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    """List the disputes Settle has seen for the current seller (filterable)."""
    return paginated(await service.get_page(
        page=pagination.page, page_size=pagination.page_size, seller_id=user["id"],
        status=status, dispute_type=dispute_type, search=search, sort=sort, order=order,
    ))


@router.get("/open", response_model=Envelope[list[OpenDisputeSummary]])
@inject
async def list_open(user: CurrentUser, service: MediationServiceDep):
    """List currently-open disputes from the dispute source (real + seeded),
    reconciled against this seller's resolved cases."""
    return success(await service.list_open(seller_id=user["id"]))


@router.get("/{dispute_id}", response_model=Envelope[DisputeResponse])
@inject
async def get_dispute(dispute_id: str, user: CurrentUser, service: DisputeServiceDep):
    """Fetch one dispute by internal UUID or PayPal/fixture id (owner-scoped)."""
    return success(await service.get_by_any_id(dispute_id, seller_id=user["id"]))


@router.get("/{paypal_dispute_id}/preview", response_model=Envelope[DisputePreviewResponse])
@inject
async def preview_dispute(paypal_dispute_id: str, user: CurrentUser, service: MediationServiceDep):
    """Assemble and return the case file WITHOUT running mediation, so the detail
    page for a not-yet-run case has something to show."""
    return success(await service.preview(paypal_dispute_id, seller_id=user["id"]))


@router.post("/{paypal_dispute_id}/mediate", response_model=Envelope[MediationSummaryResponse])
@inject
async def mediate(paypal_dispute_id: str, user: CurrentUser, service: MediationServiceDep):
    """Run a full mediation now and return the summary. (For the live reasoning
    trace, connect the mediation WebSocket instead — see UI_INTEGRATION.md.)"""
    summary = await service.mediate(paypal_dispute_id, seller_id=user["id"])
    return success(summary, message="Mediation complete")


@router.post("/{paypal_dispute_id}/approve", response_model=Envelope[ActionResultResponse])
@inject
async def approve(paypal_dispute_id: str, user: CurrentUser, service: MediationServiceDep):
    """Approve an escalated recommendation and perform it (REST equivalent of the
    `seller.approve` WebSocket action). Owner-scoped; 409 if already acted on."""
    result = await service.approve(paypal_dispute_id, seller_id=user["id"])
    inner = result.get("result", {})
    return success(
        {
            "dispute_id": result["dispute_id"],
            "executed": inner.get("executed", False),
            "action_taken": inner.get("action_taken", ""),
            "decision": result.get("decision"),
        },
        message="Recommendation approved",
    )


@router.post("/{paypal_dispute_id}/reject", response_model=Envelope[ActionResultResponse])
@inject
async def reject(paypal_dispute_id: str, user: CurrentUser, service: MediationServiceDep):
    """Reject an escalated recommendation and leave the case for manual handling
    (REST equivalent of `seller.reject`). Owner-scoped; 409 if already acted on."""
    result = await service.reject(paypal_dispute_id, seller_id=user["id"])
    return success(
        {
            "dispute_id": result["dispute_id"],
            "executed": False,
            "action_taken": result.get("action_taken", ""),
            "rationale": result.get("rationale"),
            "decision": result.get("decision"),
        },
        message="Recommendation rejected",
    )
