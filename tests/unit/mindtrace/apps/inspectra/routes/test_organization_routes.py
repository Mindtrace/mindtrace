"""Unit tests for organization route handlers (mocked service)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from mindtrace.apps.inspectra.models.enums import OrganizationStatus
from mindtrace.apps.inspectra.routes.organizations import (
    create_organization,
    get_organization,
    list_organizations,
    org_to_response,
    update_organization,
)
from mindtrace.apps.inspectra.schemas.organization import (
    CreateOrganizationRequest,
    UpdateOrganizationRequest,
)


@pytest.fixture
def mock_service():
    s = MagicMock()
    s.org_repo.count_all = AsyncMock(return_value=1)
    s.org_repo.list_all = AsyncMock(return_value=[])
    s.org_repo.get_by_name = AsyncMock(return_value=None)
    s.org_repo.get = AsyncMock(return_value=None)
    s.org_repo.create = AsyncMock(return_value=MagicMock(id="new-id", name="New", status=OrganizationStatus.ACTIVE))
    s.org_repo.update = AsyncMock(return_value=None)
    return s


def test_org_to_response():
    org = MagicMock()
    org.id = "oid"
    org.name = "Acme"
    org.status = OrganizationStatus.ACTIVE
    r = org_to_response(org)
    assert r.id == "oid"
    assert r.name == "Acme"
    assert r.is_active is True


@pytest.mark.asyncio
async def test_list_organizations(mock_service):
    mock_service.org_repo.count_all.return_value = 0
    mock_service.org_repo.list_all.return_value = []
    result = await list_organizations(skip=0, limit=20, service=mock_service)
    assert result.total == 0
    assert result.items == []


@pytest.mark.asyncio
async def test_create_organization_success(mock_service):
    mock_service.org_repo.get_by_name.return_value = None
    created = MagicMock()
    created.id = "c1"
    created.name = "NewOrg"
    created.status = OrganizationStatus.ACTIVE
    mock_service.org_repo.create.return_value = created
    payload = CreateOrganizationRequest(name="NewOrg")
    result = await create_organization(payload, mock_service)
    assert result.name == "NewOrg"
    mock_service.org_repo.create.assert_called_once_with("NewOrg")


@pytest.mark.asyncio
async def test_create_organization_duplicate_name_400(mock_service):
    mock_service.org_repo.get_by_name.return_value = MagicMock()
    payload = CreateOrganizationRequest(name="Existing")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await create_organization(payload, mock_service)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_organization_found(mock_service):
    org = SimpleNamespace(id="o1", name="Org", status=OrganizationStatus.ACTIVE)
    mock_service.org_repo.get.return_value = org
    result = await get_organization(id_="o1", service=mock_service)
    assert result.id == "o1"
    assert result.name == "Org"


@pytest.mark.asyncio
async def test_get_organization_not_found_404(mock_service):
    mock_service.org_repo.get.return_value = None
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_organization(id_="none", service=mock_service)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_organization_success(mock_service):
    updated = MagicMock()
    updated.id = "o1"
    updated.name = "NewName"
    updated.status = OrganizationStatus.ACTIVE
    mock_service.org_repo.update.return_value = updated
    payload = UpdateOrganizationRequest(name="NewName")
    result = await update_organization(id_="o1", payload=payload, service=mock_service)
    assert result.name == "NewName"


@pytest.mark.asyncio
async def test_update_organization_not_found_404(mock_service):
    mock_service.org_repo.update.return_value = None
    payload = UpdateOrganizationRequest(name="X")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await update_organization(id_="none", payload=payload, service=mock_service)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_organization_is_active_mapping(mock_service):
    """UpdateOrganizationRequest with is_active=True maps to status ACTIVE."""
    updated = MagicMock()
    updated.id = "o1"
    updated.name = "O"
    updated.status = OrganizationStatus.ACTIVE
    mock_service.org_repo.update.return_value = updated
    payload = UpdateOrganizationRequest(is_active=True)
    await update_organization(id_="o1", payload=payload, service=mock_service)
    mock_service.org_repo.update.assert_called_once()
    call_kw = mock_service.org_repo.update.call_args[1]
    assert call_kw["status"] == OrganizationStatus.ACTIVE
