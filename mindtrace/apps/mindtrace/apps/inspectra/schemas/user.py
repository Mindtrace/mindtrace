"""TaskSchemas for user management operations in Inspectra."""

from mindtrace.apps.inspectra.models.user import (
    ChangeOwnPasswordRequest,
    UserCreateRequest,
    UserIdRequest,
    UserListRequest,
    UserListResponse,
    UserPasswordResetRequest,
    UserResponse,
    UserUpdateRequest,
)
from mindtrace.core import TaskSchema


# Admin User Management TaskSchemas
CreateUserSchema = TaskSchema(
    name="inspectra_create_user",
    input_schema=UserCreateRequest,
    output_schema=UserResponse,
)

UpdateUserSchema = TaskSchema(
    name="inspectra_update_user",
    input_schema=UserUpdateRequest,
    output_schema=UserResponse,
)

DeleteUserSchema = TaskSchema(
    name="inspectra_delete_user",
    input_schema=UserIdRequest,
    output_schema=None,
)

ListUsersSchema = TaskSchema(
    name="inspectra_list_users",
    input_schema=UserListRequest,
    output_schema=UserListResponse,
)

GetUserSchema = TaskSchema(
    name="inspectra_get_user",
    input_schema=UserIdRequest,
    output_schema=UserResponse,
)

ResetUserPasswordSchema = TaskSchema(
    name="inspectra_reset_user_password",
    input_schema=UserPasswordResetRequest,
    output_schema=None,
)

ActivateUserSchema = TaskSchema(
    name="inspectra_activate_user",
    input_schema=UserIdRequest,
    output_schema=UserResponse,
)

DeactivateUserSchema = TaskSchema(
    name="inspectra_deactivate_user",
    input_schema=UserIdRequest,
    output_schema=UserResponse,
)

# Self-Service TaskSchemas
GetOwnProfileSchema = TaskSchema(
    name="inspectra_get_own_profile",
    input_schema=None,
    output_schema=UserResponse,
)

ChangeOwnPasswordSchema = TaskSchema(
    name="inspectra_change_own_password",
    input_schema=ChangeOwnPasswordRequest,
    output_schema=None,
)

__all__ = [
    # Re-export models for convenience
    "UserIdRequest",
    "UserResponse",
    "UserListResponse",
    # Admin schemas
    "CreateUserSchema",
    "UpdateUserSchema",
    "DeleteUserSchema",
    "ListUsersSchema",
    "GetUserSchema",
    "ResetUserPasswordSchema",
    "ActivateUserSchema",
    "DeactivateUserSchema",
    # Self-service schemas
    "GetOwnProfileSchema",
    "ChangeOwnPasswordSchema",
]
