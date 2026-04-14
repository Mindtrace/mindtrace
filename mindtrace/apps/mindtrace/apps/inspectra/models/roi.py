"""ROI (Region of Interest) model for the Inspectra application."""

from datetime import datetime, timezone
from typing import Any, Dict, List

from beanie import Insert, Replace, before_event
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from mindtrace.apps.inspectra.models.enums import RoiType
from mindtrace.database import Link, MindtraceDocument

from .camera import Camera
from .camera_position import CameraPosition
from .camera_set import CameraSet
from .line import Line
from .model_deployment import ModelDeployment
from .stage import Stage


class Roi(MindtraceDocument):
    """ROI (Region of Interest) model representing a region of interest in an image."""

    line: Link[Line]
    name: str
    camera: Link[Camera]
    camera_position: Link[CameraPosition]
    camera_set: Link[CameraSet]
    stage: Link[Stage]
    type: RoiType
    points: List[List[float]]  # [[x, y], [x, y], ...]
    holes: List[List[List[float]]] = Field(default_factory=list)  # [[[x, y], [x, y], ...], ...]
    model_deployment: Link[ModelDeployment]
    active: bool = True

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
        """Beanie settings for the Roi collection."""

        name = "rois"
        indexes = [
            IndexModel([("line", ASCENDING), ("name", ASCENDING)], unique=True),
        ]
