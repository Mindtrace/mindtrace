"""Inference model for the Inspectra application."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from beanie import Insert, Link, Replace, before_event
from pydantic import Field

from mindtrace.database import MindtraceDocument

from .camera import Camera
from .camera_set import CameraSet
from .line import Line
from .model_deployment import ModelDeployment
from .model_version import ModelVersion
from .organization import Organization
from .part import Part
from .part_group import PartGroup
from .plant import Plant
from .roi import Roi
from .scan import Scan
from .stage import Stage

if TYPE_CHECKING:
    from .media import Media


class Inference(MindtraceDocument):
    """Inference model representing a single inference result from a model."""

    organization: Link[Organization]
    plant: Link[Plant]
    line: Link[Line]
    partgroup: Link[PartGroup]
    part: Link[Part]
    camera: Link[Camera]
    camera_set: Link[CameraSet]
    stage: Link[Stage]
    scan: Link[Scan]
    model_deployment: Link[ModelDeployment]
    model_version: Link[ModelVersion]
    model_version: str  # field to cache the model version
    roi: Link[Roi]

    # canonical queryable fields (all optional for now)
    # classification
    label: Optional[str] = None
    confidence: Optional[float] = None
    # presence
    present: Optional[bool] = None
    quantity: Optional[float] = None
    # severity / regression
    value: Optional[float] = None
    severity: Optional[float] = None
    unit: Optional[str] = None
    # detection / geometry
    bboxes: Optional[List[Dict[str, Any]]] = None
    # keypoints
    kpoints: Optional[List[Dict[str, Any]]] = None

    # non-indexed, contract-specific payload. everything else goes here.
    extras: Dict[str, Any] = Field(default_factory=dict)
    extras_ver: int = 1

    media: Link[Media]  # noqa: F821
    artifacts: List[Link[Media]] = Field(default_factory=list)  # noqa: F821
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
        """Beanie settings for the Inference collection."""

        name = "inferences"
