"""Network and Performance TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.cameras.models import (
    BoolResponse,
    CameraPerformanceSettingsRequest,
    CameraPerformanceSettingsResponse,
    NetworkDiagnosticsResponse,
)

# Network Diagnostics Schemas
GetNetworkDiagnosticsSchema = TaskSchema(
    name="get_network_diagnostics", input_schema=None, output_schema=NetworkDiagnosticsResponse
)

# Camera Performance Schemas
# GET endpoint accepts optional camera parameter to retrieve per-camera GigE settings
GetPerformanceSettingsSchema = TaskSchema(
    name="get_performance_settings",
    input_schema=CameraPerformanceSettingsRequest,
    output_schema=CameraPerformanceSettingsResponse,
)

SetPerformanceSettingsSchema = TaskSchema(
    name="set_performance_settings", input_schema=CameraPerformanceSettingsRequest, output_schema=BoolResponse
)

__all__ = [
    "GetNetworkDiagnosticsSchema",
    "GetPerformanceSettingsSchema",
    "SetPerformanceSettingsSchema",
]
