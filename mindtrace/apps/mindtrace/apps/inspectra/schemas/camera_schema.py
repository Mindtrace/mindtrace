"""Camera request/response schemas and TaskSchemas."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from mindtrace.core import TaskSchema


class CameraConfigResponse(BaseModel):
    exposure_ms: Optional[int] = Field(None, description="Exposure in milliseconds (stored preference)")
    white_balance: Optional[str] = Field(None, description="White balance mode (e.g. off, once)")


class CameraResponse(BaseModel):
    id: str = Field(..., description="Camera ID")
    name: str = Field(..., description="Camera name (unique identifier)")
    line_id: str = Field(..., description="Line ID")
    line_name: Optional[str] = Field(None, description="Line name (resolved)")
    camera_service_id: str = Field(..., description="Camera service ID")
    camera_service_url: str = Field(..., description="Camera service URL")
    camera_set_id: Optional[str] = Field(None, description="Camera set ID")
    camera_position_ids: list[str] = Field(default_factory=list, description="Camera position IDs")
    config: CameraConfigResponse = Field(
        default_factory=CameraConfigResponse,
        description="Persisted camera configuration",
    )


class CameraListResponse(BaseModel):
    items: list[CameraResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class ListCamerasSchemaRequest(BaseModel):
    camera_service_id: Optional[str] = Field(None, description="Filter by camera service ID")
    skip: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=500)


class CameraIdRequest(BaseModel):
    id: str = Field(..., description="Camera ID")


class UpdateCameraConfigRequest(BaseModel):
    exposure_ms: Optional[int] = Field(None, description="Exposure in milliseconds")
    white_balance: Optional[Literal["off", "once"]] = Field(None, description="White balance mode")

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.exposure_ms is None and self.white_balance is None:
            raise ValueError("At least one of exposure_ms or white_balance must be provided")
        return self


ListCamerasSchema = TaskSchema(
    name="inspectra_list_cameras",
    input_schema=None,
    output_schema=CameraListResponse,
)

GetCameraSchema = TaskSchema(
    name="inspectra_get_camera",
    input_schema=CameraIdRequest,
    output_schema=CameraResponse,
)

UpdateCameraConfigSchema = TaskSchema(
    name="inspectra_update_camera_config",
    input_schema=UpdateCameraConfigRequest,
    output_schema=CameraResponse,
)

__all__ = [
    "CameraConfigResponse",
    "CameraIdRequest",
    "CameraListResponse",
    "CameraResponse",
    "GetCameraSchema",
    "ListCamerasSchema",
    "UpdateCameraConfigRequest",
    "UpdateCameraConfigSchema",
]

