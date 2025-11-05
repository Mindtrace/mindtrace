from typing import Union

from beanie import IndexModel, Link
from inspectra.backend.db.models.line import Line
from inspectra.backend.db.models.organization import Organization
from pydantic import Field
from typing_extensions import Any, Dict, Optional

from mindtrace.database import MindtraceDocument


class Part(MindtraceDocument):
    org: Link[Organization]
    line: Link[Line]
    code: Union[int, str]
    name: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

    class Settings:
        name = "parts"
        indexes = [IndexModel([("org.$id", 1), ("code", 1)], name="part_org_code_uq", unique=True)]
