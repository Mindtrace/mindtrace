"""MCP TaskSchemas for StereoCameraService."""

from mindtrace.hardware.services.stereo_cameras.schemas.capture_schemas import (
    CapturePointCloudBatchSchema,
    CapturePointCloudSchema,
    CaptureStereoPairBatchSchema,
    CaptureStereoPairSchema,
)
from mindtrace.hardware.services.stereo_cameras.schemas.config_schemas import (
    ConfigureStereoCamerasBatchSchema,
    ConfigureStereoCameraSchema,
    GetStereoCameraConfigurationSchema,
)
from mindtrace.hardware.services.stereo_cameras.schemas.health_schemas import (
    HealthSchema,
)
from mindtrace.hardware.services.stereo_cameras.schemas.info_schemas import (
    DiscoverStereoCamerasSchema,
    GetStereoCameraBackendInfoSchema,
    GetStereoCameraBackendsSchema,
    GetStereoCameraInfoSchema,
    GetStereoCameraStatusSchema,
    GetSystemDiagnosticsSchema,
)
from mindtrace.hardware.services.stereo_cameras.schemas.lifecycle_schemas import (
    CloseAllStereoCamerasSchema,
    CloseStereoCamerasBatchSchema,
    CloseStereoCameraSchema,
    GetActiveStereoCamerasSchema,
    OpenStereoCamerasBatchSchema,
    OpenStereoCameraSchema,
)

# All schemas for easy import - dict format for add_endpoint() compatibility
ALL_SCHEMAS = {
    # Health
    "health": HealthSchema,
    # Backend & Discovery
    "get_backends": GetStereoCameraBackendsSchema,
    "get_backend_info": GetStereoCameraBackendInfoSchema,
    "discover_cameras": DiscoverStereoCamerasSchema,
    # Lifecycle
    "open_camera": OpenStereoCameraSchema,
    "open_cameras_batch": OpenStereoCamerasBatchSchema,
    "close_camera": CloseStereoCameraSchema,
    "close_cameras_batch": CloseStereoCamerasBatchSchema,
    "close_all_cameras": CloseAllStereoCamerasSchema,
    "get_active_cameras": GetActiveStereoCamerasSchema,
    # Status & Information
    "get_camera_status": GetStereoCameraStatusSchema,
    "get_camera_info": GetStereoCameraInfoSchema,
    "get_system_diagnostics": GetSystemDiagnosticsSchema,
    # Configuration
    "configure_camera": ConfigureStereoCameraSchema,
    "configure_cameras_batch": ConfigureStereoCamerasBatchSchema,
    "get_camera_configuration": GetStereoCameraConfigurationSchema,
    # Capture
    "capture_stereo": CaptureStereoPairSchema,
    "capture_stereo_batch": CaptureStereoPairBatchSchema,
    "capture_pointcloud": CapturePointCloudSchema,
    "capture_pointcloud_batch": CapturePointCloudBatchSchema,
}

__all__ = [
    # Health
    "HealthSchema",
    # Individual schemas
    "GetStereoCameraBackendsSchema",
    "GetStereoCameraBackendInfoSchema",
    "DiscoverStereoCamerasSchema",
    "OpenStereoCameraSchema",
    "OpenStereoCamerasBatchSchema",
    "CloseStereoCameraSchema",
    "CloseStereoCamerasBatchSchema",
    "CloseAllStereoCamerasSchema",
    "GetActiveStereoCamerasSchema",
    "GetStereoCameraStatusSchema",
    "GetStereoCameraInfoSchema",
    "GetSystemDiagnosticsSchema",
    "ConfigureStereoCameraSchema",
    "ConfigureStereoCamerasBatchSchema",
    "GetStereoCameraConfigurationSchema",
    "CaptureStereoPairSchema",
    "CaptureStereoPairBatchSchema",
    "CapturePointCloudSchema",
    "CapturePointCloudBatchSchema",
    # Collection
    "ALL_SCHEMAS",
]
