"""
Request models for CameraManagerService.

Contains all Pydantic models for API requests, ensuring proper
input validation and documentation for all camera operations.
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


# Backend & Discovery Operations
class BackendFilterRequest(BaseModel):
    """Request model for backend filtering."""

    backend: Optional[str] = Field(None, description="Backend name to filter by (Basler, OpenCV, MockBasler)")


# Camera Lifecycle Operations
class CameraOpenRequest(BaseModel):
    """Request model for opening a camera."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    test_connection: bool = Field(True, description="Test connection after opening")


class CameraOpenBatchRequest(BaseModel):
    """Request model for batch camera opening."""

    cameras: List[str] = Field(..., description="List of camera names to open")
    test_connection: bool = Field(True, description="Test connections after opening")


class CameraCloseRequest(BaseModel):
    """Request model for closing a camera."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")


class CameraCloseBatchRequest(BaseModel):
    """Request model for batch camera closing."""

    cameras: List[str] = Field(..., description="List of camera names to close")


# Configuration Operations
class CameraConfigureRequest(BaseModel):
    """Request model for camera configuration."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    properties: Dict[str, Any] = Field(..., description="Camera properties to configure")


class CameraConfigureBatchRequest(BaseModel):
    """Request model for batch camera configuration."""

    configurations: Dict[str, Dict[str, Any]] = Field(
        ..., description="Dictionary mapping camera names to their configuration properties"
    )


class CameraQueryRequest(BaseModel):
    """Request model for camera query operations."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")


class ConfigFileImportRequest(BaseModel):
    """Request model for configuration file import."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    config_path: str = Field(..., description="Path to configuration file to import")


class ConfigFileExportRequest(BaseModel):
    """Request model for configuration file export."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    config_path: str = Field(..., description="Path where to export configuration file")


# Image Capture Operations
class CaptureImageRequest(BaseModel):
    """Request model for single image capture."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    save_path: Optional[str] = Field(None, description="Optional path to save the captured image")
    upload_to_gcs: bool = Field(False, description="Upload captured image to Google Cloud Storage")
    output_format: str = Field("numpy", description="Output format for returned image ('numpy' or 'pil')")

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        """Validate output format is supported."""
        if v.lower() not in ("numpy", "pil"):
            raise ValueError(f"Unsupported output_format: '{v}'. Supported formats: 'numpy', 'pil'")
        return v.lower()


class CaptureBatchRequest(BaseModel):
    """Request model for batch image capture."""

    cameras: List[str] = Field(..., description="List of camera names to capture from")
    upload_to_gcs: bool = Field(False, description="Upload captured images to Google Cloud Storage")
    output_format: str = Field("numpy", description="Output format for returned images ('numpy' or 'pil')")

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        """Validate output format is supported."""
        if v.lower() not in ("numpy", "pil"):
            raise ValueError(f"Unsupported output_format: '{v}'. Supported formats: 'numpy', 'pil'")
        return v.lower()


class CaptureHDRRequest(BaseModel):
    """Request model for HDR image capture."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    save_path_pattern: Optional[str] = Field(
        None, description="Optional path pattern for saving images. Use {exposure} placeholder"
    )
    exposure_levels: int = Field(3, ge=2, le=10, description="Number of different exposure levels to capture")
    exposure_multiplier: float = Field(2.0, gt=1.0, le=5.0, description="Multiplier between exposure levels")
    return_images: bool = Field(True, description="Whether to return captured images in response")
    upload_to_gcs: bool = Field(False, description="Upload captured images to Google Cloud Storage")
    output_format: str = Field("numpy", description="Output format for returned images ('numpy' or 'pil')")

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        """Validate output format is supported."""
        if v.lower() not in ("numpy", "pil"):
            raise ValueError(f"Unsupported output_format: '{v}'. Supported formats: 'numpy', 'pil'")
        return v.lower()


class CaptureHDRBatchRequest(BaseModel):
    """Request model for batch HDR image capture."""

    cameras: List[str] = Field(..., description="List of camera names to capture HDR from")
    save_path_pattern: Optional[str] = Field(
        None, description="Optional path pattern. Use {camera} and {exposure} placeholders"
    )
    exposure_levels: int = Field(3, ge=2, le=10, description="Number of different exposure levels to capture")
    exposure_multiplier: float = Field(2.0, gt=1.0, le=5.0, description="Multiplier between exposure levels")
    return_images: bool = Field(True, description="Whether to return captured images in response")
    upload_to_gcs: bool = Field(False, description="Upload captured images to Google Cloud Storage")
    output_format: str = Field("numpy", description="Output format for returned images ('numpy' or 'pil')")

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        """Validate output format is supported."""
        if v.lower() not in ("numpy", "pil"):
            raise ValueError(f"Unsupported output_format: '{v}'. Supported formats: 'numpy', 'pil'")
        return v.lower()


# Network & Bandwidth Operations
class BandwidthLimitRequest(BaseModel):
    """Request model for setting bandwidth limit."""

    max_concurrent_captures: int = Field(..., ge=1, le=10, description="Maximum number of concurrent captures (1-10)")


# Specific Camera Parameter Requests
class ExposureRequest(BaseModel):
    """Request model for exposure setting."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    exposure: Union[int, float] = Field(..., description="Exposure time in microseconds")


class GainRequest(BaseModel):
    """Request model for gain setting."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    gain: Union[int, float] = Field(..., description="Gain value")


class ROIRequest(BaseModel):
    """Request model for ROI (Region of Interest) setting."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    x: int = Field(..., description="X offset in pixels")
    y: int = Field(..., description="Y offset in pixels")
    width: int = Field(..., description="ROI width in pixels")
    height: int = Field(..., description="ROI height in pixels")


class TriggerModeRequest(BaseModel):
    """Request model for trigger mode setting."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    mode: str = Field(..., description="Trigger mode: 'continuous' or 'trigger'")


class PixelFormatRequest(BaseModel):
    """Request model for pixel format setting."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    format: str = Field(..., description="Pixel format (e.g., 'BGR8', 'Mono8', 'RGB8')")


class WhiteBalanceRequest(BaseModel):
    """Request model for white balance setting."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    mode: str = Field(..., description="White balance mode (e.g., 'auto', 'once', 'off')")


class ImageEnhancementRequest(BaseModel):
    """Request model for image enhancement setting."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    enabled: bool = Field(..., description="Whether to enable image enhancement")


# Network-specific camera parameters
class BandwidthLimitCameraRequest(BaseModel):
    """Request model for setting camera bandwidth limit."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    bandwidth_limit: Union[int, float] = Field(..., description="Bandwidth limit in bytes per second")


class PacketSizeRequest(BaseModel):
    """Request model for setting camera packet size."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    packet_size: int = Field(..., description="Packet size in bytes")


class InterPacketDelayRequest(BaseModel):
    """Request model for setting inter-packet delay."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    delay: Union[int, float] = Field(..., description="Inter-packet delay in microseconds")
