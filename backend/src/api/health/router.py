from dependency_injector.wiring import inject
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.api.deps import HealthServiceDep
from src.shared.errors import ErrorCode
from src.shared.logging import get_request_id
from src.shared.responses import Envelope, error_body, success

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=Envelope[dict])
async def liveness():
    """The process is up. No dependencies checked."""
    return success({"alive": True})


@router.get("/ready", response_model=Envelope[dict])
@inject
async def readiness(service: HealthServiceDep):
    """Every dependency answers. 503 if any check fails."""
    checks = await service.readiness()
    if all(checks.values()):
        return success(checks)
    return JSONResponse(
        status_code=503,
        content=error_body(
            ErrorCode.COMMON_SERVICE_UNAVAILABLE, "Not ready", meta={"checks": checks, "request_id": get_request_id()}
        ),
    )
