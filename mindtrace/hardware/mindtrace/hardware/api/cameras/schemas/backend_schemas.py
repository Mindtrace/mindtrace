"""Backend and Discovery TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.cameras.models import (
    BackendFilterRequest,
    BackendInfoResponse,
    BackendsResponse,
    ListResponse,
)

# Backend & Discovery Schemas
DiscoverBackendsSchema = TaskSchema(name="discover_backends", input_schema=None, output_schema=BackendsResponse)

GetBackendInfoSchema = TaskSchema(name="get_backend_info", input_schema=None, output_schema=BackendInfoResponse)

DiscoverCamerasSchema = TaskSchema(
    name="discover_cameras", input_schema=BackendFilterRequest, output_schema=ListResponse
)

__all__ = [
    "DiscoverBackendsSchema",
    "GetBackendInfoSchema",
    "DiscoverCamerasSchema",
]
