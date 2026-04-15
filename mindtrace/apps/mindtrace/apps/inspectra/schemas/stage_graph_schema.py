"""Stage graph request/response schemas and TaskSchemas."""

from typing import Optional

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema


class StageGraphStageItem(BaseModel):
    stage_id: str = Field(..., description="Stage ID")
    order: int = Field(..., ge=0, description="Stage order (0-based). Same order = parallel.")
    label: Optional[str] = Field(None, description="Optional label/alias within the graph")


class StageGraphStageResponse(StageGraphStageItem):
    stage_name: Optional[str] = Field(None, description="Resolved stage name")


class StageGraphResponse(BaseModel):
    id: str = Field(..., description="Stage graph ID")
    name: str = Field(..., description="Stage graph name")
    stage_count: int = Field(..., ge=0, description="Number of stages in this graph")
    stages: Optional[list[StageGraphStageResponse]] = Field(
        None, description="Stage entries (included for get/update)"
    )


class StageGraphListResponse(BaseModel):
    items: list[StageGraphResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class ListStageGraphsRequest(BaseModel):
    skip: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=500)


class CreateStageGraphRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Stage graph name")


class StageGraphIdRequest(BaseModel):
    id: str = Field(..., description="Stage graph ID")


class UpdateStageGraphStagesRequest(BaseModel):
    stages: list[StageGraphStageItem] = Field(default_factory=list, description="Stage entries list")


ListStageGraphsSchema = TaskSchema(
    name="inspectra_list_stage_graphs",
    input_schema=None,
    output_schema=StageGraphListResponse,
)

CreateStageGraphSchema = TaskSchema(
    name="inspectra_create_stage_graph",
    input_schema=CreateStageGraphRequest,
    output_schema=StageGraphResponse,
)

GetStageGraphSchema = TaskSchema(
    name="inspectra_get_stage_graph",
    input_schema=StageGraphIdRequest,
    output_schema=StageGraphResponse,
)

UpdateStageGraphStagesSchema = TaskSchema(
    name="inspectra_update_stage_graph_stages",
    input_schema=UpdateStageGraphStagesRequest,
    output_schema=StageGraphResponse,
)

__all__ = [
    "CreateStageGraphRequest",
    "CreateStageGraphSchema",
    "GetStageGraphSchema",
    "ListStageGraphsSchema",
    "StageGraphStageItem",
    "StageGraphStageResponse",
    "StageGraphIdRequest",
    "StageGraphListResponse",
    "StageGraphResponse",
    "UpdateStageGraphStagesRequest",
    "UpdateStageGraphStagesSchema",
]

