"""User model and request/response models for user management."""

from dataclasses import dataclass
from typing import List, Optional

from pydantic import BaseModel, Field


@dataclass
class User:
    """User dataclass for internal use."""

    id: str
    username: str
    password_hash: str
    role_id: str
    plant_id: Optional[str] = None
    is_active: bool = True


# Request/Response models for User Management


class UserCreateRequest(BaseModel):
    """Admin request to create a new user."""

    username: str = Field(..., min_length=1, description="Username")
    password: str = Field(..., min_length=1, description="Initial password")
    role_id: Optional[str] = Field(None, description="Role ID (defaults to 'user' role)")
    plant_id: Optional[str] = Field(None, description="Plant/org ID the user belongs to")
    is_active: bool = Field(True, description="Whether user is active")


class UserUpdateRequest(BaseModel):
    """Admin request to update a user."""

    id: str = Field(..., description="User ID")
    role_id: Optional[str] = Field(None, description="Updated role ID")
    plant_id: Optional[str] = Field(None, description="Updated plant/org ID")
    is_active: Optional[bool] = Field(None, description="Updated active status")


class UserPasswordResetRequest(BaseModel):
    """Admin request to reset a user's password."""

    id: str = Field(..., description="User ID")
    new_password: str = Field(..., min_length=1, description="New password")


class ChangeOwnPasswordRequest(BaseModel):
    """User request to change own password."""

    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., description="New password")


class UserResponse(BaseModel):
    """API-safe user representation (no password hash)."""

    id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    role_id: str = Field(..., description="Role ID")
    plant_id: Optional[str] = Field(None, description="Plant/org ID")
    is_active: bool = Field(..., description="Whether user is active")


class UserListRequest(BaseModel):
    """Request for listing users with filters and pagination."""

    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(50, ge=1, le=100, description="Items per page")
    is_active: Optional[bool] = Field(None, description="Filter by active status")
    role_id: Optional[str] = Field(None, description="Filter by role")
    plant_id: Optional[str] = Field(None, description="Filter by plant/org")
    search: Optional[str] = Field(None, description="Search by username")


class UserListResponse(BaseModel):
    """Paginated user list response."""

    items: List[UserResponse] = Field(..., description="List of users")
    total: int = Field(..., description="Total number of users matching filters")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")


class UserIdRequest(BaseModel):
    """Request with user ID."""

    id: str = Field(..., description="User ID")
