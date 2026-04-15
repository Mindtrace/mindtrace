"""Line request/response schemas and TaskSchemas."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from mindtrace.apps.inspectra.core.validation import validate_no_whitespace
from mindtrace.apps.inspectra.models.enums import LineStatus
from mindtrace.core import TaskSchema


class CreatePartInput(BaseModel):
    """Single part input when creating a line (within a part group)."""

    name: Optional[str] = Field(None, description="Part name")
    part_number: Optional[str] = Field(None, description="Part number")
    stage_graph_id: Optional[str] = Field(None, description="Stage graph ID to link to this part")
    stage_graph_name: Optional[str] = Field(
        None, description="If provided, create a new stage graph with this name and link it"
    )


class CreatePartGroupInput(BaseModel):
    """Part group input when creating a line (name + at least one part)."""

    name: Optional[str] = Field(None, description="Part group name")
    parts: list[CreatePartInput] = Field(..., min_length=1, description="Parts in this group (minimum one)")


# No-whitespace regex (e.g. "mig66" ok, "mig 66" rejected).
# NOTE: this is a *regex*, so it must use \S (not a literal "\\S").
_LINE_NAME_NO_SPACES_PATTERN = r"^\S+$"
_LINE_NAME_NO_SPACES_MSG = "Line name cannot contain spaces."


class LineResponse(BaseModel):
    id: str = Field(..., description="Line ID")
    organization_id: str = Field(..., description="Organization ID")
    plant_id: str = Field(..., description="Plant ID")
    name: str = Field(..., description="Line name")
    status: LineStatus = Field(LineStatus.PENDING, description="Line status")


class CreateLineRequest(BaseModel):
    plant_id: str = Field(..., description="Plant ID (organization derived from plant)")
    model_ids: list[str] = Field(..., min_length=1, description="Model IDs to deploy for this line (one deployment per model)")
    name: str = Field(..., min_length=1, pattern=_LINE_NAME_NO_SPACES_PATTERN, description="Line name (no spaces allowed)")
    status: LineStatus = Field(LineStatus.PENDING, description="Line status")
    part_groups: list[CreatePartGroupInput] = Field(..., min_length=1, description="Part groups with their parts (at least one group, each with at least one part)")

    @field_validator("name")
    @classmethod
    def name_no_spaces(cls, v: str) -> str:
        return validate_no_whitespace(v, _LINE_NAME_NO_SPACES_MSG) or v


class UpdateLineRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, pattern=_LINE_NAME_NO_SPACES_PATTERN, description="Line name (no spaces allowed)")
    status: Optional[LineStatus] = Field(None, description="Line status")
    deployment_ids_to_remove: Optional[list[str]] = Field(None, description="Model deployment IDs to take down (set inactive, call take-down service)")
    model_ids_to_add: Optional[list[str]] = Field(None, description="Model IDs to deploy for this line (spins up new deployments)")

    @field_validator("name")
    @classmethod
    def name_no_spaces(cls, v: Optional[str]) -> Optional[str]:
        return validate_no_whitespace(v, _LINE_NAME_NO_SPACES_MSG)


class LineListResponse(BaseModel):
    items: list[LineResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class LineIdRequest(BaseModel):
    id: str = Field(..., description="Line ID")


CreateLineSchema = TaskSchema(name="inspectra_create_line", input_schema=CreateLineRequest, output_schema=LineResponse)
UpdateLineSchema = TaskSchema(name="inspectra_update_line", input_schema=UpdateLineRequest, output_schema=LineResponse)
GetLineSchema = TaskSchema(name="inspectra_get_line", input_schema=LineIdRequest, output_schema=LineResponse)
ListLinesSchema = TaskSchema(name="inspectra_list_lines", input_schema=None, output_schema=LineListResponse)

__all__ = [
    "CreateLineRequest",
    "CreatePartGroupInput",
    "CreatePartInput",
    "CreateLineSchema",
    "GetLineSchema",
    "LineIdRequest",
    "LineListResponse",
    "LineResponse",
    "ListLinesSchema",
    "UpdateLineRequest",
    "UpdateLineSchema",
]
