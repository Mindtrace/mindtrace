"""PLC Lifecycle TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.plcs.models import (
    ActivePLCsResponse,
    BatchOperationResponse,
    BoolResponse,
    PLCConnectBatchRequest,
    PLCConnectRequest,
    PLCDisconnectBatchRequest,
    PLCDisconnectRequest,
)

# PLC Lifecycle Schemas
ConnectPLCSchema = TaskSchema(name="connect_plc", input_schema=PLCConnectRequest, output_schema=BoolResponse)

ConnectPLCsBatchSchema = TaskSchema(
    name="connect_plcs_batch", input_schema=PLCConnectBatchRequest, output_schema=BatchOperationResponse
)

DisconnectPLCSchema = TaskSchema(name="disconnect_plc", input_schema=PLCDisconnectRequest, output_schema=BoolResponse)

DisconnectPLCsBatchSchema = TaskSchema(
    name="disconnect_plcs_batch", input_schema=PLCDisconnectBatchRequest, output_schema=BatchOperationResponse
)

DisconnectAllPLCsSchema = TaskSchema(name="disconnect_all_plcs", input_schema=None, output_schema=BoolResponse)

GetActivePLCsSchema = TaskSchema(name="get_active_plcs", input_schema=None, output_schema=ActivePLCsResponse)

__all__ = [
    "ConnectPLCSchema",
    "ConnectPLCsBatchSchema",
    "DisconnectPLCSchema",
    "DisconnectPLCsBatchSchema",
    "DisconnectAllPLCsSchema",
    "GetActivePLCsSchema",
]
