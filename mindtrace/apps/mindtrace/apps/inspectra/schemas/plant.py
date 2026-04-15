"""Plant request/response schemas and TaskSchemas."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from mindtrace.apps.inspectra.core.validation import validate_no_whitespace
from mindtrace.core import TaskSchema

# Plant names must not contain spaces (enforced in create/update).
_PLANT_NAME_NO_SPACES_PATTERN = r"^\S+$"
_PLANT_NAME_NO_SPACES_MSG = "Plant name cannot contain spaces."


class PlantResponse(BaseModel):
    """Plant API response."""

    id: str = Field(..., description="Plant ID")
    organization_id: str = Field(..., description="Organization ID")
    name: str = Field(..., description="Plant name")
    location: Optional[str] = Field(None, description="Plant location")


class CreatePlantRequest(BaseModel):
    """Create plant request."""

    organization_id: str = Field(..., description="Organization ID")
    name: str = Field(
        ...,
        min_length=1,
        pattern=_PLANT_NAME_NO_SPACES_PATTERN,
        description="Plant name (no spaces allowed)",
    )
    location: Optional[str] = Field(None, description="Plant location")

    @field_validator("name")
    @classmethod
    def name_no_spaces(cls, v: str) -> str:
        return validate_no_whitespace(v, _PLANT_NAME_NO_SPACES_MSG) or v


class UpdatePlantRequest(BaseModel):
    """Update plant request. ID is in the URL path."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        pattern=_PLANT_NAME_NO_SPACES_PATTERN,
        description="Plant name (no spaces allowed)",
    )
    location: Optional[str] = Field(None, description="Plant location")

    @field_validator("name")
    @classmethod
    def name_no_spaces(cls, v: Optional[str]) -> Optional[str]:
        return validate_no_whitespace(v, _PLANT_NAME_NO_SPACES_MSG)


class PlantListResponse(BaseModel):
    """List plants response."""

    items: list[PlantResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class PlantIdRequest(BaseModel):
    """Plant ID path/query."""

    id: str = Field(..., description="Plant ID")


CreatePlantSchema = TaskSchema(
    name="inspectra_create_plant",
    input_schema=CreatePlantRequest,
    output_schema=PlantResponse,
)

UpdatePlantSchema = TaskSchema(
    name="inspectra_update_plant",
    input_schema=UpdatePlantRequest,
    output_schema=PlantResponse,
)

GetPlantSchema = TaskSchema(
    name="inspectra_get_plant",
    input_schema=PlantIdRequest,
    output_schema=PlantResponse,
)

ListPlantsSchema = TaskSchema(
    name="inspectra_list_plants",
    input_schema=None,
    output_schema=PlantListResponse,
)

__all__ = [
    "CreatePlantRequest",
    "CreatePlantSchema",
    "GetPlantSchema",
    "ListPlantsSchema",
    "PlantIdRequest",
    "PlantListResponse",
    "PlantResponse",
    "UpdatePlantRequest",
    "UpdatePlantSchema",
]
