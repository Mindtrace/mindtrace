"""Network and Bandwidth TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.cameras.models import (
    BandwidthLimitRequest,
    BandwidthSettingsResponse,
    BoolResponse,
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

__all__ = [
    "GetBandwidthSettingsSchema",
    "SetBandwidthLimitSchema",
    "GetNetworkDiagnosticsSchema",
]
