"""Organization request/response schemas and TaskSchemas."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from mindtrace.apps.inspectra.core.validation import validate_no_whitespace
from mindtrace.apps.inspectra.models.enums import OrganizationStatus
from mindtrace.core import TaskSchema

# Organization names must not contain spaces (enforced in create/update).
_ORG_NAME_NO_SPACES_PATTERN = r"^\S+$"
_ORG_NAME_NO_SPACES_MSG = "Organization name cannot contain spaces."


class OrganizationResponse(BaseModel):
    """Organization API response."""

    id: str = Field(..., description="Organization ID")
    name: str = Field(..., description="Organization name")
    status: OrganizationStatus = Field(
        OrganizationStatus.ACTIVE,
        description="Organization status (active or disabled).",
    )
    is_active: bool = Field(
        True,
        description="True when status is active (backward compatibility).",
    )


class CreateOrganizationRequest(BaseModel):
    """Create organization request."""

    name: str = Field(
        ...,
        min_length=1,
        pattern=_ORG_NAME_NO_SPACES_PATTERN,
        description="Organization name (no spaces allowed)",
    )

    @field_validator("name")
    @classmethod
    def name_no_spaces(cls, v: str) -> str:
        """Reject organization names that contain any whitespace; raises ValueError if invalid."""
        return validate_no_whitespace(v, _ORG_NAME_NO_SPACES_MSG) or v


class UpdateOrganizationRequest(BaseModel):
    """Update organization: name and/or status. ID is in the URL path."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        pattern=_ORG_NAME_NO_SPACES_PATTERN,
        description="New organization name, no spaces (omit to leave unchanged)",
    )
    status: Optional[OrganizationStatus] = Field(
        None,
        description="Set to disabled to deactivate (omit to leave unchanged).",
    )
    is_active: Optional[bool] = Field(
        None,
        description="If set, maps to status: False -> disabled, True -> active. Prefer status.",
    )

    @field_validator("name")
    @classmethod
    def name_no_spaces(cls, v: Optional[str]) -> Optional[str]:
        """Reject organization names that contain any whitespace; raises ValueError if invalid."""
        return validate_no_whitespace(v, _ORG_NAME_NO_SPACES_MSG)


class OrganizationListResponse(BaseModel):
    """List organizations response."""

    items: list[OrganizationResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class OrganizationIdRequest(BaseModel):
    """Organization ID path/query."""

    id: str = Field(..., description="Organization ID")


CreateOrganizationSchema = TaskSchema(
    name="inspectra_create_organization",
    input_schema=CreateOrganizationRequest,
    output_schema=OrganizationResponse,
)

UpdateOrganizationSchema = TaskSchema(
    name="inspectra_update_organization",
    input_schema=UpdateOrganizationRequest,
    output_schema=OrganizationResponse,
)

GetOrganizationSchema = TaskSchema(
    name="inspectra_get_organization",
    input_schema=OrganizationIdRequest,
    output_schema=OrganizationResponse,
)

ListOrganizationsSchema = TaskSchema(
    name="inspectra_list_organizations",
    input_schema=None,
    output_schema=OrganizationListResponse,
)

__all__ = [
    "CreateOrganizationRequest",
    "CreateOrganizationSchema",
    "GetOrganizationSchema",
    "ListOrganizationsSchema",
    "OrganizationIdRequest",
    "OrganizationListResponse",
    "OrganizationResponse",
    "UpdateOrganizationRequest",
    "UpdateOrganizationSchema",
]
