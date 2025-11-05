from datetime import datetime, timezone
from typing import List

from beanie import IndexModel, Link, PydanticObjectId
from inspectra.backend.db.models.plant import Plant
from pydantic import Field
from typing_extensions import Any, Dict

from mindtrace.database import MindtraceDocument


class Line(MindtraceDocument):
    plant: Link[Plant]
    name: str
    active: bool = True
    supported_part_ids: List[PydanticObjectId] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    meta: Dict[str, Any] = Field(default_factory=dict)

    class Settings:
        name = "lines"
        indexes = [IndexModel([("plant.$id", 1), ("name", 1)], name="line_plant_name_uq", unique=True)]
