"""Camera Status and Information TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.cameras.models import (
    CameraCapabilitiesResponse,
    CameraInfoResponse,
    CameraQueryRequest,
    CameraStatusResponse,
    SystemDiagnosticsResponse,
)

# Camera Status & Information Schemas
GetCameraStatusSchema = TaskSchema(
    name="get_camera_status", input_schema=CameraQueryRequest, output_schema=CameraStatusResponse
)

GetCameraInfoSchema = TaskSchema(
    name="get_camera_info", input_schema=CameraQueryRequest, output_schema=CameraInfoResponse
)

GetCameraCapabilitiesSchema = TaskSchema(
    name="get_camera_capabilities", input_schema=CameraQueryRequest, output_schema=CameraCapabilitiesResponse
)

GetSystemDiagnosticsSchema = TaskSchema(
    name="get_system_diagnostics", input_schema=None, output_schema=SystemDiagnosticsResponse
)

__all__ = [
    "GetCameraStatusSchema",
    "GetCameraInfoSchema",
    "GetCameraCapabilitiesSchema",
    "GetSystemDiagnosticsSchema",
]
