"""
Request models for Camera API.

Contains all Pydantic models for API requests, ensuring proper
input validation and documentation.
"""

from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field


class CameraInitializeRequest(BaseModel):
    """Request model for camera initialization."""

    test_connection: bool = Field(True, description="Test connection after initialization")


class BatchCameraInitializeRequest(BaseModel):
    """Request model for batch camera initialization."""

    cameras: List[str] = Field(..., description="List of camera names to initialize")
    test_connections: bool = Field(True, description="Test connections after initialization")


class CameraConfigRequest(BaseModel):
    """Request model for camera configuration."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    properties: Dict[str, Any] = Field(..., description="Camera properties to configure")


class BatchCameraConfigRequest(BaseModel):
    """Request model for batch camera configuration."""

    configurations: Dict[str, Dict[str, Any]] = Field(
        ..., description="Dictionary mapping camera names to their configuration properties"
    )


class CaptureRequest(BaseModel):
    """Request model for image capture."""

    save_path: Optional[str] = Field(None, description="Optional path to save the captured image")
    gcs_bucket: Optional[str] = Field(None, description="GCS bucket name for cloud storage")
    gcs_path: Optional[str] = Field(None, description="GCS path within bucket for cloud storage")
    gcs_metadata: Optional[Dict[str, str]] = Field(None, description="Optional metadata for GCS upload")
    return_image: bool = Field(True, description="Whether to return captured image in response")


class BatchCaptureRequest(BaseModel):
    """Request model for batch image capture."""

    cameras: List[str] = Field(..., description="List of camera names to capture from")
    return_images: bool = Field(True, description="Whether to return captured images in response")


class HDRCaptureRequest(BaseModel):
    """Request model for HDR image capture."""

    exposure_levels: int = Field(ge=2, le=10, default=3, description="Number of different exposure levels to capture")
    exposure_multiplier: float = Field(gt=1.0, le=5.0, default=2.0, description="Multiplier between exposure levels")
    save_path_pattern: Optional[str] = Field(
        None, description="Optional path pattern for saving images. Use {exposure} placeholder"
    )
    gcs_bucket: Optional[str] = Field(None, description="GCS bucket name for cloud storage")
    gcs_path_pattern: Optional[str] = Field(None, description="GCS path pattern. Use {exposure} placeholder")
    gcs_metadata: Optional[Dict[str, str]] = Field(None, description="Optional metadata for GCS upload")
    return_images: bool = Field(True, description="Whether to return captured images in response")


class BatchHDRCaptureRequest(BaseModel):
    """Request model for batch HDR image capture."""

    cameras: List[str] = Field(..., description="List of camera names to capture HDR from")
    exposure_levels: int = Field(ge=2, le=10, default=3, description="Number of different exposure levels to capture")
    exposure_multiplier: float = Field(gt=1.0, le=5.0, default=2.0, description="Multiplier between exposure levels")
    save_path_pattern: Optional[str] = Field(
        None, description="Optional path pattern. Use {camera} and {exposure} placeholders"
    )
    gcs_bucket: Optional[str] = Field(None, description="GCS bucket name for cloud storage")
    gcs_path_pattern: Optional[str] = Field(
        None, description="GCS path pattern. Use {camera} and {exposure} placeholders"
    )
    gcs_metadata: Optional[Dict[str, str]] = Field(None, description="Optional metadata for GCS upload")
    return_images: bool = Field(True, description="Whether to return captured images in response")


class ConfigFileRequest(BaseModel):
    """Request model for configuration file operations."""

    config_path: str = Field(..., description="Path to configuration file")


class ExposureRequest(BaseModel):
    """Request model for exposure setting."""

    exposure: Union[int, float] = Field(..., description="Exposure time in microseconds")


class GainRequest(BaseModel):
    """Request model for gain setting."""

    gain: Union[int, float] = Field(..., description="Gain value")


class ROIRequest(BaseModel):
    """Request model for ROI (Region of Interest) setting."""

    x: int = Field(..., description="X offset in pixels")
    y: int = Field(..., description="Y offset in pixels")
    width: int = Field(..., description="ROI width in pixels")
    height: int = Field(..., description="ROI height in pixels")


class TriggerModeRequest(BaseModel):
    """Request model for trigger mode setting."""

    mode: str = Field(..., description="Trigger mode: 'continuous' or 'trigger'")


class PixelFormatRequest(BaseModel):
    """Request model for pixel format setting."""

    format: str = Field(..., description="Pixel format (e.g., 'BGR8', 'Mono8', 'RGB8')")


class WhiteBalanceRequest(BaseModel):
    """Request model for white balance setting."""

    mode: str = Field(..., description="White balance mode (e.g., 'auto', 'once', 'off')")


class ImageEnhancementRequest(BaseModel):
    """Request model for image enhancement setting."""

    enabled: bool = Field(..., description="Whether to enable image enhancement")


class NetworkConcurrentLimitRequest(BaseModel):
    """Request model for setting network concurrent capture limit."""

    limit: int = Field(ge=1, le=10, description="Maximum number of concurrent captures (1-10)")


class CameraQueryRequest(BaseModel):
    """Request model for camera query operations."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")


class BackendFilterRequest(BaseModel):
    """Request model for backend filtering."""

    backend: Optional[str] = Field(None, description="Backend name to filter by")


class CameraPropertiesRequest(BaseModel):
    """Request model for setting multiple camera properties."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    exposure: Optional[Union[int, float]] = Field(None, description="Exposure time in microseconds")
    gain: Optional[Union[int, float]] = Field(None, description="Gain value")
    roi: Optional[Tuple[int, int, int, int]] = Field(None, description="ROI as (x, y, width, height)")
    trigger_mode: Optional[str] = Field(None, description="Trigger mode")
    pixel_format: Optional[str] = Field(None, description="Pixel format")
    white_balance: Optional[str] = Field(None, description="White balance mode")
    image_enhancement: Optional[bool] = Field(None, description="Image enhancement enabled")

    class Config:
        # Allow tuple types in request
        arbitrary_types_allowed = True


class StreamRequest(BaseModel):
    """Request model for video stream endpoint."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")


class BatchConfigExportRequest(BaseModel):
    """Request model for batch configuration export."""

    cameras: List[str] = Field(..., description="List of camera names")
    config_path: str = Field(..., description="Path pattern with {camera} placeholder")


class BatchConfigImportRequest(BaseModel):
    """Request model for batch configuration import."""

    cameras: List[str] = Field(..., description="List of camera names")
    config_path: str = Field(..., description="Path pattern with {camera} placeholder")
