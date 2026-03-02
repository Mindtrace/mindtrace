"""Unit tests for Inspectra core deps."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request

from mindtrace.apps.inspectra.core.deps import (
    get_inspectra_service,
    require_admin_or_super,
    require_super_admin,
)
from mindtrace.apps.inspectra.models import User
from mindtrace.apps.inspectra.models.enums import UserRole


def test_get_inspectra_service_returns_from_app_state():
    """get_inspectra_service returns request.app.state.inspectra_service."""
    service = MagicMock()
    request = MagicMock(spec=Request)
    request.app.state.inspectra_service = service
    assert get_inspectra_service(request) is service


@pytest.mark.asyncio
async def test_require_super_admin_raises_403_for_admin():
    """require_super_admin raises 403 when role is not SUPER_ADMIN."""
    user = MagicMock(spec=User)
    user.role = UserRole.ADMIN
    with pytest.raises(HTTPException) as exc_info:
        await require_super_admin(user=user)
    assert exc_info.value.status_code == 403
    assert "Super admin" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_super_admin_returns_user_when_super_admin():
    """require_super_admin returns user when role is SUPER_ADMIN."""
    user = MagicMock(spec=User)
    user.role = UserRole.SUPER_ADMIN
    result = await require_super_admin(user=user)
    assert result is user


@pytest.mark.asyncio
async def test_require_admin_or_super_raises_403_for_user():
    """require_admin_or_super raises 403 when role is user."""
    user = MagicMock(spec=User)
    user.role = UserRole.USER
    with pytest.raises(HTTPException) as exc_info:
        await require_admin_or_super(user=user)
    assert exc_info.value.status_code == 403
    assert "Admin" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_admin_or_super_returns_user_when_admin():
    """require_admin_or_super returns user when role is ADMIN."""
    user = MagicMock(spec=User)
    user.role = UserRole.ADMIN
    result = await require_admin_or_super(user=user)
    assert result is user


@pytest.mark.asyncio
async def test_require_admin_or_super_returns_user_when_super_admin():
    """require_admin_or_super returns user when role is SUPER_ADMIN."""
    user = MagicMock(spec=User)
    user.role = UserRole.SUPER_ADMIN
    result = await require_admin_or_super(user=user)
    assert result is user
