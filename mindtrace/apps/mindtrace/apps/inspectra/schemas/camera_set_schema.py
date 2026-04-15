"""Camera set request/response schemas and TaskSchemas."""

from typing import Optional

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema


class CameraSetResponse(BaseModel):
    id: str = Field(..., description="Camera set ID")
    name: str = Field(..., description="Camera set name")
    line_id: str = Field(..., description="Line ID")
    line_name: Optional[str] = Field(None, description="Line name (resolved)")
    camera_service_id: str = Field(..., description="Camera service ID")
    camera_service_url: str = Field(..., description="Camera service URL")
    cameras: list[str] = Field(default_factory=list, description="Camera names in this set")
    batch_size: int = Field(1, ge=1)


class CameraSetListResponse(BaseModel):
    items: list[CameraSetResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class CreateCameraSetRequest(BaseModel):
    camera_service_id: str = Field(..., description="Camera service ID")
    name: str = Field(..., min_length=1, description="Camera set name")
    cameras: list[str] = Field(default_factory=list, description="Camera names")
    batch_size: int = Field(1, ge=1)


class UpdateCameraSetRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, description="Camera set name")
    cameras: Optional[list[str]] = Field(None, description="Camera names")
    batch_size: Optional[int] = Field(None, ge=1)


CameraSetIdRequest = BaseModel

CreateCameraSetSchema = TaskSchema(
    name="inspectra_create_camera_set",
    input_schema=CreateCameraSetRequest,
    output_schema=CameraSetResponse,
)
UpdateCameraSetSchema = TaskSchema(
    name="inspectra_update_camera_set",
    input_schema=UpdateCameraSetRequest,
    output_schema=CameraSetResponse,
)
ListCameraSetsSchema = TaskSchema(
    name="inspectra_list_camera_sets",
    input_schema=None,
    output_schema=CameraSetListResponse,
)

__all__ = [
    "CameraSetListResponse",
    "CameraSetResponse",
    "CreateCameraSetRequest",
    "UpdateCameraSetRequest",
    "CreateCameraSetSchema",
    "UpdateCameraSetSchema",
    "ListCameraSetsSchema",
]

