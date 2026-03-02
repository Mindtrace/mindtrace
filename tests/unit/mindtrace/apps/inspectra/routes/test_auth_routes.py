"""Unit tests for auth route handlers (mocked service and deps)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.apps.inspectra.models.enums import OrganizationStatus, UserRole, UserStatus
from mindtrace.apps.inspectra.routes.auth import get_me, login, refresh
from mindtrace.apps.inspectra.schemas.auth import LoginRequest, RefreshRequest, TokenResponse


@pytest.fixture
def mock_service():
    s = MagicMock()
    s.user_repo.get_by_email = AsyncMock()
    s.org_repo.get = AsyncMock()
    return s


@patch("mindtrace.apps.inspectra.routes.auth.create_refresh_token")
@patch("mindtrace.apps.inspectra.routes.auth.create_access_token")
@patch("mindtrace.apps.inspectra.routes.auth.verify_password")
@pytest.mark.asyncio
async def test_login_success(verify_password, create_access_token, create_refresh_token, mock_service):
    user = MagicMock()
    user.id = "uid"
    user.status = UserStatus.ACTIVE
    user.role = UserRole.USER
    user.organization_id = "oid"
    mock_service.user_repo.get_by_email.return_value = user
    verify_password.return_value = True
    mock_service.org_repo.get.return_value = MagicMock(status=OrganizationStatus.ACTIVE)
    create_access_token.return_value = "access"
    create_refresh_token.return_value = "refresh"
    payload = LoginRequest(email="a@b.com", password="secret")
    result = await login(payload, mock_service)
    assert isinstance(result, TokenResponse)
    assert result.access_token == "access"
    assert result.refresh_token == "refresh"


@patch("mindtrace.apps.inspectra.routes.auth.verify_password")
@pytest.mark.asyncio
async def test_login_no_user_401(verify_password, mock_service):
    mock_service.user_repo.get_by_email.return_value = None
    payload = LoginRequest(email="a@b.com", password="secret")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await login(payload, mock_service)
    assert exc_info.value.status_code == 401


@patch("mindtrace.apps.inspectra.routes.auth.verify_password")
@pytest.mark.asyncio
async def test_login_wrong_password_401(verify_password, mock_service):
    user = MagicMock(status=UserStatus.ACTIVE)
    mock_service.user_repo.get_by_email.return_value = user
    verify_password.return_value = False
    payload = LoginRequest(email="a@b.com", password="wrong")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await login(payload, mock_service)
    assert exc_info.value.status_code == 401


@patch("mindtrace.apps.inspectra.routes.auth.verify_password")
@pytest.mark.asyncio
async def test_login_inactive_user_403(verify_password, mock_service):
    user = MagicMock(status=UserStatus.INACTIVE)
    mock_service.user_repo.get_by_email.return_value = user
    verify_password.return_value = True
    payload = LoginRequest(email="a@b.com", password="secret")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await login(payload, mock_service)
    assert exc_info.value.status_code == 403


@patch("mindtrace.apps.inspectra.routes.auth.create_refresh_token")
@patch("mindtrace.apps.inspectra.routes.auth.create_access_token")
@patch("mindtrace.apps.inspectra.routes.auth.verify_password")
@pytest.mark.asyncio
async def test_login_inactive_org_403(verify_password, create_access_token, create_refresh_token, mock_service):
    user = MagicMock()
    user.id = "uid"
    user.status = UserStatus.ACTIVE
    user.role = UserRole.USER
    user.organization_id = "oid"
    mock_service.user_repo.get_by_email.return_value = user
    verify_password.return_value = True
    mock_service.org_repo.get.return_value = MagicMock(status=OrganizationStatus.DISABLED)
    payload = LoginRequest(email="a@b.com", password="secret")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await login(payload, mock_service)
    assert exc_info.value.status_code == 403


@patch("mindtrace.apps.inspectra.routes.auth.create_refresh_token")
@patch("mindtrace.apps.inspectra.routes.auth.create_access_token")
@patch("mindtrace.apps.inspectra.routes.auth.decode_refresh_token")
@pytest.mark.asyncio
async def test_refresh_success(decode_refresh_token, create_access_token, create_refresh_token):
    decode_refresh_token.return_value = MagicMock(sub="uid")
    create_access_token.return_value = "new_access"
    create_refresh_token.return_value = "new_refresh"
    payload = RefreshRequest(refresh_token="old_refresh")
    result = await refresh(payload)
    assert result.access_token == "new_access"
    assert result.refresh_token == "new_refresh"


@patch("mindtrace.apps.inspectra.routes.auth.user_to_response")
@pytest.mark.asyncio
async def test_get_me(user_to_response):
    user = MagicMock()
    user_to_response.return_value = MagicMock()
    result = await get_me(user)
    user_to_response.assert_called_once_with(user)
    assert result == user_to_response.return_value
