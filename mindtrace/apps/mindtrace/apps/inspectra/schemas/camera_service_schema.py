"""Camera service request/response schemas and TaskSchemas."""

from typing import Optional

from pydantic import BaseModel, Field

from mindtrace.apps.inspectra.models.enums import CameraBackend, DeploymentStatus, HealthStatus
from mindtrace.core import TaskSchema


class CameraServiceResponse(BaseModel):
    id: str = Field(..., description="Camera service ID")
    line_id: str = Field(..., description="Line ID")
    cam_service_url: str = Field(..., description="Camera service URL")
    cam_service_status: DeploymentStatus = Field(..., description="Camera service deployment status")
    health_status: HealthStatus = Field(..., description="Health status")
    backend: CameraBackend = Field(..., description="Camera backend")
    line_name: Optional[str] = Field(None, description="Line name (resolved)")


class CameraServiceListResponse(BaseModel):
    items: list[CameraServiceResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class CameraServiceIdRequest(BaseModel):
    id: str = Field(..., description="Camera service ID")


class UpdateCameraServiceRequest(BaseModel):
    cam_service_status: Optional[DeploymentStatus] = Field(None, description="Camera service deployment status")
    health_status: Optional[HealthStatus] = Field(None, description="Health status")
    cam_service_url: Optional[str] = Field(None, min_length=1, description="Camera service URL")


UpdateCameraServiceSchema = TaskSchema(
    name="inspectra_update_camera_service",
    input_schema=UpdateCameraServiceRequest,
    output_schema=CameraServiceResponse,
)

ListCameraServicesSchema = TaskSchema(
    name="inspectra_list_camera_services",
    input_schema=None,
    output_schema=CameraServiceListResponse,
)

GetCameraServiceSchema = TaskSchema(
    name="inspectra_get_camera_service",
    input_schema=CameraServiceIdRequest,
    output_schema=CameraServiceResponse,
)

__all__ = [
    "CameraServiceIdRequest",
    "CameraServiceListResponse",
    "CameraServiceResponse",
    "GetCameraServiceSchema",
    "ListCameraServicesSchema",
    "UpdateCameraServiceRequest",
    "UpdateCameraServiceSchema",
]

