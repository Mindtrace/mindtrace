"""
Response models for Scanner3DService.

Contains all Pydantic models for API responses, ensuring consistent
response formatting across all 3D scanner management endpoints.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from mindtrace.hardware.core.types import ServiceStatus


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


class ListResponse(BaseResponse):
    """Response model for list data."""

    data: List[str]


class DictResponse(BaseResponse):
    """Response model for dictionary data."""

    data: Dict[str, Any]


# Backend & Discovery Responses
class BackendInfo(BaseModel):
    """3D scanner backend information model."""

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


# Scanner Status & Information
class ScannerStatus(BaseModel):
    """3D scanner status model."""

    name: str
    is_open: bool
    backend: str


class ScannerStatusResponse(BaseResponse):
    """Response model for scanner status."""

    data: ScannerStatus


class ScannerInfo(BaseModel):
    """3D scanner information model."""

    name: str
    backend: str
    serial_number: Optional[str] = None
    model: Optional[str] = None
    vendor: Optional[str] = None


class ScannerInfoResponse(BaseResponse):
    """Response model for scanner information."""

    data: ScannerInfo


# Configuration Responses
class ScannerConfiguration(BaseModel):
    """3D scanner configuration model."""

    # Operation settings
    operation_mode: Optional[str] = None
    coding_strategy: Optional[str] = None
    coding_quality: Optional[str] = None
    maximum_fps: Optional[float] = None

    # Exposure settings
    exposure_time: Optional[float] = None  # milliseconds
    single_pattern_exposure: Optional[float] = None
    shutter_multiplier: Optional[int] = None
    scan_multiplier: Optional[int] = None
    color_exposure: Optional[float] = None

    # Lighting settings
    led_power: Optional[int] = None
    laser_power: Optional[int] = None

    # Texture settings
    texture_source: Optional[str] = None
    camera_texture_source: Optional[str] = None

    # Output settings
    output_topology: Optional[str] = None
    camera_space: Optional[str] = None

    # Processing settings
    normals_estimation_radius: Optional[int] = None
    max_inaccuracy: Optional[float] = None
    calibration_volume_only: Optional[bool] = None
    hole_filling: Optional[bool] = None

    # Trigger settings
    trigger_mode: Optional[str] = None
    hardware_trigger: Optional[bool] = None
    hardware_trigger_signal: Optional[str] = None


class ScannerConfigurationResponse(BaseResponse):
    """Response model for scanner configuration."""

    data: ScannerConfiguration


class ScannerCapabilities(BaseModel):
    """Scanner capabilities model."""

    # Available components
    has_range: bool = True
    has_intensity: bool = False
    has_confidence: bool = False
    has_normal: bool = False
    has_color: bool = False

    # Available options
    operation_modes: List[str] = []
    coding_strategies: List[str] = []
    coding_qualities: List[str] = []
    texture_sources: List[str] = []
    output_topologies: List[str] = []

    # Parameter ranges
    exposure_range: Optional[Tuple[float, float]] = None
    led_power_range: Optional[Tuple[int, int]] = None
    laser_power_range: Optional[Tuple[int, int]] = None
    fps_range: Optional[Tuple[float, float]] = None

    # Resolution
    depth_resolution: Optional[Tuple[int, int]] = None
    color_resolution: Optional[Tuple[int, int]] = None

    # Device info
    model: str = ""
    serial_number: str = ""
    firmware_version: str = ""


class ScannerCapabilitiesResponse(BaseResponse):
    """Response model for scanner capabilities."""

    data: ScannerCapabilities


# Scan Capture Responses
class ScanCaptureResult(BaseModel):
    """Scan capture result model."""

    scanner_name: str
    frame_number: int
    range_shape: Optional[Tuple[int, ...]] = None
    intensity_shape: Optional[Tuple[int, ...]] = None
    confidence_shape: Optional[Tuple[int, ...]] = None
    normal_shape: Optional[Tuple[int, ...]] = None
    color_shape: Optional[Tuple[int, ...]] = None
    range_saved_path: Optional[str] = None
    intensity_saved_path: Optional[str] = None
    confidence_saved_path: Optional[str] = None
    normal_saved_path: Optional[str] = None
    color_saved_path: Optional[str] = None
    capture_timestamp: str


class ScanCaptureResponse(BaseResponse):
    """Response model for scan capture."""

    data: ScanCaptureResult


class ScanCaptureBatchResult(BaseModel):
    """Batch scan capture result model."""

    successful: int
    failed: int
    results: List[ScanCaptureResult]
    errors: Dict[str, str]


class ScanCaptureBatchResponse(BaseResponse):
    """Response model for batch scan capture."""

    data: ScanCaptureBatchResult


# Point Cloud Responses
class PointCloudResult(BaseModel):
    """Point cloud capture result model."""

    scanner_name: str
    num_points: int
    has_colors: bool
    has_normals: bool = False
    has_confidence: bool = False
    saved_path: Optional[str] = None
    points_shape: Optional[Tuple[int, ...]] = None
    colors_shape: Optional[Tuple[int, ...]] = None
    capture_timestamp: str


class PointCloudResponse(BaseResponse):
    """Response model for point cloud capture."""

    data: PointCloudResult


class PointCloudBatchResult(BaseModel):
    """Batch point cloud capture result model."""

    successful: int
    failed: int
    results: List[PointCloudResult]
    errors: Dict[str, str]


class PointCloudBatchResponse(BaseResponse):
    """Response model for batch point cloud capture."""

    data: PointCloudBatchResult


# Batch Operation Responses
class BatchOperationResult(BaseModel):
    """Individual batch operation result."""

    scanner: str
    success: bool
    message: str
    data: Optional[Any] = None


class BatchOperationResponse(BaseResponse):
    """Response model for batch operations."""

    data: Dict[str, Any]  # Contains: successful, failed, results


# Active Scanners Response
class ActiveScannersResponse(BaseResponse):
    """Response model for listing active scanners."""

    data: List[str]  # List of active scanner names


# System Diagnostics
class SystemDiagnostics(BaseModel):
    """System diagnostics model."""

    active_scanners: int
    total_scans: int
    total_point_clouds: int
    uptime_seconds: float
    memory_usage_mb: float


class SystemDiagnosticsResponse(BaseResponse):
    """Response model for system diagnostics."""

    data: SystemDiagnostics


# Health Check
class HealthCheckResponse(BaseModel):
    """Health check response model."""

    status: ServiceStatus
    service: str
    version: str = "1.0.0"
    backends: Optional[List[str]] = None
    active_scanners: int = 0
    uptime_seconds: Optional[float] = None
    error: Optional[str] = None


__all__ = [
    # Base
    "BaseResponse",
    "BoolResponse",
    "StringResponse",
    "ListResponse",
    "DictResponse",
    # Backend & Discovery
    "BackendInfo",
    "BackendsResponse",
    "BackendInfoResponse",
    # Status & Information
    "ScannerStatus",
    "ScannerStatusResponse",
    "ScannerInfo",
    "ScannerInfoResponse",
    # Configuration
    "ScannerConfiguration",
    "ScannerConfigurationResponse",
    "ScannerCapabilities",
    "ScannerCapabilitiesResponse",
    # Capture
    "ScanCaptureResult",
    "ScanCaptureResponse",
    "ScanCaptureBatchResult",
    "ScanCaptureBatchResponse",
    # Point Cloud
    "PointCloudResult",
    "PointCloudResponse",
    "PointCloudBatchResult",
    "PointCloudBatchResponse",
    # Batch Operations
    "BatchOperationResult",
    "BatchOperationResponse",
    # Active Scanners
    "ActiveScannersResponse",
    # System
    "SystemDiagnostics",
    "SystemDiagnosticsResponse",
    # Health Check
    "HealthCheckResponse",
    "ServiceStatus",
]
