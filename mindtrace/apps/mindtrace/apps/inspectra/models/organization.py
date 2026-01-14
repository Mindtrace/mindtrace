"""Organization model for the Inspectra application."""

from datetime import datetime, timezone

from beanie import Insert, Replace, before_event
from pydantic import Field
from typing_extensions import Any, Dict

from mindtrace.database import MindtraceDocument


class Organization(MindtraceDocument):
    """Organization model representing a company or organization."""

    name: str
    meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @before_event(Insert)
    async def before_insert(self):
        """Set created_at and updated_at timestamps before document insertion."""
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    @before_event(Replace)
    async def before_replace(self):
        """Update updated_at timestamp before document replacement."""
        self.updated_at = datetime.now(timezone.utc)

    class Settings:
        """Beanie settings for the Organization collection."""

        name = "organizations"
