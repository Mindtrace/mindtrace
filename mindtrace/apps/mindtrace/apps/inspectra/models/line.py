"""Line request/response models.

Note: The Line entity is now defined as LineDocument in models/documents.py
using MindtraceDocument (Beanie ODM).
"""

from typing import List, Optional

from pydantic import BaseModel, Field


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


class LineUpdateRequest(BaseModel):
    """Request model for updating an existing line."""

    id: Optional[str] = Field(None, description="Line ID (set from path param)")
    name: Optional[str] = Field(None, description="Updated line name")
    plant_id: Optional[str] = Field(None, description="Updated plant ID")


class LineIdRequest(BaseModel):
    """Request with line ID."""

    id: str = Field(..., description="Line ID")
