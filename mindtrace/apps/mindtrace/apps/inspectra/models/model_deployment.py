"""Model deployment model for the Inspectra application."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from beanie import Insert, Replace, before_event
from pydantic import Field

from mindtrace.apps.inspectra.models import Line, Model, ModelVersion, Organization, Plant
from mindtrace.apps.inspectra.models.enums import DeploymentStatus, HealthStatus
from mindtrace.database import Link, MindtraceDocument


class ModelDeployment(MindtraceDocument):
    """Model deployment model representing a deployed model instance."""

    organization: Link[Organization]
    plant: Link[Plant]
    line: Link[Line]
    model: Link[Model]

    version: Link[ModelVersion]
    deployment_status: DeploymentStatus = DeploymentStatus.PENDING
    model_server_url: str

    health_status: HealthStatus = HealthStatus.UNKNOWN
    last_health_check: Optional[datetime] = None

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
        """Beanie settings for the ModelDeployment collection."""

        name = "model_deployments"
