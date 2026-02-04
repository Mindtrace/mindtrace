"""TaskSchemas for PLCManagerService endpoints."""

# Import all schemas from domain-specific modules
from mindtrace.hardware.api.plcs.schemas.backend_schemas import (
    DiscoverBackendsSchema,
    DiscoverPLCsSchema,
    GetBackendInfoSchema,
)
from mindtrace.hardware.api.plcs.schemas.lifecycle_schemas import (
    ConnectPLCsBatchSchema,
    ConnectPLCSchema,
    DisconnectAllPLCsSchema,
    DisconnectPLCsBatchSchema,
    DisconnectPLCSchema,
    GetActivePLCsSchema,
)
from mindtrace.hardware.api.plcs.schemas.status_schemas import (
    GetPLCInfoSchema,
    GetPLCStatusSchema,
    GetSystemDiagnosticsSchema,
)
from mindtrace.hardware.api.plcs.schemas.tag_schemas import (
    TagBatchReadSchema,
    TagBatchWriteSchema,
    TagInfoSchema,
    TagListSchema,
    TagReadSchema,
    TagWriteSchema,
)

# All schemas for easy import - maintains backward compatibility
ALL_SCHEMAS = {
    # Backend & Discovery
    "discover_backends": DiscoverBackendsSchema,
    "get_backend_info": GetBackendInfoSchema,
    "discover_plcs": DiscoverPLCsSchema,
    # PLC Lifecycle
    "connect_plc": ConnectPLCSchema,
    "connect_plcs_batch": ConnectPLCsBatchSchema,
    "disconnect_plc": DisconnectPLCSchema,
    "disconnect_plcs_batch": DisconnectPLCsBatchSchema,
    "disconnect_all_plcs": DisconnectAllPLCsSchema,
    "get_active_plcs": GetActivePLCsSchema,
    # Tag Operations
    "tag_read": TagReadSchema,
    "tag_write": TagWriteSchema,
    "tag_batch_read": TagBatchReadSchema,
    "tag_batch_write": TagBatchWriteSchema,
    "tag_list": TagListSchema,
    "tag_info": TagInfoSchema,
    # Status & Information
    "get_plc_status": GetPLCStatusSchema,
    "get_plc_info": GetPLCInfoSchema,
    "get_system_diagnostics": GetSystemDiagnosticsSchema,
}

__all__ = [
    # Backend & Discovery
    "DiscoverBackendsSchema",
    "GetBackendInfoSchema",
    "DiscoverPLCsSchema",
    # PLC Lifecycle
    "ConnectPLCSchema",
    "ConnectPLCsBatchSchema",
    "DisconnectPLCSchema",
    "DisconnectPLCsBatchSchema",
    "DisconnectAllPLCsSchema",
    "GetActivePLCsSchema",
    # Tag Operations
    "TagReadSchema",
    "TagWriteSchema",
    "TagBatchReadSchema",
    "TagBatchWriteSchema",
    "TagListSchema",
    "TagInfoSchema",
    # Status & Information
    "GetPLCStatusSchema",
    "GetPLCInfoSchema",
    "GetSystemDiagnosticsSchema",
    # All schemas dictionary
    "ALL_SCHEMAS",
]
