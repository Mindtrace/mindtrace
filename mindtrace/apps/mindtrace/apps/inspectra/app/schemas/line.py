from pydantic import BaseModel
from typing import Optional

class LineCreate(BaseModel):
    name: str
    plant_id: Optional[str] = None

class LineResponse(BaseModel):
    id: str
    name: str
    plant_id: Optional[str] = None
