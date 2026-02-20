"""Plant model for the Inspectra application."""

from datetime import datetime, timezone
from typing import Dict, Optional, Union

from beanie import Insert, Link, Replace, before_event
from pydantic import Field
from typing_extensions import Any

from mindtrace.database import MindtraceDocument

from .organization import Organization


class Plant(MindtraceDocument):
    """Plant model representing a manufacturing plant or facility."""

    organization: Link[Organization]
    name: str
    location: Optional[Union[str, Dict[str, Any]]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    meta: Dict[str, Any] = Field(default_factory=dict)

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
        """Beanie settings for the Plant collection."""

        name = "plants"
