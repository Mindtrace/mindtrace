"""Unit tests for User model (lifecycle hooks and organization_id property)."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from bson import ObjectId

from mindtrace.apps.inspectra.models.user import User


@pytest.mark.asyncio
async def test_before_save_sets_email_norm():
    """before_save normalizes email to email_norm."""
    self = MagicMock()
    self.email = "Test@Example.COM"
    self.email_norm = ""
    await User.before_save(self)
    assert self.email_norm == "test@example.com"


@pytest.mark.asyncio
async def test_before_insert_sets_email_norm_and_timestamps():
    """before_insert sets email_norm, created_at, updated_at."""
    self = MagicMock()
    self.email = "U@B.org"
    self.email_norm = ""
    self.created_at = None
    self.updated_at = None
    await User.before_insert(self)
    assert self.email_norm == "u@b.org"
    assert isinstance(self.created_at, datetime)
    assert isinstance(self.updated_at, datetime)


@pytest.mark.asyncio
async def test_before_replace_sets_email_norm_and_updated_at():
    """before_replace sets email_norm and updated_at."""
    self = MagicMock()
    self.email = "X@Y.co"
    self.email_norm = ""
    self.updated_at = None
    await User.before_replace(self)
    assert self.email_norm == "x@y.co"
    assert isinstance(self.updated_at, datetime)


@pytest.mark.asyncio
async def test_after_save_sets_updated_at():
    """after_save sets updated_at."""
    self = MagicMock()
    self.updated_at = None
    await User.after_save(self)
    assert isinstance(self.updated_at, datetime)


@pytest.mark.asyncio
async def test_after_delete_sets_updated_at():
    """after_delete sets updated_at."""
    self = MagicMock()
    self.updated_at = None
    await User.after_delete(self)
    assert isinstance(self.updated_at, datetime)


def test_organization_id_when_org_has_ref():
    """organization_id returns str(org.ref.id) when org has ref."""
    oid = ObjectId()
    user = MagicMock()
    user.organization = SimpleNamespace(ref=SimpleNamespace(id=oid))
    assert User.organization_id.fget(user) == str(oid)


def test_organization_id_when_org_has_id_only():
    """organization_id returns str(org.id) when org has no ref."""
    oid = ObjectId()
    user = MagicMock()
    user.organization = SimpleNamespace(id=oid)
    assert User.organization_id.fget(user) == str(oid)
