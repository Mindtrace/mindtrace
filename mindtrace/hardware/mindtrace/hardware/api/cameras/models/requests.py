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

    configurations: Union[Dict[str, Dict[str, Any]], List[Dict[str, Any]]] = Field(
        ...,
        description="Camera configurations as dict (camera_name -> properties) or list of {camera, properties} objects",
    )

    @field_validator("configurations")
    @classmethod
    def validate_configurations(
        cls, v: Union[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]
    ) -> Dict[str, Dict[str, Any]]:
        """Convert list format to dict format."""
        if isinstance(v, dict):
            return v
        elif isinstance(v, list):
            # Convert list format to dict format
            result = {}
            for item in v:
                if not isinstance(item, dict):
                    raise ValueError("Each item in configurations list must be a dict")
                if "camera" not in item:
                    raise ValueError("Each configuration must have a 'camera' field")
                if "properties" not in item:
                    raise ValueError("Each configuration must have a 'properties' field")
                result[item["camera"]] = item["properties"]
            return result
        else:
            raise ValueError("configurations must be dict or list")


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
        v_lower = v.lower()
        # Accept common image formats and map them to appropriate return type
        if v_lower in ("numpy", "pil"):
            return v_lower
        elif v_lower in ("jpg", "jpeg", "png", "tiff", "tif", "bmp", "webp"):
            # File formats map to numpy for simplicity
            return "numpy"
        else:
            raise ValueError(
                f"Unsupported output_format: '{v}'. Supported formats: 'numpy', 'pil', 'jpeg', 'jpg', 'png', 'tiff', 'bmp', 'webp'"
            )



class CaptureBatchRequest(BaseModel):
    """Request model for batch image capture."""

    cameras: List[str] = Field(..., description="List of camera names to capture from")
    save_path_pattern: Optional[str] = Field(
        None, description="Optional path pattern for saving images. Use {camera} placeholder for camera name"
    )
    upload_to_gcs: bool = Field(False, description="Upload captured images to Google Cloud Storage")
    output_format: str = Field("numpy", description="Output format for returned images ('numpy' or 'pil')")

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        """Validate output format is supported."""
        v_lower = v.lower()
        # Accept common image formats and map them to appropriate return type
        if v_lower in ("numpy", "pil"):
            return v_lower
        elif v_lower in ("jpg", "jpeg", "png", "tiff", "tif", "bmp", "webp"):
            # File formats map to numpy for simplicity
            return "numpy"
        else:
            raise ValueError(
                f"Unsupported output_format: '{v}'. Supported formats: 'numpy', 'pil', 'jpeg', 'jpg', 'png', 'tiff', 'bmp', 'webp'"
            )



class CaptureHDRRequest(BaseModel):
    """Request model for HDR image capture."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    save_path_pattern: Optional[str] = Field(
        None, description="Optional path pattern for saving images. Use {exposure} placeholder"
    )
    exposure_levels: Union[int, List[float]] = Field(
        3, description="Number of exposure levels (int) or explicit exposure values (List[float])"
    )
    exposure_multiplier: float = Field(2.0, gt=1.0, le=5.0, description="Multiplier between exposure levels (used when exposure_levels is int)")
    return_images: bool = Field(True, description="Whether to return captured images in response")
    upload_to_gcs: bool = Field(False, description="Upload captured images to Google Cloud Storage")
    output_format: str = Field("numpy", description="Output format for returned images ('numpy' or 'pil')")

    @field_validator("exposure_levels")
    @classmethod
    def validate_exposure_levels(cls, v: Union[int, List[float]]) -> Union[int, List[float]]:
        """Validate exposure levels."""
        if isinstance(v, int):
            if v < 2 or v > 10:
                raise ValueError("exposure_levels as int must be between 2 and 10")
            return v
        elif isinstance(v, list):
            if len(v) < 2:
                raise ValueError("exposure_levels as list must have at least 2 values")
            if not all(isinstance(x, (int, float)) and x > 0 for x in v):
                raise ValueError("All exposure values must be positive numbers")
            return v
        else:
            raise ValueError("exposure_levels must be int or List[float]")

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        """Validate output format is supported."""
        v_lower = v.lower()
        # Accept common image formats and map them to appropriate return type
        if v_lower in ("numpy", "pil"):
            return v_lower
        elif v_lower in ("jpg", "jpeg", "png", "tiff", "tif", "bmp", "webp"):
            # File formats map to numpy for simplicity
            return "numpy"
        else:
            raise ValueError(
                f"Unsupported output_format: '{v}'. Supported formats: 'numpy', 'pil', 'jpeg', 'jpg', 'png', 'tiff', 'bmp', 'webp'"
            )



class CaptureHDRBatchRequest(BaseModel):
    """Request model for batch HDR image capture."""

    cameras: List[str] = Field(..., description="List of camera names to capture HDR from")
    save_path_pattern: Optional[str] = Field(
        None, description="Optional path pattern. Use {camera} and {exposure} placeholders"
    )
    exposure_levels: Union[int, List[float]] = Field(
        3, description="Number of exposure levels (int) or explicit exposure values (List[float])"
    )
    exposure_multiplier: float = Field(2.0, gt=1.0, le=5.0, description="Multiplier between exposure levels (used when exposure_levels is int)")
    return_images: bool = Field(True, description="Whether to return captured images in response")
    upload_to_gcs: bool = Field(False, description="Upload captured images to Google Cloud Storage")
    output_format: str = Field("numpy", description="Output format for returned images ('numpy' or 'pil')")

    @field_validator("exposure_levels")
    @classmethod
    def validate_exposure_levels(cls, v: Union[int, List[float]]) -> Union[int, List[float]]:
        """Validate exposure levels."""
        if isinstance(v, int):
            if v < 2 or v > 10:
                raise ValueError("exposure_levels as int must be between 2 and 10")
            return v
        elif isinstance(v, list):
            if len(v) < 2:
                raise ValueError("exposure_levels as list must have at least 2 values")
            if not all(isinstance(x, (int, float)) and x > 0 for x in v):
                raise ValueError("All exposure values must be positive numbers")
            return v
        else:
            raise ValueError("exposure_levels must be int or List[float]")

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        """Validate output format is supported."""
        v_lower = v.lower()
        # Accept common image formats and map them to appropriate return type
        if v_lower in ("numpy", "pil"):
            return v_lower
        elif v_lower in ("jpg", "jpeg", "png", "tiff", "tif", "bmp", "webp"):
            # File formats map to numpy for simplicity
            return "numpy"
        else:
            raise ValueError(
                f"Unsupported output_format: '{v}'. Supported formats: 'numpy', 'pil', 'jpeg', 'jpg', 'png', 'tiff', 'bmp', 'webp'"
            )



# Network & Bandwidth Operations
class BandwidthLimitRequest(BaseModel):
    """Request model for setting bandwidth limit."""

    max_concurrent_captures: int = Field(..., ge=1, le=10, description="Maximum number of concurrent captures (1-10)")


class CameraPerformanceSettingsRequest(BaseModel):
    """Request model for updating camera performance settings.

    Global settings (always applicable):
    - timeout_ms, retrieve_retry_count, max_concurrent_captures

    Per-camera GigE settings (requires camera field, only for GigE cameras):
    - packet_size, inter_packet_delay, bandwidth_limit_mbps
    """

    camera: Optional[str] = Field(None, description="Optional camera name for per-camera GigE settings (format 'Backend:device_name')")
    timeout_ms: Optional[int] = Field(None, ge=100, le=30000, description="Capture timeout in milliseconds (100-30000)")
    retrieve_retry_count: Optional[int] = Field(None, ge=1, le=10, description="Number of capture retry attempts (1-10)")
    max_concurrent_captures: Optional[int] = Field(None, ge=1, le=10, description="Maximum concurrent captures (1-10)")

    # GigE-specific performance parameters (require camera field)
    packet_size: Optional[int] = Field(None, ge=1476, le=16000, description="GigE packet size in bytes (1476-16000, typically 1500 or 9000)")
    inter_packet_delay: Optional[int] = Field(None, ge=0, le=65535, description="Inter-packet delay in ticks (0-65535, higher = slower)")
    bandwidth_limit_mbps: Optional[float] = Field(None, ge=1.0, le=10000.0, description="Bandwidth limit in Mbps (1.0-10000.0, None = unlimited)")


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


# Streaming Operations
class StreamStartRequest(BaseModel):
    """Request model for starting camera stream."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
    quality: int = Field(85, description="JPEG quality (1-100)", ge=1, le=100)
    fps: int = Field(30, description="Frames per second", ge=1, le=120)


class StreamStopRequest(BaseModel):
    """Request model for stopping camera stream."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")


class StreamStatusRequest(BaseModel):
    """Request model for getting stream status."""

    camera: str = Field(..., description="Camera name in format 'Backend:device_name'")
