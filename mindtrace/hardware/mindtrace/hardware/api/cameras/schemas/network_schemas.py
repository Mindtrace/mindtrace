"""Network and Bandwidth TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.cameras.models import (
    BandwidthLimitRequest,
    BandwidthSettingsResponse,
    BoolResponse,
    CameraPerformanceSettingsRequest,
    CameraPerformanceSettingsResponse,
    NetworkDiagnosticsResponse,
)

# Network & Bandwidth Schemas
GetBandwidthSettingsSchema = TaskSchema(
    name="get_bandwidth_settings", input_schema=None, output_schema=BandwidthSettingsResponse
)

SetBandwidthLimitSchema = TaskSchema(
    name="set_bandwidth_limit", input_schema=BandwidthLimitRequest, output_schema=BoolResponse
)

GetNetworkDiagnosticsSchema = TaskSchema(
    name="get_network_diagnostics", input_schema=None, output_schema=NetworkDiagnosticsResponse
)

# Camera Performance Schemas
GetPerformanceSettingsSchema = TaskSchema(
    name="get_performance_settings", input_schema=None, output_schema=CameraPerformanceSettingsResponse
)

SetPerformanceSettingsSchema = TaskSchema(
    name="set_performance_settings", input_schema=CameraPerformanceSettingsRequest, output_schema=BoolResponse
)

__all__ = [
    "GetBandwidthSettingsSchema",
    "SetBandwidthLimitSchema",
    "GetNetworkDiagnosticsSchema",
    "GetPerformanceSettingsSchema",
    "SetPerformanceSettingsSchema",
]
