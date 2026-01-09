"""Plant request/response models.

Note: The Plant entity is now defined as PlantDocument in models/documents.py
using MindtraceDocument (Beanie ODM).
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class PlantBase(BaseModel):
    """Base attributes shared by all plant models."""

    name: str = Field(..., description="Plant name")
    code: str = Field(..., description="Unique plant code", min_length=1, max_length=64)
    location: Optional[str] = Field(None, description="Physical location / site name")
    is_active: bool = Field(True, description="Whether the plant is active")


class PlantCreateRequest(PlantBase):
    """Request model for creating a new plant."""
    pass


class PlantUpdateRequest(BaseModel):
    """Request model for updating an existing plant."""

    id: Optional[str] = Field(None, description="Plant ID (set from path param)")
    name: Optional[str] = Field(None, description="Updated plant name")
    location: Optional[str] = Field(None, description="Updated plant location")
    is_active: Optional[bool] = Field(None, description="Updated active flag")


class PlantResponse(PlantBase):
    """Response model representing a plant."""

    id: str = Field(..., description="Unique plant ID")


class PlantListResponse(BaseModel):
    """Response model for listing plants."""

    items: List[PlantResponse]
    total: int = Field(..., description="Total number of plants")
