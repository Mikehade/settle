import uuid

from dependency_injector.wiring import inject
from fastapi import APIRouter

from src.api.deps import CurrentUser, DisputeServiceDep, MediationServiceDep, Pagination
from src.api.disputes.schemas import DisputeResponse, MediationSummaryResponse, OpenDisputeSummary
from src.shared.responses import Envelope, paginated, success

router = APIRouter(prefix="/disputes", tags=["Disputes"])


@router.get("", response_model=Envelope[list[DisputeResponse]])
@inject
async def list_disputes(pagination: Pagination, user: CurrentUser, service: DisputeServiceDep):
    """List the disputes Settle has seen for the current seller."""
    return paginated(await service.get_page(page=pagination.page, page_size=pagination.page_size, seller_id=user["id"]))


@router.get("/open", response_model=Envelope[list[OpenDisputeSummary]])
@inject
async def list_open(user: CurrentUser, service: MediationServiceDep):
    """List currently-open disputes from the dispute source (real + seeded)."""
    return success(await service.list_open())


@router.get("/{dispute_id}", response_model=Envelope[DisputeResponse])
@inject
async def get_dispute(dispute_id: uuid.UUID, user: CurrentUser, service: DisputeServiceDep):
    return success(await service.get(dispute_id))


@router.post("/{paypal_dispute_id}/mediate", response_model=Envelope[MediationSummaryResponse])
@inject
async def mediate(paypal_dispute_id: str, user: CurrentUser, service: MediationServiceDep):
    """Run a full mediation now and return the summary. (For the live reasoning
    trace, connect the mediation WebSocket instead — see UI_INTEGRATION.md.)"""
    summary = await service.mediate(paypal_dispute_id, seller_id=user["id"])
    return success(summary, message="Mediation complete")
