"""Scanner Information TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.services.scanners_3d.models import (
    BackendFilterRequest,
    BackendInfoResponse,
    BackendsResponse,
    ListResponse,
    ScannerInfoResponse,
    ScannerQueryRequest,
    ScannerStatusResponse,
    SystemDiagnosticsResponse,
)

# Backend & Discovery Schemas
GetScannerBackendsSchema = TaskSchema(name="get_scanner_backends", input_schema=None, output_schema=BackendsResponse)

GetScannerBackendInfoSchema = TaskSchema(
    name="get_scanner_backend_info", input_schema=None, output_schema=BackendInfoResponse
)

DiscoverScannersSchema = TaskSchema(
    name="discover_scanners", input_schema=BackendFilterRequest, output_schema=ListResponse
)

# Status & Information Schemas
GetScannerStatusSchema = TaskSchema(
    name="get_scanner_status", input_schema=ScannerQueryRequest, output_schema=ScannerStatusResponse
)

GetScannerInfoSchema = TaskSchema(
    name="get_scanner_info", input_schema=ScannerQueryRequest, output_schema=ScannerInfoResponse
)

GetSystemDiagnosticsSchema = TaskSchema(
    name="get_system_diagnostics", input_schema=None, output_schema=SystemDiagnosticsResponse
)

__all__ = [
    "GetScannerBackendsSchema",
    "GetScannerBackendInfoSchema",
    "DiscoverScannersSchema",
    "GetScannerStatusSchema",
    "GetScannerInfoSchema",
    "GetSystemDiagnosticsSchema",
]
