"""TaskSchemas for role-related operations in Inspectra."""

from pydantic import BaseModel, Field

from mindtrace.apps.inspectra.models import (
    RoleCreateRequest,
    RoleListResponse,
    RoleResponse,
    RoleUpdateRequest,
)
from mindtrace.core import TaskSchema


class RoleIdRequest(BaseModel):
    id: str = Field(..., description="Role ID")


CreateRoleSchema = TaskSchema(
    name="inspectra_create_role",
    input_schema=RoleCreateRequest,
    output_schema=RoleResponse,
)

UpdateRoleSchema = TaskSchema(
    name="inspectra_update_role",
    input_schema=RoleUpdateRequest,
    output_schema=RoleResponse,
)

GetRoleSchema = TaskSchema(
    name="inspectra_get_role",
    input_schema=RoleIdRequest,
    output_schema=RoleResponse,
)

ListRolesSchema = TaskSchema(
    name="inspectra_list_roles",
    input_schema=None,
    output_schema=RoleListResponse,
)

__all__ = [
    "CreateRoleSchema",
    "UpdateRoleSchema",
    "GetRoleSchema",
    "ListRolesSchema",
    "RoleIdRequest",
]
