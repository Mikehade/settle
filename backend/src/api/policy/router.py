from dependency_injector.wiring import inject
from fastapi import APIRouter

from src.api.deps import CurrentUser, PolicyServiceDep
from src.api.policy.schemas import PolicyResponse, PolicyUpdateRequest
from src.domain.exceptions import NotFoundError
from src.shared.errors import ErrorCode
from src.shared.responses import Envelope, success

router = APIRouter(prefix="/policy", tags=["Fairness Policy"])


@router.get("", response_model=Envelope[PolicyResponse])
@inject
async def get_policy(user: CurrentUser, service: PolicyServiceDep):
    """The current seller's fairness policy."""
    policy = await service.get_for_seller(user["id"])
    if policy is None:
        raise NotFoundError(ErrorCode.POLICY_NOT_FOUND, "No fairness policy set yet")
    return success(policy)


@router.put("", response_model=Envelope[PolicyResponse])
@inject
async def set_policy(body: PolicyUpdateRequest, user: CurrentUser, service: PolicyServiceDep):
    """Create or update the seller's fairness policy."""
    policy = await service.set_policy(user["id"], body.model_dump(exclude_unset=True))
    return success(policy, message="Fairness policy saved")
