"""FastAPI dependencies for Inspectra auth and RBAC."""

from typing import Any

from fastapi import Depends, HTTPException, Request, status

from mindtrace.apps.inspectra.models import User
from mindtrace.apps.inspectra.models.enums import UserRole

from .security import get_current_user


def get_inspectra_service(request: Request) -> Any:
    """Return the InspectraService instance from app.state (set by the service in __init__)."""
    return request.app.state.inspectra_service


async def require_super_admin(user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency: require SUPER_ADMIN role. Raises 403 otherwise."""
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin required")
    return user


async def require_admin_or_super(user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency: require ADMIN or SUPER_ADMIN role. Raises 403 otherwise."""
    if user.role not in (UserRole.SUPER_ADMIN, UserRole.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or super admin required")
    return user
