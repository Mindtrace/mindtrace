from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional, Union

from beanie import Link, PydanticObjectId
from inspectra.backend.db.models.camera import Camera
from inspectra.backend.db.models.line import Line
from inspectra.backend.db.models.media import Media
from inspectra.backend.db.models.organization import Organization
from inspectra.backend.db.models.part_scan import PartScan
from inspectra.backend.db.models.plant import Plant
from pydantic import Field
from pymongo import IndexModel

from mindtrace.database import MindtraceDocument


class LocationScan(MindtraceDocument):  # per camera/location shot
    part_scan: Link[PartScan]
    line: Link[Line]
    plant: Link[Plant]
    org: Link[Organization]
    camera: Link[Camera]

    # denorm hot filters
    location_name: str  #  w_11 or cam_1, could be used for queries

    line_id: PydanticObjectId
    line_name: str
    camera_id: PydanticObjectId
    camera_name: str
    part_code: Union[int, str]
    part_name: Optional[str] = None

    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    input_media: Link[Media]
    meta: Dict[str, Any] = Field(default_factory=dict)
    is_defective: Literal["Unknown", "Healthy", "Defective"] = "Unknown"  # hot part filter

    class Settings:
        name = "location_scans"
        indexes = [
            IndexModel([("part_scan.$id", 1), ("captured_at", 1)], name="ls_part_time"),
            IndexModel([("line_id", 1), ("camera_name", 1), ("captured_at", -1)], name="ls_line_cam_time"),
            IndexModel([("camera_id", 1), ("captured_at", -1)], name="ls_camera_time"),
        ]
