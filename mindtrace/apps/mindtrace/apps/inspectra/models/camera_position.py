"""Camera position model for the Inspectra application."""

from datetime import datetime, timezone
from typing import Any, Dict

from beanie import Insert, Replace, before_event
from pydantic import Field

from mindtrace.apps.inspectra.models import CameraService, CameraSet, Line
from mindtrace.database import Link, MindtraceDocument


class CameraPosition(MindtraceDocument):
    """Camera position model representing a physical camera position."""

    position: int

    line: Link[Line]
    camera_service: Link[CameraService]
    camera_set: Link[CameraSet]

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
        """Beanie settings for the CameraPosition collection."""

        name = "camera_positions"
