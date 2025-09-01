"""Models for CameraManagerService API."""

from .requests import (
    # Backend & Discovery
    BackendFilterRequest,
    
    # Camera Lifecycle
    CameraOpenRequest,
    CameraOpenBatchRequest,
    CameraCloseRequest,
    CameraCloseBatchRequest,
    
    # Configuration
    CameraConfigureRequest,
    CameraConfigureBatchRequest,
    CameraQueryRequest,
    ConfigFileImportRequest,
    ConfigFileExportRequest,
    
    # Image Capture
    CaptureImageRequest,
    CaptureBatchRequest,
    CaptureHDRRequest,
    CaptureHDRBatchRequest,
    
    # Network & Bandwidth
    BandwidthLimitRequest,
    
    # Specific Parameters
    ExposureRequest,
    GainRequest,
    ROIRequest,
    TriggerModeRequest,
    PixelFormatRequest,
    WhiteBalanceRequest,
    ImageEnhancementRequest,
    BandwidthLimitCameraRequest,
    PacketSizeRequest,
    InterPacketDelayRequest,
)

from .responses import (
    # Base Responses
    BaseResponse,
    BoolResponse,
    StringResponse,
    IntResponse,
    FloatResponse,
    ListResponse,
    DictResponse,
    
    # Backend & Discovery
    BackendInfo,
    BackendsResponse,
    BackendInfoResponse,
    
    # Camera Information
    CameraInfo,
    CameraStatus,
    CameraCapabilities,
    CameraConfiguration,
    CameraInfoResponse,
    CameraStatusResponse,
    CameraCapabilitiesResponse,
    CameraConfigurationResponse,
    ActiveCamerasResponse,
    
    # Capture Operations
    CaptureResult,
    CaptureResponse,
    BatchCaptureResponse,
    HDRCaptureResult,
    HDRCaptureResponse,
    BatchHDRCaptureResponse,
    
    # System & Network
    SystemDiagnostics,
    SystemDiagnosticsResponse,
    BandwidthSettings,
    BandwidthSettingsResponse,
    NetworkDiagnostics,
    NetworkDiagnosticsResponse,
    
    # Batch Operations
    BatchOperationResult,
    BatchOperationResponse,
    
    # Error Handling
    ErrorDetail,
    ErrorResponse,
    
    # Parameter Ranges
    ParameterRange,
    RangeResponse,
    
    # Configuration Files
    ConfigFileOperationResult,
    ConfigFileResponse,
)

__all__ = [
    # Requests
    "BackendFilterRequest",
    "CameraOpenRequest",
    "CameraOpenBatchRequest",
    "CameraCloseRequest",
    "CameraCloseBatchRequest",
    "CameraConfigureRequest",
    "CameraConfigureBatchRequest",
    "CameraQueryRequest",
    "ConfigFileImportRequest",
    "ConfigFileExportRequest",
    "CaptureImageRequest",
    "CaptureBatchRequest",
    "CaptureHDRRequest",
    "CaptureHDRBatchRequest",
    "BandwidthLimitRequest",
    "ExposureRequest",
    "GainRequest",
    "ROIRequest",
    "TriggerModeRequest",
    "PixelFormatRequest",
    "WhiteBalanceRequest",
    "ImageEnhancementRequest",
    "BandwidthLimitCameraRequest",
    "PacketSizeRequest",
    "InterPacketDelayRequest",
    
    # Responses
    "BaseResponse",
    "BoolResponse",
    "StringResponse",
    "IntResponse",
    "FloatResponse",
    "ListResponse",
    "DictResponse",
    "BackendInfo",
    "BackendsResponse",
    "BackendInfoResponse",
    "CameraInfo",
    "CameraStatus",
    "CameraCapabilities",
    "CameraConfiguration",
    "CameraInfoResponse",
    "CameraStatusResponse",
    "CameraCapabilitiesResponse",
    "CameraConfigurationResponse",
    "ActiveCamerasResponse",
    "CaptureResult",
    "CaptureResponse",
    "BatchCaptureResponse",
    "HDRCaptureResult",
    "HDRCaptureResponse",
    "BatchHDRCaptureResponse",
    "SystemDiagnostics",
    "SystemDiagnosticsResponse",
    "BandwidthSettings",
    "BandwidthSettingsResponse",
    "NetworkDiagnostics",
    "NetworkDiagnosticsResponse",
    "BatchOperationResult",
    "BatchOperationResponse",
    "ErrorDetail",
    "ErrorResponse",
    "ParameterRange",
    "RangeResponse",
    "ConfigFileOperationResult",
    "ConfigFileResponse",
]