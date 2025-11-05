from datetime import datetime, timezone
from typing import Any, Dict, Optional

from beanie import IndexModel, Link
from inspectra.backend.db.models.line import Line
from pydantic import BaseModel, Field

from mindtrace.database import MindtraceDocument


class CameraConfig(BaseModel):
    exposure_ms: Optional[int] = None
    gain: Optional[float] = None
    white_balance: Optional[str] = None
    lens: Optional[str] = None
    # TODO: add more config fields as needed


class Camera(MindtraceDocument):
    line: Link[Line]
    camera_id: str  # device/location id
    name: str  # e.g. "cam_1" or "w_11"
    config: CameraConfig = Field(default_factory=CameraConfig)
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    meta: Dict[str, Any] = Field(default_factory=dict)

    class Settings:
        name = "cameras"
        indexes = [
            IndexModel([("line.$id", 1), ("camera_id", 1)], name="cam_line_cameraid_uq", unique=True),
            IndexModel([("line.$id", 1), ("name", 1)], name="cam_line_name"),
        ]
