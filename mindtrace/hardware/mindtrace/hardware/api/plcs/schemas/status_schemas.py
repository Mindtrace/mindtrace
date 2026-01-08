"""Status & Information TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.plcs.models import (
    PLCInfoResponse,
    PLCQueryRequest,
    PLCStatusResponse,
    SystemDiagnosticsResponse,
)

# Status & Information Schemas
GetPLCStatusSchema = TaskSchema(name="get_plc_status", input_schema=PLCQueryRequest, output_schema=PLCStatusResponse)

GetPLCInfoSchema = TaskSchema(name="get_plc_info", input_schema=PLCQueryRequest, output_schema=PLCInfoResponse)

GetSystemDiagnosticsSchema = TaskSchema(
    name="get_system_diagnostics", input_schema=None, output_schema=SystemDiagnosticsResponse
)

__all__ = [
    "GetPLCStatusSchema",
    "GetPLCInfoSchema",
    "GetSystemDiagnosticsSchema",
]
