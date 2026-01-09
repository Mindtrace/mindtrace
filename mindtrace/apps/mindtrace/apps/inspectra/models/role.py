"""Role request/response models for RBAC.

Note: The Role entity is now defined as RoleDocument in models/documents.py
using MindtraceDocument (Beanie ODM).
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class RoleBase(BaseModel):
    """Base attributes shared by all role models."""

    name: str = Field(..., description="Role name", min_length=1)
    description: Optional[str] = Field(None, description="Role description")
    permissions: Optional[List[str]] = Field(
        default=None,
        description="List of permission identifiers",
    )


class RoleCreateRequest(RoleBase):
    """Request model for creating a new role."""
    pass


class RoleUpdateRequest(BaseModel):
    """Request model for updating an existing role."""

    id: Optional[str] = Field(None, description="Role ID (set from path param)")
    name: Optional[str] = Field(None, description="Updated role name")
    description: Optional[str] = Field(None, description="Updated role description")
    permissions: Optional[List[str]] = Field(
        default=None,
        description="Updated permissions list (full replacement)",
    )


class RoleResponse(RoleBase):
    """Response model representing a role."""

    id: str = Field(..., description="Role ID")


class RoleListResponse(BaseModel):
    """Response model for listing roles."""

    items: List[RoleResponse]
    total: int = Field(..., description="Total number of roles")
