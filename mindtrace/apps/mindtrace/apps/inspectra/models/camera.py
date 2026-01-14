"""Camera model for the Inspectra application."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from beanie import Insert, Replace, before_event
from pydantic import BaseModel, Field

from mindtrace.apps.inspectra.models import CameraPosition, CameraService, CameraSet, Line
from mindtrace.database import Link, MindtraceDocument


class CameraConfig(BaseModel):
    """Configuration settings for a camera."""

    exposure_ms: Optional[int] = None
    white_balance: Optional[str] = None


class Camera(MindtraceDocument):
    """Camera model representing a physical camera device."""

    line: Link[Line]
    name: str  # e.g. "cam_1" or "w_11"
    camera_service: Link[CameraService]
    camera_set: Link[CameraSet]
    camera_position: Link[CameraPosition]
    config: CameraConfig = Field(default_factory=CameraConfig)
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
        """Beanie settings for the Camera collection."""

        name = "cameras"
