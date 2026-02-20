"""
Organization model for Inspectra.

MongoDB document representing a company or organization. Extends MindtraceDocument
with name, status (active/disabled), and optional meta.
"""

from datetime import datetime, timezone

from beanie import Insert, Replace, before_event
from pydantic import Field
from typing_extensions import Any, Dict

from mindtrace.apps.inspectra.models.enums import OrganizationStatus
from mindtrace.database import MindtraceDocument


class Organization(MindtraceDocument):
    """Organization document for scoping users and resources.

    Attributes:
        name: Organization name.
        status: Organization status (active or disabled). Disabled orgs block access for non–super_admin users.
        meta: Arbitrary metadata.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    name: str
    status: OrganizationStatus = OrganizationStatus.ACTIVE
    meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @before_event(Insert)
    async def before_insert(self):
        """Set created_at and updated_at before insert."""
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    @before_event(Replace)
    async def before_replace(self):
        """Update updated_at before replace."""
        self.updated_at = datetime.now(timezone.utc)

    class Settings:
        """Beanie collection settings for Organization."""

        name = "organizations"
