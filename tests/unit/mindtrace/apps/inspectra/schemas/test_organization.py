"""Unit tests for Inspectra organization schemas."""

import pytest
from pydantic import ValidationError

from mindtrace.apps.inspectra.schemas.organization import (
    CreateOrganizationRequest,
    UpdateOrganizationRequest,
)


def test_create_organization_request_name_valid():
    """CreateOrganizationRequest accepts name without spaces."""
    req = CreateOrganizationRequest(name="Acme")
    assert req.name == "Acme"


def test_create_organization_request_name_with_spaces_raises():
    """CreateOrganizationRequest rejects name with spaces (pattern or validator)."""
    with pytest.raises(ValidationError, match="pattern|spaces"):
        CreateOrganizationRequest(name="Acme Corp")


def test_update_organization_request_name_none_allowed():
    """UpdateOrganizationRequest allows name=None (omit to leave unchanged)."""
    req = UpdateOrganizationRequest(name=None)
    assert req.name is None


def test_update_organization_request_name_valid():
    """UpdateOrganizationRequest accepts name without spaces."""
    req = UpdateOrganizationRequest(name="NewName")
    assert req.name == "NewName"


def test_update_organization_request_name_with_spaces_raises():
    """UpdateOrganizationRequest rejects name with spaces (pattern or validator)."""
    with pytest.raises(ValidationError, match="pattern|spaces"):
        UpdateOrganizationRequest(name="New Name")
