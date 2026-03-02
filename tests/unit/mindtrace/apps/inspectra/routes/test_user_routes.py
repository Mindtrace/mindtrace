"""Unit tests for user route handlers (mocked service and deps)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.apps.inspectra.models import User
from mindtrace.apps.inspectra.models.enums import UserRole, UserStatus
from mindtrace.apps.inspectra.routes.users import (
    create_user,
    get_user,
    list_users,
    update_user,
    user_to_response,
)
from mindtrace.apps.inspectra.schemas.user import (
    CreateUserRequest,
    UpdateUserRequest,
)


def test_user_to_response():
    user = MagicMock(spec=User)
    user.id = "uid"
    user.email = "a@b.com"
    user.role = UserRole.USER
    user.organization_id = "oid"
    user.first_name = "F"
    user.last_name = "L"
    user.status = UserStatus.ACTIVE
    r = user_to_response(user)
    assert r.id == "uid"
    assert r.email == "a@b.com"
    assert r.role == UserRole.USER


@pytest.fixture
def mock_service():
    s = MagicMock()
    s.user_repo.count_by_organization = AsyncMock(return_value=0)
    s.user_repo.list_by_organization = AsyncMock(return_value=[])
    s.user_repo.count_all = AsyncMock(return_value=0)
    s.user_repo.list_all = AsyncMock(return_value=[])
    s.user_repo.get_by_id = AsyncMock(return_value=None)
    s.user_repo.get_by_email = AsyncMock(return_value=None)
    s.user_repo.create = AsyncMock(return_value=MagicMock())
    s.user_repo.update = AsyncMock(return_value=None)
    return s


def _admin_user(org_id="org1"):
    u = MagicMock(spec=User)
    u.role = UserRole.ADMIN
    u.organization_id = org_id
    return u


def _super_admin_user():
    u = MagicMock(spec=User)
    u.role = UserRole.SUPER_ADMIN
    u.organization_id = "any"
    return u


@pytest.mark.asyncio
async def test_list_users_super_admin_with_org(mock_service):
    mock_service.user_repo.count_by_organization.return_value = 1
    mock_service.user_repo.list_by_organization.return_value = []
    result = await list_users(
        user=_super_admin_user(),
        organization_id="org1",
        skip=0,
        limit=20,
        search=None,
        service=mock_service,
    )
    assert result.total == 1
    mock_service.user_repo.count_by_organization.assert_called_once_with("org1", search=None)
    mock_service.user_repo.list_by_organization.assert_called_once()


@pytest.mark.asyncio
async def test_list_users_super_admin_all(mock_service):
    mock_service.user_repo.count_all.return_value = 0
    mock_service.user_repo.list_all.return_value = []
    result = await list_users(
        user=_super_admin_user(),
        organization_id=None,
        skip=0,
        limit=20,
        search=None,
        service=mock_service,
    )
    assert result.total == 0
    mock_service.user_repo.count_all.assert_called_once()
    mock_service.user_repo.list_all.assert_called_once()


@pytest.mark.asyncio
async def test_list_users_admin(mock_service):
    mock_service.user_repo.count_by_organization.return_value = 0
    mock_service.user_repo.list_by_organization.return_value = []
    result = await list_users(
        user=_admin_user(org_id="org1"),
        organization_id=None,
        skip=0,
        limit=20,
        search=None,
        service=mock_service,
    )
    assert result.total == 0
    mock_service.user_repo.count_by_organization.assert_called_once_with("org1", search=None)


@patch("mindtrace.apps.inspectra.routes.users.validate_password_strength")
@patch("mindtrace.apps.inspectra.routes.users.hash_password")
@pytest.mark.asyncio
async def test_create_user_success(hash_password, validate_password_strength, mock_service):
    validate_password_strength.return_value = []
    mock_service.user_repo.get_by_email.return_value = None
    new_user = MagicMock(
        id="u1",
        email="n@b.com",
        role=UserRole.USER,
        organization_id="o1",
        first_name="N",
        last_name="U",
        status=UserStatus.ACTIVE,
    )
    mock_service.user_repo.create.return_value = new_user
    hash_password.return_value = "hashed"
    payload = CreateUserRequest(
        email="n@b.com",
        password="Strong1!",
        role=UserRole.USER,
        organization_id="o1",
        first_name="N",
        last_name="U",
    )
    result = await create_user(payload, _super_admin_user(), mock_service)
    assert result.email == "n@b.com"
    mock_service.user_repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_create_user_admin_cannot_create_super_admin(mock_service):
    payload = CreateUserRequest(
        email="n@b.com",
        password="Strong1!",
        role=UserRole.SUPER_ADMIN,
        organization_id="org1",
        first_name="N",
        last_name="U",
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await create_user(payload, _admin_user("org1"), mock_service)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_create_user_admin_other_org_403(mock_service):
    payload = CreateUserRequest(
        email="n@b.com",
        password="Strong1!",
        role=UserRole.USER,
        organization_id="other_org",
        first_name="N",
        last_name="U",
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await create_user(payload, _admin_user("org1"), mock_service)
    assert exc_info.value.status_code == 403


@patch("mindtrace.apps.inspectra.routes.users.validate_password_strength")
@pytest.mark.asyncio
async def test_create_user_weak_password_400(validate_password_strength, mock_service):
    validate_password_strength.return_value = ["Too short"]
    payload = CreateUserRequest(
        email="n@b.com",
        password="weak",
        role=UserRole.USER,
        organization_id="o1",
        first_name="N",
        last_name="U",
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await create_user(payload, _super_admin_user(), mock_service)
    assert exc_info.value.status_code == 400


@patch("mindtrace.apps.inspectra.routes.users.validate_password_strength")
@pytest.mark.asyncio
async def test_create_user_email_exists_400(validate_password_strength, mock_service):
    validate_password_strength.return_value = []
    mock_service.user_repo.get_by_email.return_value = MagicMock()
    payload = CreateUserRequest(
        email="existing@b.com",
        password="Strong1!",
        role=UserRole.USER,
        organization_id="o1",
        first_name="N",
        last_name="U",
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await create_user(payload, _super_admin_user(), mock_service)
    assert exc_info.value.status_code == 400


@patch("mindtrace.apps.inspectra.routes.users.validate_password_strength")
@patch("mindtrace.apps.inspectra.routes.users.hash_password")
@pytest.mark.asyncio
async def test_create_user_value_error_400(hash_password, validate_password_strength, mock_service):
    validate_password_strength.return_value = []
    mock_service.user_repo.get_by_email.return_value = None
    mock_service.user_repo.create.side_effect = ValueError("Organization not found")
    hash_password.return_value = "h"
    payload = CreateUserRequest(
        email="n@b.com",
        password="Strong1!",
        role=UserRole.USER,
        organization_id="bad",
        first_name="N",
        last_name="U",
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await create_user(payload, _super_admin_user(), mock_service)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_user_found(mock_service):
    target = MagicMock(
        id="u1",
        email="a@b.com",
        role=UserRole.USER,
        organization_id="o1",
        first_name="A",
        last_name="B",
        status=UserStatus.ACTIVE,
    )
    mock_service.user_repo.get_by_id.return_value = target
    result = await get_user(id_="u1", user=_super_admin_user(), service=mock_service)
    assert result.id == "u1"


@pytest.mark.asyncio
async def test_get_user_not_found_404(mock_service):
    mock_service.user_repo.get_by_id.return_value = None
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_user(id_="none", user=_super_admin_user(), service=mock_service)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_user_admin_other_org_403(mock_service):
    target = MagicMock(organization_id="other")
    mock_service.user_repo.get_by_id.return_value = target
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_user(id_="u1", user=_admin_user("org1"), service=mock_service)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_update_user_success(mock_service):
    target = MagicMock(id="u1", organization_id="o1")
    updated = MagicMock()
    updated.id = "u1"
    updated.email = "a@b.com"
    updated.role = UserRole.USER
    updated.organization_id = "o1"
    updated.first_name = "New"
    updated.last_name = "L"
    updated.status = UserStatus.ACTIVE
    mock_service.user_repo.get_by_id.return_value = target
    mock_service.user_repo.update.return_value = updated
    payload = UpdateUserRequest(first_name="New")
    result = await update_user(id_="u1", payload=payload, user=_super_admin_user(), service=mock_service)
    assert result.first_name == "New"


@pytest.mark.asyncio
async def test_update_user_not_found_404(mock_service):
    mock_service.user_repo.get_by_id.return_value = None
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await update_user(id_="none", payload=UpdateUserRequest(), user=_super_admin_user(), service=mock_service)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_user_admin_other_org_403(mock_service):
    target = MagicMock(organization_id="other")
    mock_service.user_repo.get_by_id.return_value = target
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await update_user(id_="u1", payload=UpdateUserRequest(), user=_admin_user("org1"), service=mock_service)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_update_user_admin_cannot_assign_super_admin_403(mock_service):
    target = MagicMock(organization_id="org1")
    mock_service.user_repo.get_by_id.return_value = target
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await update_user(
            id_="u1",
            payload=UpdateUserRequest(role=UserRole.SUPER_ADMIN),
            user=_admin_user("org1"),
            service=mock_service,
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_update_user_update_returns_none_404(mock_service):
    target = MagicMock(organization_id="o1")
    mock_service.user_repo.get_by_id.return_value = target
    mock_service.user_repo.update.return_value = None
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await update_user(
            id_="u1", payload=UpdateUserRequest(first_name="X"), user=_super_admin_user(), service=mock_service
        )
    assert exc_info.value.status_code == 404
