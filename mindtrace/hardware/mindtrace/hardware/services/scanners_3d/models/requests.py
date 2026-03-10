"""
Request models for Scanner3DService.

Contains all Pydantic models for API requests, ensuring proper
input validation and documentation for all 3D scanner operations.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Backend & Discovery Operations
class BackendFilterRequest(BaseModel):
    """Request model for backend filtering."""

    backend: Optional[str] = Field(None, description="Backend name to filter by (Photoneo)")


# Scanner Lifecycle Operations
class ScannerOpenRequest(BaseModel):
    """Request model for opening a 3D scanner."""

    scanner: str = Field(..., description="Scanner name in format 'Backend:serial_number'")
    test_connection: bool = Field(False, description="Test connection after opening")


class ScannerOpenBatchRequest(BaseModel):
    """Request model for batch scanner opening."""

    scanners: List[str] = Field(..., description="List of scanner names to open")
    test_connection: bool = Field(False, description="Test connections after opening")


class ScannerCloseRequest(BaseModel):
    """Request model for closing a 3D scanner."""

    scanner: str = Field(..., description="Scanner name in format 'Backend:serial_number'")


class ScannerCloseBatchRequest(BaseModel):
    """Request model for batch scanner closing."""

    scanners: List[str] = Field(..., description="List of scanner names to close")


# Query Operations
class ScannerQueryRequest(BaseModel):
    """Request model for scanner queries."""

    scanner: str = Field(..., description="Scanner name to query")


# Configuration Operations
class ScannerConfigureRequest(BaseModel):
    """Request model for scanner configuration.

    All fields are optional - only provided fields will be applied.
    """

    scanner: str = Field(..., description="Scanner name in format 'Backend:serial_number'")

    # Operation settings
    operation_mode: Optional[str] = Field(None, description="Operation mode: Camera, Scanner, Mode_2D")
    coding_strategy: Optional[str] = Field(None, description="Coding strategy: Normal, Interreflections, HighFrequency")
    coding_quality: Optional[str] = Field(None, description="Quality preset: Ultra, High, Fast")
    maximum_fps: Optional[float] = Field(None, description="Maximum frames per second (0-100)")

    # Exposure settings
    exposure_time: Optional[float] = Field(None, description="Exposure time in milliseconds")
    single_pattern_exposure: Optional[float] = Field(None, description="Single pattern exposure time")
    shutter_multiplier: Optional[int] = Field(None, description="Shutter multiplier (1-10)")
    scan_multiplier: Optional[int] = Field(None, description="Scan multiplier (1-10)")
    color_exposure: Optional[float] = Field(None, description="Color camera exposure time")

    # Lighting settings
    led_power: Optional[int] = Field(None, description="LED power level (0-4095)")
    laser_power: Optional[int] = Field(None, description="Laser/projector power level (1-4095)")

    # Texture settings
    texture_source: Optional[str] = Field(None, description="Texture source: LED, Computed, Laser, Focus, Color")
    camera_texture_source: Optional[str] = Field(None, description="Camera texture source: Laser, LED, Color")

    # Output settings
    output_topology: Optional[str] = Field(None, description="Output topology: Raw, RegularGrid, FullGrid")
    camera_space: Optional[str] = Field(None, description="Camera space: PrimaryCamera, ColorCamera")

    # Processing settings
    normals_estimation_radius: Optional[int] = Field(None, description="Normals estimation radius (0-4)")
    max_inaccuracy: Optional[float] = Field(None, description="Maximum allowed inaccuracy (0-100)")
    calibration_volume_only: Optional[bool] = Field(None, description="Filter to calibration volume only")
    hole_filling: Optional[bool] = Field(None, description="Enable hole filling")

    # Trigger settings
    trigger_mode: Optional[str] = Field(None, description="Trigger mode: Software, Hardware, Continuous")
    hardware_trigger: Optional[bool] = Field(None, description="Enable hardware trigger")
    hardware_trigger_signal: Optional[str] = Field(None, description="Hardware trigger signal: Falling, Rising, Both")


class ScannerConfigureBatchRequest(BaseModel):
    """Request model for batch scanner configuration."""

    configurations: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="Scanner configurations as dict (scanner_name -> properties)",
    )


# Scan Capture Operations
class ScanCaptureRequest(BaseModel):
    """Request model for 3D scan capture."""

    scanner: str = Field(..., description="Scanner name")
    save_range_path: Optional[str] = Field(None, description="Path to save range/depth image")
    save_intensity_path: Optional[str] = Field(None, description="Path to save intensity image")
    save_confidence_path: Optional[str] = Field(None, description="Path to save confidence image")
    save_normal_path: Optional[str] = Field(None, description="Path to save surface normal image")
    save_color_path: Optional[str] = Field(None, description="Path to save color texture image")
    enable_range: bool = Field(True, description="Capture range/depth data")
    enable_intensity: bool = Field(True, description="Capture intensity data")
    enable_confidence: bool = Field(False, description="Capture confidence data")
    enable_normal: bool = Field(False, description="Capture surface normals")
    enable_color: bool = Field(False, description="Capture color texture")
    timeout_ms: int = Field(10000, description="Capture timeout in milliseconds")
    output_format: str = Field("numpy", description="Output format (numpy)")


class ScanCaptureBatchRequest(BaseModel):
    """Request model for batch scan capture."""

    captures: List[Dict[str, Any]] = Field(..., description="List of capture configurations")
    output_format: str = Field("numpy", description="Output format (numpy)")


# Point Cloud Operations
class PointCloudCaptureRequest(BaseModel):
    """Request model for point cloud capture."""

    scanner: str = Field(..., description="Scanner name")
    save_path: Optional[str] = Field(None, description="Path to save point cloud (.ply)")
    include_colors: bool = Field(True, description="Include color/intensity information")
    include_confidence: bool = Field(False, description="Include confidence values")
    downsample_factor: int = Field(1, description="Downsampling factor (1 = no downsampling)")
    output_format: str = Field("numpy", description="Output format for points/colors (numpy)")


class PointCloudCaptureBatchRequest(BaseModel):
    """Request model for batch point cloud capture."""

    captures: List[Dict[str, Any]] = Field(..., description="List of point cloud capture configurations")
    output_format: str = Field("numpy", description="Output format (numpy)")


__all__ = [
    # Backend & Discovery
    "BackendFilterRequest",
    # Lifecycle
    "ScannerOpenRequest",
    "ScannerOpenBatchRequest",
    "ScannerCloseRequest",
    "ScannerCloseBatchRequest",
    # Query
    "ScannerQueryRequest",
    # Configuration
    "ScannerConfigureRequest",
    "ScannerConfigureBatchRequest",
    # Capture
    "ScanCaptureRequest",
    "ScanCaptureBatchRequest",
    # Point Cloud
    "PointCloudCaptureRequest",
    "PointCloudCaptureBatchRequest",
]
