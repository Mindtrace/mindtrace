from datetime import datetime
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from inspectra.schemas.user_schema import PyObjectId


class InspectionSchema(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id")
    inspector_id: PyObjectId
    item_name: str
    result: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True
        arbitrary_types_allowed = True
