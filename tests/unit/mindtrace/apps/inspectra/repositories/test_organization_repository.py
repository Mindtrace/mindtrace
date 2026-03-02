"""Unit tests for OrganizationRepository (mocked ODM)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.apps.inspectra.models import Organization
from mindtrace.apps.inspectra.models.enums import OrganizationStatus
from mindtrace.apps.inspectra.repositories.organization_repository import OrganizationRepository


def _mock_odm_org_get(return_org=None):
    odm = MagicMock()
    odm.organization.get = AsyncMock(return_value=return_org)
    odm.organization.find = AsyncMock(return_value=[])
    odm.organization.insert = AsyncMock(return_value=MagicMock(spec=Organization))
    odm.organization.update = AsyncMock(return_value=MagicMock(spec=Organization))
    return odm


@patch("mindtrace.apps.inspectra.repositories.organization_repository.get_odm")
@pytest.mark.asyncio
async def test_organization_repo_get_found(mock_get_odm):
    org = MagicMock(spec=Organization)
    mock_get_odm.return_value = _mock_odm_org_get(return_org=org)
    repo = OrganizationRepository()
    result = await repo.get("507f1f77bcf86cd799439011")
    assert result is org


@patch("mindtrace.apps.inspectra.repositories.organization_repository.get_odm")
@pytest.mark.asyncio
async def test_organization_repo_get_not_found(mock_get_odm):
    mock_get_odm.return_value = _mock_odm_org_get(return_org=None)
    repo = OrganizationRepository()
    result = await repo.get("507f1f77bcf86cd799439011")
    assert result is None


@patch("mindtrace.apps.inspectra.repositories.organization_repository.get_odm")
@pytest.mark.asyncio
async def test_organization_repo_get_exception_returns_none(mock_get_odm):
    odm = MagicMock()
    odm.organization.get = AsyncMock(side_effect=Exception("db error"))
    mock_get_odm.return_value = odm
    repo = OrganizationRepository()
    result = await repo.get("507f1f77bcf86cd799439011")
    assert result is None


@patch("mindtrace.apps.inspectra.repositories.organization_repository.get_odm")
@pytest.mark.asyncio
async def test_organization_repo_get_by_name_found(mock_get_odm):
    org = MagicMock(spec=Organization)
    odm = MagicMock()
    odm.organization.find = AsyncMock(return_value=[org])
    mock_get_odm.return_value = odm
    with patch("mindtrace.apps.inspectra.repositories.organization_repository.Organization") as mock_org:
        mock_org.name = MagicMock()
        mock_org.name.__eq__ = lambda self, other: True
        repo = OrganizationRepository()
        result = await repo.get_by_name("Acme")
    assert result is org


@patch("mindtrace.apps.inspectra.repositories.organization_repository.get_odm")
@pytest.mark.asyncio
async def test_organization_repo_get_by_name_not_found(mock_get_odm):
    odm = MagicMock()
    odm.organization.find = AsyncMock(return_value=[])
    mock_get_odm.return_value = odm
    with patch("mindtrace.apps.inspectra.repositories.organization_repository.Organization") as mock_org:
        mock_org.name = MagicMock()
        mock_org.name.__eq__ = lambda self, other: True
        repo = OrganizationRepository()
        result = await repo.get_by_name("Acme")
    assert result is None


@patch("mindtrace.apps.inspectra.repositories.organization_repository.get_odm")
@pytest.mark.asyncio
async def test_organization_repo_list_all_include_inactive(mock_get_odm):
    odm = MagicMock()
    odm.organization.find = AsyncMock(return_value=[])
    mock_get_odm.return_value = odm
    repo = OrganizationRepository()
    result = await repo.list_all(include_inactive=True, skip=0, limit=20)
    assert result == []
    odm.organization.find.assert_called_once()


@patch("mindtrace.apps.inspectra.repositories.organization_repository.get_odm")
@pytest.mark.asyncio
async def test_organization_repo_list_all_active_only(mock_get_odm):
    odm = MagicMock()
    odm.organization.find = AsyncMock(return_value=[])
    mock_get_odm.return_value = odm
    repo = OrganizationRepository()
    result = await repo.list_all(include_inactive=False)
    assert result == []
    call_args = odm.organization.find.call_args
    assert call_args[0][0] == {"status": OrganizationStatus.ACTIVE}


@patch("mindtrace.apps.inspectra.repositories.organization_repository.get_odm")
@pytest.mark.asyncio
async def test_organization_repo_count_all_include_inactive(mock_get_odm):
    with patch.object(Organization, "count", new_callable=AsyncMock, return_value=5):
        mock_get_odm.return_value = MagicMock()
        repo = OrganizationRepository()
        result = await repo.count_all(include_inactive=True)
        assert result == 5


@patch("mindtrace.apps.inspectra.repositories.organization_repository.get_odm")
@pytest.mark.asyncio
async def test_organization_repo_count_all_active_only(mock_get_odm):
    with patch.object(Organization, "find") as mock_find:
        mock_query = MagicMock()
        mock_query.count = AsyncMock(return_value=3)
        mock_find.return_value = mock_query
        mock_get_odm.return_value = MagicMock()
        repo = OrganizationRepository()
        result = await repo.count_all(include_inactive=False)
        assert result == 3
        mock_find.assert_called_once_with({"status": OrganizationStatus.ACTIVE})


@patch("mindtrace.apps.inspectra.repositories.organization_repository.Organization")
@patch("mindtrace.apps.inspectra.repositories.organization_repository.get_odm")
@pytest.mark.asyncio
async def test_organization_repo_create(mock_get_odm, mock_org_cls):
    inserted = MagicMock(spec=Organization)
    mock_org_instance = MagicMock()
    mock_org_cls.return_value = mock_org_instance
    odm = MagicMock()
    odm.organization.insert = AsyncMock(return_value=inserted)
    mock_get_odm.return_value = odm
    repo = OrganizationRepository()
    result = await repo.create("NewOrg")
    assert result is inserted
    mock_org_cls.assert_called_once_with(name="NewOrg", status=OrganizationStatus.ACTIVE)
    odm.organization.insert.assert_called_once_with(mock_org_instance)


@patch("mindtrace.apps.inspectra.repositories.organization_repository.get_odm")
@pytest.mark.asyncio
async def test_organization_repo_update_not_found(mock_get_odm):
    odm = MagicMock()
    odm.organization.get = AsyncMock(return_value=None)
    mock_get_odm.return_value = odm
    repo = OrganizationRepository()
    result = await repo.update("507f1f77bcf86cd799439011", name="New")
    assert result is None


@patch("mindtrace.apps.inspectra.repositories.organization_repository.get_odm")
@pytest.mark.asyncio
async def test_organization_repo_update_found(mock_get_odm):
    org = MagicMock(spec=Organization)
    org.name = "Old"
    org.status = OrganizationStatus.ACTIVE
    updated = MagicMock(spec=Organization)
    odm = MagicMock()
    odm.organization.get = AsyncMock(return_value=org)
    odm.organization.update = AsyncMock(return_value=updated)
    mock_get_odm.return_value = odm
    repo = OrganizationRepository()
    result = await repo.update("507f1f77bcf86cd799439011", name="NewName", status=OrganizationStatus.DISABLED)
    assert result is updated
    assert org.name == "NewName"
    assert org.status == OrganizationStatus.DISABLED
