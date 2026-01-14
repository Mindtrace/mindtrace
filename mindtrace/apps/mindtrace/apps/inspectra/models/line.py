"""Line model for the Inspectra application."""

from datetime import datetime, timezone

from beanie import Insert, Link, Replace, before_event
from pydantic import Field
from typing_extensions import Any, Dict

from mindtrace.apps.inspectra.models import CameraService, Organization, Plant
from mindtrace.apps.inspectra.models.enums import LineStatus
from mindtrace.database import MindtraceDocument


class Line(MindtraceDocument):
    """Line model representing a production line."""

    organization: Link[Organization]
    plant: Link[Plant]
    name: str
    status: LineStatus = LineStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    meta: Dict[str, Any] = Field(default_factory=dict)

    camera_service: Link[CameraService] = None

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
        """Beanie settings for the Line collection."""

        name = "lines"
