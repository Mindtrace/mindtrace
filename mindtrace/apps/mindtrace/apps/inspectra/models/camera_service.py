"""Camera service model for the Inspectra application."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from beanie import Insert, Replace, before_event
from pydantic import Field

from mindtrace.apps.inspectra.models import Line
from mindtrace.apps.inspectra.models.enums import CameraBackend, DeploymentStatus, HealthStatus
from mindtrace.database import Link, MindtraceDocument


class CameraService(MindtraceDocument):
    """Camera service model representing a camera service instance."""

    line: Link[Line]

    cam_service_status: DeploymentStatus = DeploymentStatus.PENDING
    cam_service_url: str

    max_concurrent_captures: int = 1

    health_status: HealthStatus = HealthStatus.UNKNOWN
    last_health_check: Optional[datetime] = None

    backend: CameraBackend = CameraBackend.BASLER

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
        """Beanie settings for the CameraService collection."""

        name = "camera_services"
