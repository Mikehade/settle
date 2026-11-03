"""Every domain router is included here (startapp adds new ones at the markers)."""
from fastapi import APIRouter

from src.api.health.router import router as health_router
from src.api.auth.router import router as auth_router
from src.api.disputes.router import router as disputes_router
from src.api.policy.router import router as policy_router
from src.api.audit.router import router as audit_router
from src.api.webhooks.router import router as webhooks_router
from src.api.mediation.router import router as mediation_ws_router
# [kit:router-imports]

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(disputes_router)
api_router.include_router(policy_router)
api_router.include_router(audit_router)
api_router.include_router(webhooks_router)
api_router.include_router(mediation_ws_router)
# [kit:routers]
