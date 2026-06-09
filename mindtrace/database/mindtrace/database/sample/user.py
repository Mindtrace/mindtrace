from datetime import datetime

from pydantic import BaseModel, Field

from mindtrace.core import utcnow


class User(BaseModel):
    name: str
    id: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
