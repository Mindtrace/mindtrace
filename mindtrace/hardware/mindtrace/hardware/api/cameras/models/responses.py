"""
Response models for CameraManagerService.

Contains all Pydantic models for API responses, ensuring consistent
response formatting across all camera management endpoints.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class BaseResponse(BaseModel):
    """Base response model for all API endpoints."""

    success: bool
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BoolResponse(BaseResponse):
    """Response model for boolean operations."""

    data: bool


class StringResponse(BaseResponse):
    """Response model for string values."""

    data: str


class IntResponse(BaseResponse):
    """Response model for integer values."""

    data: int


class FloatResponse(BaseResponse):
    """Response model for float values."""

    data: float


class ListResponse(BaseResponse):
    """Response model for list data."""

    data: List[str]


class DictResponse(BaseResponse):
    """Response model for dictionary data."""

    data: Dict[str, Any]


# Backend & Discovery Responses
class BackendInfo(BaseModel):
    """Backend information model."""

    name: str
    available: bool
    type: str  # "hardware" or "mock"
    sdk_required: bool
    description: Optional[str] = None


class BackendsResponse(BaseResponse):
    """Response model for backend listing."""

    data: List[str]  # List of backend names


class BackendInfoResponse(BaseResponse):
    """Response model for detailed backend information."""

    data: Dict[str, BackendInfo]


# Camera Information Models
class CameraInfo(BaseModel):
    """Camera information model."""

    name: str
    backend: str
    device_name: str
    active: bool
    connected: bool
    sensor_info: Optional[Dict[str, Any]] = None


class CameraStatus(BaseModel):
    """Camera status model."""

    camera: str
    connected: bool
    initialized: bool
    backend: str
    device_name: str
    last_capture_time: Optional[datetime] = None
    error_count: int = 0


class CameraCapabilities(BaseModel):
    """Camera capabilities model."""

    exposure_range: Optional[Tuple[float, float]] = None
    gain_range: Optional[Tuple[float, float]] = None
    pixel_formats: Optional[List[str]] = None
    white_balance_modes: Optional[List[str]] = None
    trigger_modes: Optional[List[str]] = None
    width_range: Optional[Tuple[int, int]] = None
    height_range: Optional[Tuple[int, int]] = None
    bandwidth_limit_range: Optional[Tuple[float, float]] = None
    packet_size_range: Optional[Tuple[int, int]] = None
    inter_packet_delay_range: Optional[Tuple[int, int]] = None
    max_resolution: Optional[Tuple[int, int]] = None
    supports_roi: bool = False
    supports_trigger: bool = False
    supports_hdr: bool = False


class CameraConfiguration(BaseModel):
    """Camera configuration model."""

    exposure_time: Optional[float] = None
    gain: Optional[float] = None
    roi: Optional[Tuple[int, int, int, int]] = None
    trigger_mode: Optional[str] = None
    pixel_format: Optional[str] = None
    white_balance: Optional[str] = None
    image_enhancement: Optional[bool] = None
    bandwidth_limit: Optional[float] = None
    packet_size: Optional[int] = None
    inter_packet_delay: Optional[float] = None


# Response Models for Camera Operations
class CameraInfoResponse(BaseResponse):
    """Response model for camera information."""

    data: CameraInfo


class CameraStatusResponse(BaseResponse):
    """Response model for camera status."""

    data: CameraStatus


class CameraCapabilitiesResponse(BaseResponse):
    """Response model for camera capabilities."""

    data: CameraCapabilities


class CameraConfigurationResponse(BaseResponse):
    """Response model for camera configuration."""

    data: CameraConfiguration


class ActiveCamerasResponse(BaseResponse):
    """Response model for active cameras list."""

    data: List[str]


# Capture Operation Responses
class CaptureResult(BaseModel):
    """Capture result model."""

    success: bool
    error: Optional[str] = None
    image_data: Optional[str] = None  # Base64 encoded image
    image_path: Optional[str] = None
    capture_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    image_size: Optional[Tuple[int, int]] = None
    file_size_bytes: Optional[int] = None


class CaptureResponse(BaseResponse):
    """Response model for single image capture."""

    data: CaptureResult


class BatchCaptureResponse(BaseResponse):
    """Response model for batch capture operations."""

    data: Dict[str, CaptureResult]  # Maps camera names to capture results
    successful_count: int
    failed_count: int


class HDRCaptureResult(BaseModel):
    """HDR capture result model."""

    success: bool
    images: Optional[List[str]] = None  # Base64 encoded images
    image_paths: Optional[List[str]] = None
    exposure_levels: List[float]
    capture_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    successful_captures: int


class HDRCaptureResponse(BaseResponse):
    """Response model for HDR capture."""

    data: HDRCaptureResult


class BatchHDRCaptureResponse(BaseResponse):
    """Response model for batch HDR capture."""

    data: Dict[str, HDRCaptureResult]  # Maps camera names to HDR results
    successful_count: int
    failed_count: int


# System & Network Responses
class SystemDiagnostics(BaseModel):
    """System diagnostics model."""

    active_cameras: int
    max_concurrent_captures: int
    gige_cameras: int
    bandwidth_management_enabled: bool
    recommended_settings: Dict[str, int]
    backend_status: Dict[str, bool]
    memory_usage_mb: Optional[float] = None
    uptime_seconds: Optional[float] = None


class SystemDiagnosticsResponse(BaseResponse):
    """Response model for system diagnostics."""

    data: SystemDiagnostics


class BandwidthSettings(BaseModel):
    """Bandwidth settings model."""

    max_concurrent_captures: int
    current_active_captures: int
    available_slots: int
    recommended_limit: int


class BandwidthSettingsResponse(BaseResponse):
    """Response model for bandwidth settings."""

    data: BandwidthSettings


class CameraPerformanceSettings(BaseModel):
    """Camera performance and retry settings model.

    Global settings:
    - timeout_ms, retrieve_retry_count, max_concurrent_captures

    Per-camera GigE settings (None if not applicable or not queried):
    - packet_size, inter_packet_delay, bandwidth_limit_mbps
    """

    camera: Optional[str] = None  # Camera name if per-camera settings are included
    timeout_ms: int
    retrieve_retry_count: int
    max_concurrent_captures: int

    # GigE-specific performance parameters (None if not GigE camera or not queried)
    packet_size: Optional[int] = None
    inter_packet_delay: Optional[int] = None
    bandwidth_limit_mbps: Optional[float] = None


class CameraPerformanceSettingsResponse(BaseResponse):
    """Response model for camera performance settings."""

    data: CameraPerformanceSettings


class NetworkDiagnostics(BaseModel):
    """Network diagnostics model."""

    gige_cameras_count: int
    total_bandwidth_usage: float
    average_packet_size: Optional[float] = None
    network_interface: Optional[str] = None
    jumbo_frames_enabled: bool
    multicast_enabled: bool


class NetworkDiagnosticsResponse(BaseResponse):
    """Response model for network diagnostics."""

    data: NetworkDiagnostics


# Batch Operation Responses
class BatchOperationResult(BaseModel):
    """Batch operation result model."""

    successful: List[str]  # List of successful camera names
    failed: List[str]  # List of failed camera names
    results: Dict[str, bool]  # Maps camera names to success status
    successful_count: int
    failed_count: int


class BatchOperationResponse(BaseResponse):
    """Response model for batch operations."""

    data: BatchOperationResult


# Error Response
class ErrorDetail(BaseModel):
    """Error detail model."""

    error_type: str
    error_code: str
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseResponse):
    """Response model for error conditions."""

    success: bool = False
    error: ErrorDetail
    traceback: Optional[str] = None  # Only in development


# Parameter Range Responses
class ParameterRange(BaseModel):
    """Parameter range model."""

    min_value: float
    max_value: float
    step: Optional[float] = None
    default: Optional[float] = None


class RangeResponse(BaseResponse):
    """Response model for parameter ranges."""

    data: ParameterRange


# Configuration File Responses
class ConfigFileOperationResult(BaseModel):
    """Configuration file operation result."""

    file_path: str
    operation: str  # "import" or "export"
    success: bool
    properties_count: Optional[int] = None


class ConfigFileResponse(BaseResponse):
    """Response model for configuration file operations."""

    data: ConfigFileOperationResult


# Streaming Responses
class StreamInfo(BaseModel):
    """Stream information model."""

    camera: str
    streaming: bool
    stream_url: Optional[str] = None
    start_time: Optional[datetime] = None


class StreamStatus(BaseModel):
    """Stream status model."""

    camera: str
    streaming: bool
    connected: bool
    stream_url: Optional[str] = None
    uptime_seconds: Optional[float] = None


class StreamInfoResponse(BaseResponse):
    """Response model for stream information."""

    data: StreamInfo


class StreamStatusResponse(BaseResponse):
    """Response model for stream status."""

    data: StreamStatus


class ActiveStreamsResponse(BaseResponse):
    """Response model for active streams list."""

    data: List[str]  # List of camera names with active streams


# Homography Calibration & Measurement Responses
class HomographyCalibrationResult(BaseModel):
    """Homography calibration result model."""

    success: bool
    calibration_path: Optional[str] = None
    homography_matrix_summary: Optional[Dict[str, Any]] = None  # H matrix shape/determinant
    world_unit: Optional[str] = None
    inlier_count: Optional[int] = None
    total_points: Optional[int] = None


class HomographyCalibrationResponse(BaseResponse):
    """Response model for homography calibration."""

    data: HomographyCalibrationResult


class HomographyMeasurementResult(BaseModel):
    """Homography measurement result model."""

    success: bool
    corners_world: Optional[List[List[float]]] = None  # [[x, y], [x, y], ...]
    width_world: Optional[float] = None
    height_world: Optional[float] = None
    area_world: Optional[float] = None
    unit: Optional[str] = None


class HomographyMeasurementResponse(BaseResponse):
    """Response model for single homography measurement."""

    data: HomographyMeasurementResult


class HomographyDistanceResult(BaseModel):
    """Homography distance measurement result model."""

    success: bool
    distance: Optional[float] = None
    unit: Optional[str] = None
    point1_world: Optional[List[float]] = None  # [x, y]
    point2_world: Optional[List[float]] = None  # [x, y]


class HomographyDistanceResponse(BaseResponse):
    """Response model for distance measurement."""

    data: HomographyDistanceResult


class HomographyBatchMeasurementData(BaseModel):
    """Batch measurement data containing both box and distance measurements."""

    box_measurements: Optional[List[HomographyMeasurementResult]] = None
    distance_measurements: Optional[List[HomographyDistanceResult]] = None
    total_boxes: int = 0
    total_distances: int = 0
    successful_boxes: int = 0
    successful_distances: int = 0


class HomographyBatchMeasurementResponse(BaseResponse):
    """Response model for unified batch homography measurements."""

    data: HomographyBatchMeasurementData
