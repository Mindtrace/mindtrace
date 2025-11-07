from datetime import datetime, timezone
from typing import Any, Dict

from pydantic import Field
from pymongo import IndexModel

from mindtrace.database import MindtraceDocument


class Model(MindtraceDocument):
    name: str
    version: str
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    meta: Dict[str, Any] = Field(default_factory=dict)

    class Settings:
        name = "models"
        indexes = [IndexModel([("name", 1), ("version", 1)], name="model_name_version_uq", unique=True)]
