"""
Response models for Camera API.

Contains all Pydantic models for API responses, ensuring consistent
response formatting across all endpoints.
"""

from datetime import datetime, UTC
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field


class BaseResponse(BaseModel):
    """Base response model for all API endpoints."""

    success: bool
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BoolResponse(BaseResponse):
    """Response model for boolean operations."""

    pass


class ListResponse(BaseResponse):
    """Response model for list data."""

    data: List[str]


class DictResponse(BaseResponse):
    """Response model for dictionary data."""

    data: Dict[str, Any]


class FloatResponse(BaseResponse):
    """Response model for float values."""

    data: float


class StringResponse(BaseResponse):
    """Response model for string values."""

    data: str


class IntResponse(BaseResponse):
    """Response model for integer values."""

    data: int


class CameraInfo(BaseModel):
    """Camera information model."""

    name: str
    backend: str
    device_name: str
    active: bool
    connected: bool


class CameraProperties(BaseModel):
    """Camera properties model."""

    exposure: Optional[float] = None
    gain: Optional[float] = None
    roi: Optional[Tuple[int, int, int, int]] = None
    trigger_mode: Optional[str] = None
    pixel_format: Optional[str] = None
    white_balance: Optional[str] = None
    image_enhancement: Optional[bool] = None


class CaptureResponse(BaseResponse):
    """Response model for image capture operations."""

    image_data: Optional[str] = None  # Base64 encoded image
    save_path: Optional[str] = None
    gcs_uri: Optional[str] = None  # GCS URI of uploaded image
    media_type: str = "image/jpeg"


class HDRCaptureResponse(BaseResponse):
    """Response model for HDR capture operations."""

    images: Optional[List[str]] = None  # Base64 encoded images
    exposure_levels: Optional[List[float]] = None
    gcs_uris: Optional[List[str]] = None  # GCS URIs of uploaded images
    successful_captures: int


class ErrorResponse(BaseResponse):
    """Response model for error conditions."""

    success: bool = False
    error_type: str
    error_code: str
    details: Optional[Dict[str, Any]] = None
    traceback: Optional[str] = None  # Only in development


class CameraInfoResponse(BaseResponse):
    """Response model for camera information."""

    data: CameraInfo


class CameraPropertiesResponse(BaseResponse):
    """Response model for camera properties."""

    data: CameraProperties


class CameraListResponse(BaseResponse):
    """Response model for camera list operations."""

    data: List[CameraInfo]


class BackendInfoResponse(BaseResponse):
    """Response model for backend information."""

    data: Dict[str, Any]


class NetworkBandwidthResponse(BaseResponse):
    """Response model for network bandwidth information."""

    data: Dict[str, Any]


class RangeResponse(BaseResponse):
    """Response model for parameter ranges (e.g., exposure range, gain range)."""

    data: Tuple[float, float]

    class Config:
        # Allow tuple types in response
        arbitrary_types_allowed = True


class PixelFormatListResponse(BaseResponse):
    """Response model for available pixel formats."""

    data: List[str]


class WhiteBalanceListResponse(BaseResponse):
    """Response model for available white balance modes."""

    data: List[str]


class BatchOperationResponse(BaseResponse):
    """Response model for batch operations."""

    results: Dict[str, bool]  # Maps camera names to success status
    successful_count: int
    failed_count: int


class ConfigurationResponse(BaseResponse):
    """Response model for configuration operations."""

    data: Dict[str, Any]  # Configuration data


class StatusResponse(BaseResponse):
    """Response model for status checks."""
    data: Dict[str, Any]  # Status information 


class StreamResponse(BaseResponse):
    """Response model for video stream endpoint."""
    media_type: str = "multipart/x-mixed-replace; boundary=frame"


class BatchHDRCaptureResponse(BaseResponse):
    """Response model for batch HDR capture operations."""
    data: Dict[str, HDRCaptureResponse]


class BatchCaptureResponse(BaseResponse):
    """Response model for batch capture operations."""
    data: Dict[str, CaptureResponse] 