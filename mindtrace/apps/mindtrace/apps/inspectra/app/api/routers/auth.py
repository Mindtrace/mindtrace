from fastapi import APIRouter

from mindtrace.apps.inspectra.app.schemas.auth import (
    LoginPayload,
    RegisterPayload,
    TokenResponse,
)
from mindtrace.apps.inspectra.app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])

service = AuthService()

@router.post("/register", response_model=TokenResponse)
async def register(payload: RegisterPayload) -> TokenResponse:
    return await service.register(payload)

@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginPayload) -> TokenResponse:
    return await service.login(payload)
