"""Stage request/response schemas and TaskSchemas."""

from typing import Optional

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema


class StageResponse(BaseModel):
    id: str = Field(..., description="Stage ID")
    name: str = Field(..., description="Stage name")


class StageListResponse(BaseModel):
    items: list[StageResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class CreateStageRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Stage name")


class StageIdRequest(BaseModel):
    id: str = Field(..., description="Stage ID")


ListStagesSchema = TaskSchema(
    name="inspectra_list_stages",
    input_schema=None,
    output_schema=StageListResponse,
)

CreateStageSchema = TaskSchema(
    name="inspectra_create_stage",
    input_schema=CreateStageRequest,
    output_schema=StageResponse,
)

GetStageSchema = TaskSchema(
    name="inspectra_get_stage",
    input_schema=StageIdRequest,
    output_schema=StageResponse,
)

__all__ = [
    "CreateStageRequest",
    "CreateStageSchema",
    "GetStageSchema",
    "ListStagesSchema",
    "StageIdRequest",
    "StageListResponse",
    "StageResponse",
]

