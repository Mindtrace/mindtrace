"""Media model for the Inspectra application."""

from datetime import datetime, timezone
from typing import Any, Dict, List

from beanie import Insert, Replace, before_event
from pydantic import Field

from mindtrace.apps.inspectra.models import (
    Camera,
    CameraSet,
    Inference,
    Line,
    Organization,
    Part,
    PartGroup,
    Plant,
    Scan,
    Stage,
)
from mindtrace.apps.inspectra.models.enums import MediaKind
from mindtrace.database import Link, MindtraceDocument


class Media(MindtraceDocument):
    """Media model representing image, mask, or heatmap files."""

    organization: Link[Organization]
    plant: Link[Plant]
    line: Link[Line]
    partgroup: Link[PartGroup]
    part: Link[Part]
    camera: Link[Camera]
    camera_set: Link[CameraSet]
    stage: Link[Stage]
    scan: Link[Scan]
    kind: MediaKind = Field(default=MediaKind.IMAGE)
    uri: str  # relative/path to the media file within the media storage bucket
    bucket: str
    inference: List[Link[Inference]] = Field(default_factory=list)
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
        """Beanie settings for the Media collection."""

        name = "medias"
