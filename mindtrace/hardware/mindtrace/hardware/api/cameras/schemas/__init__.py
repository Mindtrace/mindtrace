"""TaskSchemas for CameraManagerService endpoints."""

# Import all schemas from domain-specific modules
from mindtrace.hardware.api.cameras.schemas.backend_schemas import (
    DiscoverBackendsSchema,
    DiscoverCamerasSchema,
    GetBackendInfoSchema,
)
from mindtrace.hardware.api.cameras.schemas.capture_schemas import (
    CaptureHDRImagesBatchSchema,
    CaptureHDRImageSchema,
    CaptureImagesBatchSchema,
    CaptureImageSchema,
)
from mindtrace.hardware.api.cameras.schemas.config_schemas import (
    ConfigureCamerasBatchSchema,
    ConfigureCameraSchema,
    ExportCameraConfigSchema,
    GetCameraConfigurationSchema,
    ImportCameraConfigSchema,
)
from mindtrace.hardware.api.cameras.schemas.info_schemas import (
    GetCameraCapabilitiesSchema,
    GetCameraInfoSchema,
    GetCameraStatusSchema,
    GetSystemDiagnosticsSchema,
)
from mindtrace.hardware.api.cameras.schemas.lifecycle_schemas import (
    CloseAllCamerasSchema,
    CloseCamerasBatchSchema,
    CloseCameraSchema,
    GetActiveCamerasSchema,
    OpenCamerasBatchSchema,
    OpenCameraSchema,
)
from mindtrace.hardware.api.cameras.schemas.network_schemas import (
    GetBandwidthSettingsSchema,
    GetNetworkDiagnosticsSchema,
    SetBandwidthLimitSchema,
)

# All schemas for easy import - maintains backward compatibility
ALL_SCHEMAS = {
    # Backend & Discovery
    "discover_backends": DiscoverBackendsSchema,
    "get_backend_info": GetBackendInfoSchema,
    "discover_cameras": DiscoverCamerasSchema,
    # Camera Lifecycle
    "open_camera": OpenCameraSchema,
    "open_cameras_batch": OpenCamerasBatchSchema,
    "close_camera": CloseCameraSchema,
    "close_cameras_batch": CloseCamerasBatchSchema,
    "close_all_cameras": CloseAllCamerasSchema,
    "get_active_cameras": GetActiveCamerasSchema,
    # Camera Status & Information
    "get_camera_status": GetCameraStatusSchema,
    "get_camera_info": GetCameraInfoSchema,
    "get_camera_capabilities": GetCameraCapabilitiesSchema,
    "get_system_diagnostics": GetSystemDiagnosticsSchema,
    # Camera Configuration
    "configure_camera": ConfigureCameraSchema,
    "configure_cameras_batch": ConfigureCamerasBatchSchema,
    "get_camera_configuration": GetCameraConfigurationSchema,
    "import_camera_config": ImportCameraConfigSchema,
    "export_camera_config": ExportCameraConfigSchema,
    # Image Capture
    "capture_image": CaptureImageSchema,
    "capture_images_batch": CaptureImagesBatchSchema,
    "capture_hdr_image": CaptureHDRImageSchema,
    "capture_hdr_images_batch": CaptureHDRImagesBatchSchema,
    # Network & Bandwidth
    "get_bandwidth_settings": GetBandwidthSettingsSchema,
    "set_bandwidth_limit": SetBandwidthLimitSchema,
    "get_network_diagnostics": GetNetworkDiagnosticsSchema,
}

__all__ = [
    # Backend & Discovery
    "DiscoverBackendsSchema",
    "GetBackendInfoSchema",
    "DiscoverCamerasSchema",
    # Camera Lifecycle
    "OpenCameraSchema",
    "OpenCamerasBatchSchema",
    "CloseCameraSchema",
    "CloseCamerasBatchSchema",
    "CloseAllCamerasSchema",
    "GetActiveCamerasSchema",
    # Camera Status & Information
    "GetCameraStatusSchema",
    "GetCameraInfoSchema",
    "GetCameraCapabilitiesSchema",
    "GetSystemDiagnosticsSchema",
    # Camera Configuration
    "ConfigureCameraSchema",
    "ConfigureCamerasBatchSchema",
    "GetCameraConfigurationSchema",
    "ImportCameraConfigSchema",
    "ExportCameraConfigSchema",
    # Image Capture
    "CaptureImageSchema",
    "CaptureImagesBatchSchema",
    "CaptureHDRImageSchema",
    "CaptureHDRImagesBatchSchema",
    # Network & Bandwidth
    "GetBandwidthSettingsSchema",
    "SetBandwidthLimitSchema",
    "GetNetworkDiagnosticsSchema",
    # All schemas dictionary
    "ALL_SCHEMAS",
]
