from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional, Union

from beanie import Link
from inspectra.backend.db.models.line import Line
from inspectra.backend.db.models.organization import Organization
from inspectra.backend.db.models.part import Part
from inspectra.backend.db.models.plant import Plant
from pydantic import Field
from pymongo import IndexModel

from mindtrace.database import MindtraceDocument


class PartScan(MindtraceDocument):  # immutable parent of part scans, i.e. single scan of a part
    line: Link[Line]
    plant: Link[Plant]
    org: Link[Organization]
    part: Link[Part]
    part_code: Union[int, str]
    part_name: Optional[str] = None
    serial: Optional[str] = None
    scanned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_defective: Literal["Unknown", "Healthy", "Defective"] = "Unknown"
    meta: Dict[str, Any] = Field(default_factory=dict)

    class Settings:
        name = "part_scans"
        indexes = [
            IndexModel([("line.$id", 1), ("scanned_at", -1)], name="ps_line_scanned"),
            IndexModel([("plant.$id", 1), ("scanned_at", -1)], name="ps_plant_scanned"),
            IndexModel([("org.$id", 1), ("scanned_at", -1)], name="ps_org_scanned"),
            IndexModel([("part_code", 1), ("scanned_at", -1)], name="ps_part_time"),
        ]
