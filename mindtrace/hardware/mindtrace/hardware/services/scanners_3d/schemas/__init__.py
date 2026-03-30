"""MCP TaskSchemas for Scanner3DService."""

from mindtrace.hardware.services.scanners_3d.schemas.capture_schemas import (
    CapturePointCloudBatchSchema,
    CapturePointCloudSchema,
    CaptureScanBatchSchema,
    CaptureScanSchema,
)
from mindtrace.hardware.services.scanners_3d.schemas.config_schemas import (
    ConfigureScannersBatchSchema,
    ConfigureScannerSchema,
    GetScannerCapabilitiesSchema,
    GetScannerConfigurationSchema,
)
from mindtrace.hardware.services.scanners_3d.schemas.health_schemas import (
    HealthSchema,
)
from mindtrace.hardware.services.scanners_3d.schemas.info_schemas import (
    DiscoverScannersSchema,
    GetScannerBackendInfoSchema,
    GetScannerBackendsSchema,
    GetScannerInfoSchema,
    GetScannerStatusSchema,
    GetSystemDiagnosticsSchema,
)
from mindtrace.hardware.services.scanners_3d.schemas.lifecycle_schemas import (
    CloseAllScannersSchema,
    CloseScannersBatchSchema,
    CloseScannerSchema,
    GetActiveScannersSchema,
    OpenScannersBatchSchema,
    OpenScannerSchema,
)

# All schemas for easy import - dict format for add_endpoint() compatibility
ALL_SCHEMAS = {
    # Health
    "health": HealthSchema,
    # Backend & Discovery
    "get_backends": GetScannerBackendsSchema,
    "get_backend_info": GetScannerBackendInfoSchema,
    "discover_scanners": DiscoverScannersSchema,
    # Lifecycle
    "open_scanner": OpenScannerSchema,
    "open_scanners_batch": OpenScannersBatchSchema,
    "close_scanner": CloseScannerSchema,
    "close_scanners_batch": CloseScannersBatchSchema,
    "close_all_scanners": CloseAllScannersSchema,
    "get_active_scanners": GetActiveScannersSchema,
    # Status & Information
    "get_scanner_status": GetScannerStatusSchema,
    "get_scanner_info": GetScannerInfoSchema,
    "get_system_diagnostics": GetSystemDiagnosticsSchema,
    # Configuration
    "get_scanner_capabilities": GetScannerCapabilitiesSchema,
    "configure_scanner": ConfigureScannerSchema,
    "configure_scanners_batch": ConfigureScannersBatchSchema,
    "get_scanner_configuration": GetScannerConfigurationSchema,
    # Capture
    "capture_scan": CaptureScanSchema,
    "capture_scan_batch": CaptureScanBatchSchema,
    "capture_pointcloud": CapturePointCloudSchema,
    "capture_pointcloud_batch": CapturePointCloudBatchSchema,
}

__all__ = [
    # Health
    "HealthSchema",
    # Individual schemas
    "GetScannerBackendsSchema",
    "GetScannerBackendInfoSchema",
    "DiscoverScannersSchema",
    "OpenScannerSchema",
    "OpenScannersBatchSchema",
    "CloseScannerSchema",
    "CloseScannersBatchSchema",
    "CloseAllScannersSchema",
    "GetActiveScannersSchema",
    "GetScannerStatusSchema",
    "GetScannerInfoSchema",
    "GetSystemDiagnosticsSchema",
    "GetScannerCapabilitiesSchema",
    "ConfigureScannerSchema",
    "ConfigureScannersBatchSchema",
    "GetScannerConfigurationSchema",
    "CaptureScanSchema",
    "CaptureScanBatchSchema",
    "CapturePointCloudSchema",
    "CapturePointCloudBatchSchema",
    # Collection
    "ALL_SCHEMAS",
]
