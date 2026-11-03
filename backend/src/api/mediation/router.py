"""Mediation WebSocket route: GET (upgrade) {API_PREFIX}/ws/mediation?token=<jwt>.

The consumer authenticates from the `token` query param (browsers can't set
WebSocket headers), then streams the live reasoning trace. See
UI_INTEGRATION.md for the event contract.
"""
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, WebSocket

from src.api.mediation.consumer import MediationConsumer
from src.config.container import Container
from src.core.auth import AuthService
from src.core.mediation import MediationService
from src.core.policy import FairnessPolicyService

router = APIRouter()


@router.websocket("/ws/mediation")
@inject
async def mediation_ws(
    websocket: WebSocket,
    auth: AuthService = Depends(Provide[Container.auth_service]),
    mediation: MediationService = Depends(Provide[Container.mediation_service]),
    policy: FairnessPolicyService = Depends(Provide[Container.policy_service]),
) -> None:
    consumer = MediationConsumer(websocket, auth, mediation, policy)
    await consumer.handle_connection()
