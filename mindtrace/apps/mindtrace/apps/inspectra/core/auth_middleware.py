"""Authentication middleware for Inspectra."""

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

AUTH_EXEMPT_PATHS = {
    "/auth/login",
    "/auth/register",
    "/license/activate",
    "/license/machine-id",
    "/license/status",
    "/license/validate",
    "/password/validate",
    "/status",
    "/heartbeat",
    "/endpoints",
    "/server_id",
    "/pid_file",
    "/shutdown",
    "/docs",
    "/redoc",
    "/openapi.json",
}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that validates JWT and attaches user to request state.

    Validates:
    - JWT token presence and validity
    - User exists and is active
    - Attaches AuthenticatedUser to request.state.user
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        for exempt in AUTH_EXEMPT_PATHS:
            if path == exempt or path.startswith(exempt + "/"):
                return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        token = auth_header.split(" ")[1]

        from mindtrace.apps.inspectra.core.security import AuthenticatedUser, decode_token

        try:
            token_data = decode_token(token)
        except HTTPException:
            raise

        from mindtrace.apps.inspectra.repositories.user_repository import UserRepository

        user_repo = UserRepository()
        user = await user_repo.get_by_username(token_data.sub)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated",
            )

        from mindtrace.apps.inspectra.repositories.role_repository import RoleRepository

        role_repo = RoleRepository()
        role = await role_repo.get_by_id(user.role_id)

        request.state.user = AuthenticatedUser(
            user_id=user.id,
            username=user.username,
            role_id=user.role_id,
            role_name=role.name if role else "unknown",
            plant_id=user.plant_id,
            permissions=role.permissions if role and role.permissions else [],
            is_active=user.is_active,
        )

        return await call_next(request)
