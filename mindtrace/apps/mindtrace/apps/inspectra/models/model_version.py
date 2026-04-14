"""Model version model for the Inspectra application."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict

from beanie import Insert, Replace, before_event
from pydantic import Field

from mindtrace.database import Link, MindtraceDocument

if TYPE_CHECKING:
    from .model_deployment import ModelDeployment

from .model import Model


class ModelVersion(MindtraceDocument):
    """Model version model representing a specific version of a model."""

    model: Link[Model]
    model_deployment: Link["ModelDeployment"] | None = None  # noqa: F821
    version: str
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
        """Beanie settings for the ModelVersion collection."""

        name = "model_versions"
