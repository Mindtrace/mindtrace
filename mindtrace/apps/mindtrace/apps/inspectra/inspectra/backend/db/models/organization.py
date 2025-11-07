from datetime import datetime, timezone

from pydantic import Field
from pymongo import IndexModel
from typing_extensions import Any, Dict

from mindtrace.database import MindtraceDocument


class Organization(MindtraceDocument):
    name: str
    meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "organizations"
        indexes = [IndexModel([("name", 1)], name="org_name_uq", unique=True)]
