from dependency_injector.wiring import inject
from fastapi import APIRouter

from src.api.auth.schemas import LoginRequest, TokenResponse, UserResponse
from src.api.deps import AuthServiceDep, CurrentUser
from src.shared.responses import Envelope, success

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=Envelope[TokenResponse])
@inject
async def login(body: LoginRequest, auth: AuthServiceDep):
    token = await auth.login(email=body.email, password=body.password)
    return success(token, message="Logged in")


@router.get("/me", response_model=Envelope[UserResponse])
async def me(user: CurrentUser):
    return success(user)
