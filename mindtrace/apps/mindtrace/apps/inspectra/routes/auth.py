"""Auth endpoints: login, refresh, GET /auth/me."""

from fastapi import Depends, HTTPException, status

from mindtrace.apps.inspectra.core import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_current_user,
    get_inspectra_service,
    verify_password,
)
from mindtrace.apps.inspectra.models import User
from mindtrace.apps.inspectra.models.enums import OrganizationStatus, UserRole, UserStatus
from mindtrace.apps.inspectra.routes.users import user_to_response
from mindtrace.apps.inspectra.schemas.auth import (
    LoginRequest,
    LoginSchema,
    RefreshRequest,
    RefreshSchema,
    TokenResponse,
)


def register(service):
    """Register auth routes on the given InspectraService."""
    service.add_endpoint(
        "/auth/login",
        login,
        schema=LoginSchema,
        methods=["POST"],
        as_tool=False,
    )
    service.add_endpoint(
        "/auth/refresh",
        refresh,
        schema=RefreshSchema,
        methods=["POST"],
        as_tool=False,
    )
    service.add_endpoint(
        "/auth/me",
        get_me,
        schema=None,
        methods=["GET"],
        api_route_kwargs={"dependencies": [Depends(get_current_user)]},
        as_tool=False,
    )


async def login(payload: LoginRequest, service=Depends(get_inspectra_service)):
    """Authenticate with email and password; return access and refresh tokens."""
    email = (payload.email or "").strip().lower()
    password = (payload.password or "").strip()
    user = await service.user_repo.get_by_email(email)
    if not user or not verify_password(password, getattr(user, "pw_hash", None)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")
    org_id = user.organization_id
    if org_id:
        org = await service.org_repo.get(org_id)
        if org and org.status != OrganizationStatus.ACTIVE and user.role != UserRole.SUPER_ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization is inactive")
    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_refresh_token(subject=str(user.id))
    return TokenResponse(access_token=access_token, token_type="bearer", refresh_token=refresh_token)


async def refresh(payload: RefreshRequest):
    """Exchange a valid refresh token for new access and refresh tokens."""
    data = decode_refresh_token(payload.refresh_token)
    access_token = create_access_token(subject=data.sub)
    refresh_token = create_refresh_token(subject=data.sub)
    return TokenResponse(access_token=access_token, token_type="bearer", refresh_token=refresh_token)


async def get_me(user: User = Depends(get_current_user)):
    """Return the current authenticated user."""
    return user_to_response(user)
