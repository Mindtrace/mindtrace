"""
Response models for StereoCameraService.

Contains all Pydantic models for API responses, ensuring consistent
response formatting across all stereo camera management endpoints.
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


class ListResponse(BaseResponse):
    """Response model for list data."""

    data: List[str]


class DictResponse(BaseResponse):
    """Response model for dictionary data."""

    data: Dict[str, Any]


# Backend & Discovery Responses
class BackendInfo(BaseModel):
    """Stereo camera backend information model."""

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


# Camera Status & Information
class StereoCameraStatus(BaseModel):
    """Stereo camera status model."""

    name: str
    is_open: bool
    backend: str
    has_calibration: bool


class StereoCameraStatusResponse(BaseResponse):
    """Response model for stereo camera status."""

    data: StereoCameraStatus


class StereoCameraInfo(BaseModel):
    """Stereo camera information model."""

    name: str
    backend: str
    serial_number: Optional[str] = None
    has_calibration: bool
    calibration_info: Optional[Dict[str, Any]] = None


class StereoCameraInfoResponse(BaseResponse):
    """Response model for stereo camera information."""

    data: StereoCameraInfo


# Configuration Responses
class StereoCameraConfiguration(BaseModel):
    """Stereo camera configuration model."""

    exposure_time: Optional[float] = None  # microseconds
    gain: Optional[float] = None
    depth_quality: Optional[str] = None
    pixel_format: Optional[str] = None
    binning: Optional[Tuple[int, int]] = None
    illumination_mode: Optional[str] = None
    depth_range: Optional[Tuple[float, float]] = None


class StereoCameraConfigurationResponse(BaseResponse):
    """Response model for stereo camera configuration."""

    data: StereoCameraConfiguration


# Capture Responses
class StereoCaptureResult(BaseModel):
    """Stereo capture result model."""

    camera_name: str
    frame_number: int
    intensity_shape: Optional[Tuple[int, ...]] = None
    disparity_shape: Optional[Tuple[int, ...]] = None
    intensity_saved_path: Optional[str] = None
    disparity_saved_path: Optional[str] = None
    capture_timestamp: str


class StereoCaptureResponse(BaseResponse):
    """Response model for stereo capture."""

    data: StereoCaptureResult


class StereoCaptureBatchResult(BaseModel):
    """Batch stereo capture result model."""

    successful: int
    failed: int
    results: List[StereoCaptureResult]
    errors: Dict[str, str]


class StereoCaptureBatchResponse(BaseResponse):
    """Response model for batch stereo capture."""

    data: StereoCaptureBatchResult


# Point Cloud Responses
class PointCloudResult(BaseModel):
    """Point cloud capture result model."""

    camera_name: str
    num_points: int
    has_colors: bool
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

    camera: str
    success: bool
    message: str
    data: Optional[Any] = None


class BatchOperationResponse(BaseResponse):
    """Response model for batch operations."""

    data: Dict[str, Any]  # Contains: successful, failed, results


# Active Cameras Response
class ActiveStereoCamerasResponse(BaseResponse):
    """Response model for listing active stereo cameras."""

    data: List[str]  # List of active camera names


# System Diagnostics
class SystemDiagnostics(BaseModel):
    """System diagnostics model."""

    active_cameras: int
    total_captures: int
    uptime_seconds: float
    memory_usage_mb: float


class SystemDiagnosticsResponse(BaseResponse):
    """Response model for system diagnostics."""

    data: SystemDiagnostics


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
    "StereoCameraStatus",
    "StereoCameraStatusResponse",
    "StereoCameraInfo",
    "StereoCameraInfoResponse",
    # Configuration
    "StereoCameraConfiguration",
    "StereoCameraConfigurationResponse",
    # Capture
    "StereoCaptureResult",
    "StereoCaptureResponse",
    "StereoCaptureBatchResult",
    "StereoCaptureBatchResponse",
    # Point Cloud
    "PointCloudResult",
    "PointCloudResponse",
    "PointCloudBatchResult",
    "PointCloudBatchResponse",
    # Batch Operations
    "BatchOperationResult",
    "BatchOperationResponse",
    # Active Cameras
    "ActiveStereoCamerasResponse",
    # System
    "SystemDiagnostics",
    "SystemDiagnosticsResponse",
]
