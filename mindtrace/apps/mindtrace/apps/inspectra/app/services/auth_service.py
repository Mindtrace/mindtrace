from fastapi import HTTPException, status

from mindtrace.apps.inspectra.app.api.core.security import (
    hash_password,
    verify_password,
    create_access_token,
)
from mindtrace.apps.inspectra.app.repositories.user_repository import UserRepository
from mindtrace.apps.inspectra.app.repositories.role_repository import RoleRepository
from mindtrace.apps.inspectra.app.schemas.auth import (
    LoginPayload,
    RegisterPayload,
    TokenResponse,
)

class AuthService:
    def __init__(self, user_repo=None, role_repo=None):
        self.user_repo = user_repo or UserRepository()
        self.role_repo = role_repo or RoleRepository()

    async def _get_default_role_id(self) -> str:
        """
        Ensure there is a default 'user' role and return its ID.
        """
        role = await self.role_repo.get_by_name("user")
        if not role:
            from mindtrace.apps.inspectra.app.schemas.role import RoleCreate
            role = await self.role_repo.create(
                RoleCreate(name="user", description="Default user role")
            )
        return role.id

    async def register(self, payload: RegisterPayload) -> TokenResponse:
        existing = await self.user_repo.get_by_username(payload.username)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )

        password_hash = hash_password(payload.password)
        default_role_id = await self._get_default_role_id()

        user = await self.user_repo.create_user(
            username=payload.username,
            password_hash=password_hash,
            role_id=default_role_id,
        )

        return TokenResponse(access_token=create_access_token(subject=user.username))

    async def login(self, payload: LoginPayload) -> TokenResponse:
        user = await self.user_repo.get_by_username(payload.username)
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        return TokenResponse(access_token=create_access_token(subject=user.username))
