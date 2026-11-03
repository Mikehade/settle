"""Typed DI aliases for routers. Handlers using them must be decorated with @inject.

    async def create_order(body: OrderCreateRequest, service: OrderServiceDep): ...
"""
from dataclasses import dataclass
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Query

from src.config.container import Container
from src.core.health import HealthService
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.auth import AuthService
from src.core.users import UserService
from src.domain.entities.users import User
from src.domain.exceptions import AuthenticationError, PermissionDeniedError
from src.shared.errors import ErrorCode
from src.shared.logging import bind_user
from src.core.audit import AuditService
from src.core.disputes import DisputeService
from src.core.mediation import MediationService
from src.core.policy import FairnessPolicyService
# [kit:imports]

HealthServiceDep = Annotated[HealthService, Depends(Provide[Container.health_service])]
UserServiceDep = Annotated[UserService, Depends(Provide[Container.user_service])]
AuthServiceDep = Annotated[AuthService, Depends(Provide[Container.auth_service])]
DisputeServiceDep = Annotated[DisputeService, Depends(Provide[Container.dispute_service])]
PolicyServiceDep = Annotated[FairnessPolicyService, Depends(Provide[Container.policy_service])]
AuditServiceDep = Annotated[AuditService, Depends(Provide[Container.audit_service])]
MediationServiceDep = Annotated[MediationService, Depends(Provide[Container.mediation_service])]
# [kit:deps]


@dataclass(frozen=True)
class PageParams:
    page: int = Query(1, ge=1)
    page_size: int = Query(20, ge=1, le=100)


Pagination = Annotated[PageParams, Depends()]

_bearer = HTTPBearer(auto_error=False)


@inject
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth: Annotated[AuthService, Depends(Provide[Container.auth_service])],
) -> User:
    if credentials is None:
        raise AuthenticationError(ErrorCode.AUTH_NOT_AUTHENTICATED, "Not authenticated")
    user = await auth.resolve_token(credentials.credentials)
    bind_user(user["id"])
    return user


async def get_current_superuser(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user["is_superuser"]:
        raise PermissionDeniedError(ErrorCode.AUTH_PERMISSION_DENIED, "Superuser required")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentSuperuser = Annotated[User, Depends(get_current_superuser)]
