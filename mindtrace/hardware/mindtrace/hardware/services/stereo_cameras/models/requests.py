"""
Request models for StereoCameraService.

Contains all Pydantic models for API requests, ensuring proper
input validation and documentation for all stereo camera operations.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Backend & Discovery Operations
class BackendFilterRequest(BaseModel):
    """Request model for backend filtering."""

    backend: Optional[str] = Field(None, description="Backend name to filter by (BaslerStereoAce)")


# Stereo Camera Lifecycle Operations
class StereoCameraOpenRequest(BaseModel):
    """Request model for opening a stereo camera."""

    camera: str = Field(..., description="Camera name in format 'Backend:serial_number'")
    test_connection: bool = Field(False, description="Test connection after opening")


class StereoCameraOpenBatchRequest(BaseModel):
    """Request model for batch stereo camera opening."""

    cameras: List[str] = Field(..., description="List of camera names to open")
    test_connection: bool = Field(False, description="Test connections after opening")


class StereoCameraCloseRequest(BaseModel):
    """Request model for closing a stereo camera."""

    camera: str = Field(..., description="Camera name in format 'Backend:serial_number'")


class StereoCameraCloseBatchRequest(BaseModel):
    """Request model for batch stereo camera closing."""

    cameras: List[str] = Field(..., description="List of camera names to close")


# Query Operations
class StereoCameraQueryRequest(BaseModel):
    """Request model for stereo camera queries."""

    camera: str = Field(..., description="Camera name to query")


# Configuration Operations
class StereoCameraConfigureRequest(BaseModel):
    """Request model for stereo camera configuration."""

    camera: str = Field(..., description="Camera name in format 'Backend:serial_number'")
    properties: Dict[str, Any] = Field(..., description="Stereo camera properties to configure")


class StereoCameraConfigureBatchRequest(BaseModel):
    """Request model for batch stereo camera configuration."""

    configurations: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="Camera configurations as dict (camera_name -> properties)",
    )


# Capture Operations
class StereoCaptureRequest(BaseModel):
    """Request model for stereo capture."""

    camera: str = Field(..., description="Camera name")
    save_intensity_path: Optional[str] = Field(None, description="Path to save intensity image")
    save_disparity_path: Optional[str] = Field(None, description="Path to save disparity map")
    enable_intensity: bool = Field(True, description="Capture intensity image")
    enable_disparity: bool = Field(True, description="Capture disparity map")
    calibrate_disparity: bool = Field(True, description="Apply calibration to disparity")
    timeout_ms: int = Field(20000, description="Capture timeout in milliseconds")
    output_format: str = Field("pil", description="Output format (numpy or pil)")


class StereoCaptureBatchRequest(BaseModel):
    """Request model for batch stereo capture."""

    captures: List[Dict[str, Any]] = Field(..., description="List of capture configurations")
    output_format: str = Field("pil", description="Output format (numpy or pil)")


# Point Cloud Operations
class PointCloudCaptureRequest(BaseModel):
    """Request model for point cloud capture."""

    camera: str = Field(..., description="Camera name")
    save_path: Optional[str] = Field(None, description="Path to save point cloud (.ply)")
    include_colors: bool = Field(True, description="Include color information from intensity")
    remove_outliers: bool = Field(False, description="Remove statistical outliers")
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
    "StereoCameraOpenRequest",
    "StereoCameraOpenBatchRequest",
    "StereoCameraCloseRequest",
    "StereoCameraCloseBatchRequest",
    # Query
    "StereoCameraQueryRequest",
    # Configuration
    "StereoCameraConfigureRequest",
    "StereoCameraConfigureBatchRequest",
    # Capture
    "StereoCaptureRequest",
    "StereoCaptureBatchRequest",
    # Point Cloud
    "PointCloudCaptureRequest",
    "PointCloudCaptureBatchRequest",
]
