"""Schemas for camera position endpoints."""

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema


class CameraPositionResponse(BaseModel):
    id: str
    camera_id: str
    position: int


class CameraPositionListResponse(BaseModel):
    items: list[CameraPositionResponse]
    total: int


class UpsertCameraPositionRequest(BaseModel):
    camera_id: str = Field(..., description="Camera ID")
    position: int = Field(0, ge=0, description="Position number (unique per camera)")

ListCameraPositionsSchema = TaskSchema(
    name="inspectra_list_camera_positions",
    input_schema=None,
    output_schema=CameraPositionListResponse,
)

GetCameraPositionSchema = TaskSchema(
    name="inspectra_get_camera_position",
    input_schema=None,
    output_schema=CameraPositionResponse,
)

UpsertCameraPositionSchema = TaskSchema(
    name="inspectra_upsert_camera_position",
    input_schema=UpsertCameraPositionRequest,
    output_schema=CameraPositionResponse,
)

