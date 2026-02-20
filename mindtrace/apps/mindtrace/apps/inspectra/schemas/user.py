"""User request/response schemas and TaskSchemas."""

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from mindtrace.apps.inspectra.models.enums import UserRole, UserStatus
from mindtrace.core import TaskSchema


class UserResponse(BaseModel):
    """User API response (no password)."""

    id: str = Field(..., description="User ID")
    email: str = Field(..., description="Email")
    role: UserRole = Field(..., description="User role")
    organization_id: str = Field(..., description="Organization ID")
    first_name: str = Field(..., description="First name")
    last_name: str = Field(..., description="Last name")
    status: UserStatus = Field(..., description="User account status (active or inactive).")


class CreateUserRequest(BaseModel):
    """Create user request (admin/super_admin only)."""

    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=1, description="Password")
    role: UserRole = Field(..., description="User role")
    organization_id: str = Field(..., description="Organization ID")
    first_name: str = Field(..., min_length=1, description="First name")
    last_name: str = Field(..., min_length=1, description="Last name")


class UpdateUserRequest(BaseModel):
    """Update user profile: name, role, or status. ID is in the URL path. Omit fields to leave unchanged."""

    first_name: Optional[str] = Field(None, min_length=1, description="First name")
    last_name: Optional[str] = Field(None, min_length=1, description="Last name")
    role: Optional[UserRole] = Field(None, description="User role (ADMIN cannot set SUPER_ADMIN)")
    status: Optional[UserStatus] = Field(None, description="Account status: active or inactive.")


class UserListResponse(BaseModel):
    """List users response."""

    items: List[UserResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class UserIdRequest(BaseModel):
    """User ID path/query."""

    id: str = Field(..., description="User ID")


CreateUserSchema = TaskSchema(
    name="inspectra_create_user",
    input_schema=CreateUserRequest,
    output_schema=UserResponse,
)

UpdateUserSchema = TaskSchema(
    name="inspectra_update_user",
    input_schema=UpdateUserRequest,
    output_schema=UserResponse,
)

GetUserSchema = TaskSchema(
    name="inspectra_get_user",
    input_schema=UserIdRequest,
    output_schema=UserResponse,
)

ListUsersSchema = TaskSchema(
    name="inspectra_list_users",
    input_schema=None,
    output_schema=UserListResponse,
)

__all__ = [
    "CreateUserRequest",
    "CreateUserSchema",
    "GetUserSchema",
    "ListUsersSchema",
    "UpdateUserRequest",
    "UpdateUserSchema",
    "UserIdRequest",
    "UserListResponse",
    "UserResponse",
]
