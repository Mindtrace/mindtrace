from typing import Dict, Optional, Union

from beanie import IndexModel, Link
from inspectra.backend.db.models.organization import Organization
from pydantic import Field
from typing_extensions import Any

from mindtrace.database import MindtraceDocument


class Plant(MindtraceDocument):
    org: Link[Organization]
    name: str
    location: Optional[Union[str, Dict[str, Any]]] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

    class Settings:
        name = "plants"
        indexes = [
            IndexModel([("org.$id", 1), ("name", 1)],
                       name="plant_org_name_uq", unique=True)
        ]