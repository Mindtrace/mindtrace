from dataclasses import dataclass
from typing import List, Optional

from pydantic import BaseModel, Field


@dataclass
class Line:
    id: str
    name: str
    plant_id: Optional[str] = None

class LineCreateRequest(BaseModel):
    """Payload for creating a new line."""

    name: str = Field(..., description="Line name")
    plant_id: Optional[str] = Field(
        default=None,
        description="Associated plant ID (if any)",
    )


class LineResponse(BaseModel):
    """Response model representing a production line."""

    id: str = Field(..., description="Line ID")
    name: str = Field(..., description="Line name")
    plant_id: Optional[str] = Field(
        default=None,
        description="Associated plant ID (if any)",
    )


class LineListResponse(BaseModel):
    """Response model for listing lines."""

    items: List[LineResponse]
    total: int = Field(..., description="Total number of lines")
    
