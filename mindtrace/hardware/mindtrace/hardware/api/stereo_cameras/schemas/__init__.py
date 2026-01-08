"""MCP TaskSchemas for StereoCameraService."""

from mindtrace.hardware.api.stereo_cameras.schemas.capture_schemas import (
    CapturePointCloudBatchSchema,
    CapturePointCloudSchema,
    CaptureStereoPairBatchSchema,
    CaptureStereoPairSchema,
)
from mindtrace.hardware.api.stereo_cameras.schemas.config_schemas import (
    ConfigureStereoCamerasBatchSchema,
    ConfigureStereoCameraSchema,
    GetStereoCameraConfigurationSchema,
)
from mindtrace.hardware.api.stereo_cameras.schemas.info_schemas import (
    DiscoverStereoCamerasSchema,
    GetStereoCameraBackendInfoSchema,
    GetStereoCameraBackendsSchema,
    GetStereoCameraInfoSchema,
    GetStereoCameraStatusSchema,
    GetSystemDiagnosticsSchema,
)
from mindtrace.hardware.api.stereo_cameras.schemas.lifecycle_schemas import (
    CloseAllStereoCamerasSchema,
    CloseStereoCamerasBatchSchema,
    CloseStereoCameraSchema,
    GetActiveStereoCamerasSchema,
    OpenStereoCamerasBatchSchema,
    OpenStereoCameraSchema,
)

# Collect all schemas for service registration
ALL_SCHEMAS = [
    # Backend & Discovery
    GetStereoCameraBackendsSchema,
    GetStereoCameraBackendInfoSchema,
    DiscoverStereoCamerasSchema,
    # Lifecycle
    OpenStereoCameraSchema,
    OpenStereoCamerasBatchSchema,
    CloseStereoCameraSchema,
    CloseStereoCamerasBatchSchema,
    CloseAllStereoCamerasSchema,
    GetActiveStereoCamerasSchema,
    # Status & Information
    GetStereoCameraStatusSchema,
    GetStereoCameraInfoSchema,
    GetSystemDiagnosticsSchema,
    # Configuration
    ConfigureStereoCameraSchema,
    ConfigureStereoCamerasBatchSchema,
    GetStereoCameraConfigurationSchema,
    # Capture
    CaptureStereoPairSchema,
    CaptureStereoPairBatchSchema,
    CapturePointCloudSchema,
    CapturePointCloudBatchSchema,
]

__all__ = [
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
