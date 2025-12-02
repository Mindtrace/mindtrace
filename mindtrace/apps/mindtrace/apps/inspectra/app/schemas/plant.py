from pydantic import BaseModel
from typing import Optional

class PlantCreate(BaseModel):
    name: str
    location: Optional[str] = None

class PlantResponse(BaseModel):
    id: str
    name: str
    location: Optional[str] = None
