"""Scan model for the Inspectra application."""

from datetime import datetime, timezone
from typing import Any, Dict, List

from beanie import Insert, Link, Replace, before_event
from pydantic import Field

from mindtrace.apps.inspectra.models import Line, Media, Organization, Part, PartGroup, Plant
from mindtrace.apps.inspectra.models.enums import ScanResult
from mindtrace.database import MindtraceDocument


class Scan(MindtraceDocument):
    """Scan model representing a single scan/inspection of a part."""

    organization: Link[Organization]
    plant: Link[Plant]
    line: Link[Line]
    partgroup: Link[PartGroup]
    part: Link[Part]
    serial: str
    cls_result: ScanResult = ScanResult.UNKNOWN
    # View results are custom fields for the client to use and create display
    # conditions based on the Inferences
    view_result0: ScanResult = ScanResult.UNKNOWN
    view_result1: ScanResult = ScanResult.UNKNOWN
    view_result2: ScanResult = ScanResult.UNKNOWN
    view_result3: ScanResult = ScanResult.UNKNOWN
    view_result4: ScanResult = ScanResult.UNKNOWN

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    media: List[Link[Media]] = Field(default_factory=list)

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
        """Beanie settings for the Scan collection."""

        name = "scans"
