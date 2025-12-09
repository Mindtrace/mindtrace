from typing import List

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema


class UserResponse(BaseModel):
    """API-safe representation of a user (no password hash)."""

    id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    role_id: str = Field(..., description="Role ID")
    is_active: bool = Field(True, description="Whether the user is active")


class UserListResponse(BaseModel):
    """Response model for listing users."""

    items: List[UserResponse]
    total: int = Field(..., description="Total number of users")


class UserIdRequest(BaseModel):
    id: str = Field(..., description="User ID")


ListUsersSchema = TaskSchema(
    name="list_users",
    input_schema=None,
    output_schema=UserListResponse,
)

GetUserSchema = TaskSchema(
    name="get_user",
    input_schema=UserIdRequest,
    output_schema=UserResponse,
)

__all__ = [
    "UserResponse",
    "UserListResponse",
    "UserIdRequest",
    "ListUsersSchema",
    "GetUserSchema",
]