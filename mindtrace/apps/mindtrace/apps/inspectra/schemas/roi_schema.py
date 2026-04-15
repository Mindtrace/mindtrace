"""Schemas for ROI endpoints."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from mindtrace.apps.inspectra.models.enums import RoiType
from mindtrace.core import TaskSchema


class RoiResponse(BaseModel):
    id: str
    line_id: str
    name: str
    camera_id: str
    camera_position_id: str
    camera_set_id: str
    stage_id: str
    model_deployment_id: str
    type: RoiType
    points: List[List[float]]
    holes: List[List[List[float]]] = Field(default_factory=list)
    active: bool = True
    meta: Dict[str, Any] = Field(default_factory=dict)


class RoiListResponse(BaseModel):
    items: list[RoiResponse]
    total: int


class CreateRoiRequest(BaseModel):
    camera_id: str
    camera_position_id: str
    stage_id: str
    model_deployment_id: str
    name: Optional[str] = None
    type: RoiType = RoiType.BOX
    # Box ROIs require 4 points; polygon ROIs require >=3. Validated in the route handler.
    points: List[List[float]] = Field(..., min_length=3, description="ROI points")

ListRoisSchema = TaskSchema(
    name="inspectra_list_rois",
    input_schema=None,
    output_schema=RoiListResponse,
)

CreateRoiSchema = TaskSchema(
    name="inspectra_create_roi",
    input_schema=CreateRoiRequest,
    output_schema=RoiResponse,
)

GetRoiSchema = TaskSchema(
    name="inspectra_get_roi",
    input_schema=None,
    output_schema=RoiResponse,
)

DeleteRoiSchema = TaskSchema(
    name="inspectra_delete_roi",
    input_schema=None,
    output_schema=None,
)

