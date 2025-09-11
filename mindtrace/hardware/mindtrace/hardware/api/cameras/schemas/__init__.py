"""TaskSchemas for CameraManagerService endpoints."""

from mindtrace.core import TaskSchema

from ..models import (
    ActiveCamerasResponse,
    # Requests
    BackendFilterRequest,
    BackendInfoResponse,
    # Responses
    BackendsResponse,
    BandwidthLimitRequest,
    BandwidthSettingsResponse,
    BatchCaptureResponse,
    BatchHDRCaptureResponse,
    BatchOperationResponse,
    BoolResponse,
    CameraCapabilitiesResponse,
    CameraCloseBatchRequest,
    CameraCloseRequest,
    CameraConfigurationResponse,
    CameraConfigureBatchRequest,
    CameraConfigureRequest,
    CameraInfoResponse,
    CameraOpenBatchRequest,
    CameraOpenRequest,
    CameraQueryRequest,
    CameraStatusResponse,
    CaptureBatchRequest,
    CaptureHDRBatchRequest,
    CaptureHDRRequest,
    CaptureImageRequest,
    CaptureResponse,
    ConfigFileExportRequest,
    ConfigFileImportRequest,
    ConfigFileResponse,
    HDRCaptureResponse,
    ListResponse,
    NetworkDiagnosticsResponse,
    SystemDiagnosticsResponse,
)

# Backend & Discovery Schemas
DiscoverBackendsSchema = TaskSchema(
    name="discover_backends",
    input_schema=None,
    output_schema=BackendsResponse
)

GetBackendInfoSchema = TaskSchema(
    name="get_backend_info", 
    input_schema=None,
    output_schema=BackendInfoResponse
)

DiscoverCamerasSchema = TaskSchema(
    name="discover_cameras",
    input_schema=BackendFilterRequest,
    output_schema=ListResponse
)

# Camera Lifecycle Schemas
OpenCameraSchema = TaskSchema(
    name="open_camera",
    input_schema=CameraOpenRequest,
    output_schema=BoolResponse
)

OpenCamerasBatchSchema = TaskSchema(
    name="open_cameras_batch",
    input_schema=CameraOpenBatchRequest,
    output_schema=BatchOperationResponse
)

CloseCameraSchema = TaskSchema(
    name="close_camera",
    input_schema=CameraCloseRequest,
    output_schema=BoolResponse
)

CloseCamerasBatchSchema = TaskSchema(
    name="close_cameras_batch",
    input_schema=CameraCloseBatchRequest,
    output_schema=BatchOperationResponse
)

CloseAllCamerasSchema = TaskSchema(
    name="close_all_cameras",
    input_schema=None,
    output_schema=BoolResponse
)

GetActiveCamerasSchema = TaskSchema(
    name="get_active_cameras",
    input_schema=None,
    output_schema=ActiveCamerasResponse
)

# Camera Status & Information Schemas
GetCameraStatusSchema = TaskSchema(
    name="get_camera_status",
    input_schema=CameraQueryRequest,
    output_schema=CameraStatusResponse
)

GetCameraInfoSchema = TaskSchema(
    name="get_camera_info",
    input_schema=CameraQueryRequest,
    output_schema=CameraInfoResponse
)

GetCameraCapabilitiesSchema = TaskSchema(
    name="get_camera_capabilities",
    input_schema=CameraQueryRequest,
    output_schema=CameraCapabilitiesResponse
)

GetSystemDiagnosticsSchema = TaskSchema(
    name="get_system_diagnostics",
    input_schema=None,
    output_schema=SystemDiagnosticsResponse
)

# Camera Configuration Schemas
ConfigureCameraSchema = TaskSchema(
    name="configure_camera",
    input_schema=CameraConfigureRequest,
    output_schema=BoolResponse
)

ConfigureCamerasBatchSchema = TaskSchema(
    name="configure_cameras_batch",
    input_schema=CameraConfigureBatchRequest,
    output_schema=BatchOperationResponse
)

GetCameraConfigurationSchema = TaskSchema(
    name="get_camera_configuration",
    input_schema=CameraQueryRequest,
    output_schema=CameraConfigurationResponse
)

ImportCameraConfigSchema = TaskSchema(
    name="import_camera_config",
    input_schema=ConfigFileImportRequest,
    output_schema=ConfigFileResponse
)

ExportCameraConfigSchema = TaskSchema(
    name="export_camera_config",
    input_schema=ConfigFileExportRequest,
    output_schema=ConfigFileResponse
)

# Image Capture Schemas
CaptureImageSchema = TaskSchema(
    name="capture_image",
    input_schema=CaptureImageRequest,
    output_schema=CaptureResponse
)

CaptureImagesBatchSchema = TaskSchema(
    name="capture_images_batch",
    input_schema=CaptureBatchRequest,
    output_schema=BatchCaptureResponse
)

CaptureHDRImageSchema = TaskSchema(
    name="capture_hdr_image",
    input_schema=CaptureHDRRequest,
    output_schema=HDRCaptureResponse
)

CaptureHDRImagesBatchSchema = TaskSchema(
    name="capture_hdr_images_batch",
    input_schema=CaptureHDRBatchRequest,
    output_schema=BatchHDRCaptureResponse
)

# Network & Bandwidth Schemas
GetBandwidthSettingsSchema = TaskSchema(
    name="get_bandwidth_settings",
    input_schema=None,
    output_schema=BandwidthSettingsResponse
)

SetBandwidthLimitSchema = TaskSchema(
    name="set_bandwidth_limit",
    input_schema=BandwidthLimitRequest,
    output_schema=BoolResponse
)

GetNetworkDiagnosticsSchema = TaskSchema(
    name="get_network_diagnostics",
    input_schema=None,
    output_schema=NetworkDiagnosticsResponse
)

# All schemas for easy import
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
    "DiscoverBackendsSchema",
    "GetBackendInfoSchema", 
    "DiscoverCamerasSchema",
    "OpenCameraSchema",
    "OpenCamerasBatchSchema",
    "CloseCameraSchema",
    "CloseCamerasBatchSchema",
    "CloseAllCamerasSchema",
    "GetActiveCamerasSchema",
    "GetCameraStatusSchema",
    "GetCameraInfoSchema",
    "GetCameraCapabilitiesSchema",
    "GetSystemDiagnosticsSchema",
    "ConfigureCameraSchema",
    "ConfigureCamerasBatchSchema",
    "GetCameraConfigurationSchema",
    "ImportCameraConfigSchema",
    "ExportCameraConfigSchema",
    "CaptureImageSchema",
    "CaptureImagesBatchSchema",
    "CaptureHDRImageSchema",
    "CaptureHDRImagesBatchSchema",
    "GetBandwidthSettingsSchema",
    "SetBandwidthLimitSchema",
    "GetNetworkDiagnosticsSchema",
    "ALL_SCHEMAS",
]