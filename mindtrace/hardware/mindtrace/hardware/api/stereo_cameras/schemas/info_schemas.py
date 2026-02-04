"""Stereo Camera Information TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.stereo_cameras.models import (
    BackendFilterRequest,
    BackendInfoResponse,
    BackendsResponse,
    ListResponse,
    StereoCameraInfoResponse,
    StereoCameraQueryRequest,
    StereoCameraStatusResponse,
    SystemDiagnosticsResponse,
)

# Backend & Discovery Schemas
GetStereoCameraBackendsSchema = TaskSchema(
    name="get_stereo_camera_backends", input_schema=None, output_schema=BackendsResponse
)

GetStereoCameraBackendInfoSchema = TaskSchema(
    name="get_stereo_camera_backend_info", input_schema=None, output_schema=BackendInfoResponse
)

DiscoverStereoCamerasSchema = TaskSchema(
    name="discover_stereo_cameras", input_schema=BackendFilterRequest, output_schema=ListResponse
)

# Status & Information Schemas
GetStereoCameraStatusSchema = TaskSchema(
    name="get_stereo_camera_status", input_schema=StereoCameraQueryRequest, output_schema=StereoCameraStatusResponse
)

GetStereoCameraInfoSchema = TaskSchema(
    name="get_stereo_camera_info", input_schema=StereoCameraQueryRequest, output_schema=StereoCameraInfoResponse
)

GetSystemDiagnosticsSchema = TaskSchema(
    name="get_system_diagnostics", input_schema=None, output_schema=SystemDiagnosticsResponse
)

__all__ = [
    "GetStereoCameraBackendsSchema",
    "GetStereoCameraBackendInfoSchema",
    "DiscoverStereoCamerasSchema",
    "GetStereoCameraStatusSchema",
    "GetStereoCameraInfoSchema",
    "GetSystemDiagnosticsSchema",
]
