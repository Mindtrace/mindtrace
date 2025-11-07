from datetime import datetime

from pydantic import BaseModel, Field


class User(BaseModel):
    name: str
    id: int | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
