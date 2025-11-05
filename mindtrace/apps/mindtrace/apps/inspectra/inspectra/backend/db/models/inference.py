from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from beanie import IndexModel, Link, PydanticObjectId
from inspectra.backend.db.models.brain import Model
from inspectra.backend.db.models.camera import Camera
from inspectra.backend.db.models.line import Line
from inspectra.backend.db.models.location_scan import LocationScan
from inspectra.backend.db.models.media import Media
from inspectra.backend.db.models.organization import Organization
from inspectra.backend.db.models.part_scan import PartScan
from inspectra.backend.db.models.plant import Plant
from pydantic import Field

from mindtrace.database import MindtraceDocument

# ========= Inference (single-result row; semantic contract + base fields + extras) =========

class Inference(MindtraceDocument):
    # links + denorm (for fast filters)
    location_scan: Link[LocationScan]
    location_scan_id: PydanticObjectId

    part_scan: Link[PartScan]
    part_code: Union[int, str]
    part_name: Optional[str] = None

    line: Link[Line]
    line_id: PydanticObjectId
    line_name: str

    plant: Link[Plant]
    plant_id: PydanticObjectId

    org: Link[Organization]
    org_id: PydanticObjectId

    camera: Link[Camera]
    camera_id: PydanticObjectId
    camera_name: str

    model: Link[Model]
    model_ver: str

    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    run_id: Optional[Union[str, PydanticObjectId]] = None

    # semantic grouping only (no enforcement right now)
    contract_name: str   # e.g., "visual_inspection", "location_presence_check", "assembly_inspection", "other"

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

    input_media: Link[Media]
    artifacts: List[Link[Media]] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)

    class Settings:
        name = "inferences"
        indexes = [
            # scope & time
            IndexModel([("org_id", 1), ("plant_id", 1), ("line_id", 1), ("created_at", -1)],
                       name="inf_scope_time"),
            IndexModel([("line_id", 1), ("created_at", -1)],
                       name="inf_line_time"),
            IndexModel([("line_name", 1), ("created_at", -1)],
                       name="inf_linename_time"),
            IndexModel([("camera_name", 1), ("created_at", -1)],
                       name="inf_camname_time"),
            IndexModel([("part_code", 1), ("created_at", -1)],
                       name="inf_part_time"),
            IndexModel([("contract_name", 1), ("created_at", -1)],
                       name="inf_contract_time"),
            # (optional) one row per (capture, model, version, contract, label)
            IndexModel([("location_scan.$id", 1), ("model.$id", 1), ("model_ver", 1),
                        ("contract_name", 1), ("label", 1)],
                       name="inf_unique", unique=True, sparse=True),
        ]