"""TaskSchemas for plant-related operations in Inspectra."""

from pydantic import BaseModel, Field

from mindtrace.apps.inspectra.models import (
    PlantCreateRequest,
    PlantListResponse,
    PlantResponse,
    PlantUpdateRequest,
)
from mindtrace.core import TaskSchema


class PlantIdRequest(BaseModel):
    id: str = Field(..., description="Plant ID")


CreatePlantSchema = TaskSchema(
    name="inspectra_create_plant",
    input_schema=PlantCreateRequest,
    output_schema=PlantResponse,
)

UpdatePlantSchema = TaskSchema(
    name="inspectra_update_plant",
    input_schema=PlantUpdateRequest,
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

DeletePlantSchema = TaskSchema(
    name="inspectra_delete_plant",
    input_schema=PlantIdRequest,
    output_schema=None,
)

__all__ = [
    "CreatePlantSchema",
    "UpdatePlantSchema",
    "GetPlantSchema",
    "ListPlantsSchema",
    "DeletePlantSchema",
    "PlantIdRequest",
]
