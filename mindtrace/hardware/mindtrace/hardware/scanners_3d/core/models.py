"""Data models for 3D scanner operations.

This module provides data structures for handling 3D scanner data including
multi-component scan results, coordinate maps, and point clouds.

Designed for structured light scanners like Photoneo PhoXi, but extensible
for other 3D scanning technologies (ToF, LiDAR, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Union

import numpy as np


class ScanComponent(Enum):
    """Available scan components from 3D scanners."""

    RANGE = "Range"  # Depth/Z map (Coord3D_C16 or similar)
    INTENSITY = "Intensity"  # Grayscale intensity image
    CONFIDENCE = "Confidence"  # Per-pixel confidence/quality map
    NORMAL = "Normal"  # Surface normal vectors
    COLOR = "ColorCamera"  # RGB color texture
    EVENT = "Event"  # Event data (timestamp, etc.)


class OperationMode(Enum):
    """Scanner operation mode."""

    CAMERA = "Camera"  # Single shot mode
    SCANNER = "Scanner"  # Continuous scanning mode
    MODE_2D = "Mode_2D"  # 2D imaging only


class CodingStrategy(Enum):
    """Structured light coding strategy."""

    NORMAL = "Normal"  # Standard coding
    INTERREFLECTIONS = "Interreflections"  # Optimized for reflective surfaces
    HIGH_FREQUENCY = "HighFrequency"  # High detail patterns


class CodingQuality(Enum):
    """Scan quality/speed tradeoff."""

    ULTRA = "Ultra"  # Highest quality, slowest
    HIGH = "High"  # Balanced quality/speed
    FAST = "Fast"  # Fastest, lower quality


class TextureSource(Enum):
    """Source for texture/intensity data."""

    LED = "LED"  # LED illumination
    COMPUTED = "Computed"  # Computed from patterns
    LASER = "Laser"  # Laser illumination
    FOCUS = "Focus"  # Focus-based
    COLOR = "Color"  # Color camera


class OutputTopology(Enum):
    """Point cloud output topology."""

    RAW = "Raw"  # Unorganized point cloud
    REGULAR_GRID = "RegularGrid"  # Regular grid structure
    FULL_GRID = "FullGrid"  # Full dense grid


class CameraSpace(Enum):
    """Coordinate system reference camera."""

    PRIMARY_CAMERA = "PrimaryCamera"  # Primary depth camera
    COLOR_CAMERA = "ColorCamera"  # Color camera reference


class TriggerMode(Enum):
    """Acquisition trigger mode."""

    SOFTWARE = "Software"  # Software triggered
    HARDWARE = "Hardware"  # Hardware triggered
    CONTINUOUS = "Continuous"  # Free-running


class HardwareTriggerSignal(Enum):
    """Hardware trigger signal edge."""

    FALLING = "Falling"
    RISING = "Rising"
    BOTH = "Both"


@dataclass
class ScannerConfiguration:
    """Configuration settings for 3D scanners.

    Groups all configurable parameters for structured light scanners.
    Not all parameters may be available on all scanner models.
    """

    # Operation settings
    operation_mode: Optional[OperationMode] = None
    coding_strategy: Optional[CodingStrategy] = None
    coding_quality: Optional[CodingQuality] = None
    maximum_fps: Optional[float] = None

    # Exposure settings
    exposure_time: Optional[float] = None  # milliseconds
    single_pattern_exposure: Optional[float] = None
    shutter_multiplier: Optional[int] = None  # 1-10
    scan_multiplier: Optional[int] = None  # 1-10
    color_exposure: Optional[float] = None  # Color camera exposure

    # Lighting settings
    led_power: Optional[int] = None  # 0-4095
    laser_power: Optional[int] = None  # 1-4095

    # Texture settings
    texture_source: Optional[TextureSource] = None
    camera_texture_source: Optional[TextureSource] = None

    # Output settings
    output_topology: Optional[OutputTopology] = None
    camera_space: Optional[CameraSpace] = None

    # Processing settings
    normals_estimation_radius: Optional[int] = None  # 0-4
    max_inaccuracy: Optional[float] = None  # 0-100
    calibration_volume_only: Optional[bool] = None
    hole_filling: Optional[bool] = None

    # Trigger settings
    trigger_mode: Optional[TriggerMode] = None
    hardware_trigger: Optional[bool] = None
    hardware_trigger_signal: Optional[HardwareTriggerSignal] = None

    def to_dict(self) -> Dict[str, any]:
        """Convert to dictionary, excluding None values."""
        result = {}
        for key, value in self.__dict__.items():
            if value is not None:
                if isinstance(value, Enum):
                    result[key] = value.value
                else:
                    result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "ScannerConfiguration":
        """Create configuration from dictionary."""
        config = cls()

        # Map string values to enums
        enum_mappings = {
            "operation_mode": OperationMode,
            "coding_strategy": CodingStrategy,
            "coding_quality": CodingQuality,
            "texture_source": TextureSource,
            "camera_texture_source": TextureSource,
            "output_topology": OutputTopology,
            "camera_space": CameraSpace,
            "trigger_mode": TriggerMode,
            "hardware_trigger_signal": HardwareTriggerSignal,
        }

        for key, value in data.items():
            if hasattr(config, key):
                if key in enum_mappings and isinstance(value, str):
                    try:
                        value = enum_mappings[key](value)
                    except ValueError:
                        pass  # Keep as string if not valid enum
                setattr(config, key, value)

        return config


@dataclass
class ScannerCapabilities:
    """Describes the capabilities of a 3D scanner.

    Used to query what features and settings are available on a specific scanner.
    """

    # Available components
    has_range: bool = True
    has_intensity: bool = False
    has_confidence: bool = False
    has_normal: bool = False
    has_color: bool = False

    # Available operation modes
    operation_modes: list = field(default_factory=list)
    coding_strategies: list = field(default_factory=list)
    coding_qualities: list = field(default_factory=list)
    texture_sources: list = field(default_factory=list)
    output_topologies: list = field(default_factory=list)

    # Parameter ranges
    exposure_range: Optional[tuple] = None  # (min, max) in ms
    led_power_range: Optional[tuple] = None  # (min, max)
    laser_power_range: Optional[tuple] = None  # (min, max)
    fps_range: Optional[tuple] = None  # (min, max)

    # Resolution
    depth_resolution: Optional[tuple] = None  # (width, height)
    color_resolution: Optional[tuple] = None  # (width, height)

    # Device info
    model: str = ""
    serial_number: str = ""
    firmware_version: str = ""


@dataclass
class ScanResult:
    """Result from 3D scanner capture containing multi-component data.

    Attributes:
        range_map: Depth/range map - typically uint16 or float32 (H, W)
        intensity: Intensity image - uint8 or uint16 (H, W) or (H, W, 3)
        confidence: Confidence map - uint8 or uint16 (H, W), values indicate quality
        normal_map: Surface normals - float32 (H, W, 3), xyz components
        color: Color texture - uint8 (H, W, 3) RGB
        timestamp: Capture timestamp in seconds (from device or system)
        frame_number: Sequential frame number
        components_enabled: Dict of which components were captured
        metadata: Additional scan metadata (exposure, gain, etc.)
    """

    range_map: Optional[np.ndarray] = None
    intensity: Optional[np.ndarray] = None
    confidence: Optional[np.ndarray] = None
    normal_map: Optional[np.ndarray] = None
    color: Optional[np.ndarray] = None
    timestamp: float = 0.0
    frame_number: int = 0
    components_enabled: Dict[ScanComponent, bool] = field(default_factory=dict)
    metadata: Dict[str, Union[str, int, float]] = field(default_factory=dict)

    @property
    def has_range(self) -> bool:
        """Check if range data is present."""
        return self.range_map is not None

    @property
    def has_intensity(self) -> bool:
        """Check if intensity data is present."""
        return self.intensity is not None

    @property
    def has_confidence(self) -> bool:
        """Check if confidence data is present."""
        return self.confidence is not None

    @property
    def has_normals(self) -> bool:
        """Check if normal map is present."""
        return self.normal_map is not None

    @property
    def has_color(self) -> bool:
        """Check if color data is present."""
        return self.color is not None

    @property
    def range_shape(self) -> tuple:
        """Get shape of range map."""
        return self.range_map.shape if self.has_range else (0, 0)

    @property
    def intensity_shape(self) -> tuple:
        """Get shape of intensity image."""
        return self.intensity.shape if self.has_intensity else (0, 0)

    def get_valid_mask(self, min_confidence: int = 0) -> np.ndarray:
        """Get mask of valid pixels based on range and confidence.

        Args:
            min_confidence: Minimum confidence threshold (0-255 typical)

        Returns:
            Boolean mask (H, W) where True indicates valid pixel
        """
        if not self.has_range:
            raise ValueError("No range data available")

        # Valid where range is non-zero
        mask = self.range_map > 0

        # Apply confidence threshold if available
        if self.has_confidence and min_confidence > 0:
            mask = mask & (self.confidence >= min_confidence)

        return mask

    def __repr__(self) -> str:
        """String representation of scan result."""
        components = []
        if self.has_range:
            components.append(f"range={self.range_shape}")
        if self.has_intensity:
            components.append(f"intensity={self.intensity_shape}")
        if self.has_confidence:
            components.append("confidence")
        if self.has_normals:
            components.append("normals")
        if self.has_color:
            components.append("color")

        return f"ScanResult(frame={self.frame_number}, {', '.join(components)})"


@dataclass
class CoordinateMap:
    """Coordinate map for efficient point cloud generation.

    Photoneo devices can provide pre-computed coordinate maps that allow
    efficient conversion from range-only data to full 3D point clouds.
    This enables faster transfers (only Z data) with local point cloud computation.

    Attributes:
        x_map: X coordinate map (H, W) - multiply by range to get X
        y_map: Y coordinate map (H, W) - multiply by range to get Y
        width: Map width in pixels
        height: Map height in pixels
        scale: Coordinate scale factor
        offset: Coordinate offset
        is_valid: Whether the map has been initialized
    """

    x_map: Optional[np.ndarray] = None
    y_map: Optional[np.ndarray] = None
    width: int = 0
    height: int = 0
    scale: float = 1.0
    offset: float = 0.0
    is_valid: bool = False

    @classmethod
    def from_projected_c(
        cls,
        projected_c: np.ndarray,
        width: int,
        height: int,
        scale: float = 1.0,
        offset: float = 0.0,
    ) -> "CoordinateMap":
        """Create coordinate map from Photoneo ProjectedC component.

        The ProjectedC component contains pre-computed X,Y coordinates
        that can be cached and reused for faster point cloud generation.

        Args:
            projected_c: ProjectedC data from Photoneo (H, W, 3) float32
            width: Image width
            height: Image height
            scale: Coordinate scale factor
            offset: Coordinate offset

        Returns:
            CoordinateMap instance
        """
        if projected_c.ndim != 3 or projected_c.shape[2] < 2:
            raise ValueError(f"Expected (H, W, 3) array, got {projected_c.shape}")

        return cls(
            x_map=projected_c[:, :, 0].astype(np.float32),
            y_map=projected_c[:, :, 1].astype(np.float32),
            width=width,
            height=height,
            scale=scale,
            offset=offset,
            is_valid=True,
        )

    def compute_point_cloud(
        self,
        range_map: np.ndarray,
        valid_mask: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Compute 3D point cloud from range map using cached coordinates.

        Args:
            range_map: Depth/range map (H, W)
            valid_mask: Optional mask of valid pixels

        Returns:
            Point cloud array (N, 3) with X, Y, Z coordinates
        """
        if not self.is_valid:
            raise ValueError("Coordinate map not initialized")

        if range_map.shape != (self.height, self.width):
            raise ValueError(
                f"Range map shape {range_map.shape} doesn't match coordinate map ({self.height}, {self.width})"
            )

        # Apply scale and offset to range
        z = range_map.astype(np.float32) * self.scale + self.offset

        # Compute X, Y from coordinate maps
        x = self.x_map * z
        y = self.y_map * z

        # Stack into point cloud
        points = np.stack([x, y, z], axis=-1)

        # Apply mask if provided
        if valid_mask is None:
            valid_mask = z > 0

        return points[valid_mask].reshape(-1, 3)

    def __repr__(self) -> str:
        """String representation."""
        status = "valid" if self.is_valid else "invalid"
        return f"CoordinateMap({self.width}x{self.height}, {status})"


@dataclass
class PointCloudData:
    """3D point cloud data with optional attributes.

    Attributes:
        points: Array of 3D points (N, 3) - (x, y, z) in meters
        colors: Optional RGB colors (N, 3) - values in [0, 1]
        normals: Optional surface normals (N, 3) - unit vectors
        confidence: Optional per-point confidence (N,)
        num_points: Number of valid points
        has_colors: Flag indicating if color information is present
    """

    points: np.ndarray
    colors: Optional[np.ndarray] = None
    normals: Optional[np.ndarray] = None
    confidence: Optional[np.ndarray] = None
    num_points: int = 0
    has_colors: bool = False

    def __post_init__(self):
        """Validate and set derived attributes."""
        if self.num_points == 0:
            self.num_points = len(self.points)

        if self.colors is not None:
            self.has_colors = True
            if len(self.colors) != self.num_points:
                raise ValueError(f"Colors length {len(self.colors)} doesn't match points length {self.num_points}")

        # Validate other arrays
        if self.normals is not None and len(self.normals) != self.num_points:
            raise ValueError(f"Normals length {len(self.normals)} doesn't match points length {self.num_points}")

        if self.confidence is not None and len(self.confidence) != self.num_points:
            raise ValueError(f"Confidence length {len(self.confidence)} doesn't match points length {self.num_points}")

    @property
    def has_normals(self) -> bool:
        """Check if normal information is present."""
        return self.normals is not None

    @property
    def has_confidence(self) -> bool:
        """Check if confidence information is present."""
        return self.confidence is not None

    def save_ply(self, path: str, binary: bool = True) -> None:
        """Save point cloud as PLY file.

        Args:
            path: Output file path
            binary: If True, save in binary format; otherwise ASCII

        Raises:
            ImportError: If plyfile is not installed
        """
        try:
            from plyfile import PlyData, PlyElement
        except ImportError:
            raise ImportError("plyfile package required for PLY export. Install with: pip install plyfile") from None

        # Build dtype based on available attributes
        dtype_list = [("x", "f4"), ("y", "f4"), ("z", "f4")]

        if self.has_colors:
            dtype_list.extend([("red", "u1"), ("green", "u1"), ("blue", "u1")])

        if self.has_normals:
            dtype_list.extend([("nx", "f4"), ("ny", "f4"), ("nz", "f4")])

        if self.has_confidence:
            dtype_list.append(("confidence", "f4"))

        vertices = np.zeros(self.num_points, dtype=dtype_list)

        vertices["x"] = self.points[:, 0]
        vertices["y"] = self.points[:, 1]
        vertices["z"] = self.points[:, 2]

        if self.has_colors:
            colors_uint8 = (self.colors * 255).astype(np.uint8)
            vertices["red"] = colors_uint8[:, 0]
            vertices["green"] = colors_uint8[:, 1]
            vertices["blue"] = colors_uint8[:, 2]

        if self.has_normals:
            vertices["nx"] = self.normals[:, 0]
            vertices["ny"] = self.normals[:, 1]
            vertices["nz"] = self.normals[:, 2]

        if self.has_confidence:
            vertices["confidence"] = self.confidence

        vertex_element = PlyElement.describe(vertices, "vertex")
        ply_data = PlyData([vertex_element])

        if binary:
            with open(path, "wb") as f:
                ply_data.write(f)
        else:
            with open(path, "w") as f:
                ply_data.text = True
                ply_data.write(f)

    def downsample(self, factor: int) -> "PointCloudData":
        """Downsample point cloud by given factor.

        Args:
            factor: Downsampling factor (e.g., 2 = keep every 2nd point)

        Returns:
            New PointCloudData with downsampled data
        """
        indices = np.arange(0, self.num_points, factor)

        return PointCloudData(
            points=self.points[indices],
            colors=self.colors[indices] if self.has_colors else None,
            normals=self.normals[indices] if self.has_normals else None,
            confidence=self.confidence[indices] if self.has_confidence else None,
            num_points=len(indices),
            has_colors=self.has_colors,
        )

    def filter_by_confidence(self, min_confidence: float) -> "PointCloudData":
        """Filter points by minimum confidence threshold.

        Args:
            min_confidence: Minimum confidence value (0.0 to 1.0)

        Returns:
            New PointCloudData with filtered points

        Raises:
            ValueError: If no confidence data available
        """
        if not self.has_confidence:
            raise ValueError("No confidence data available for filtering")

        mask = self.confidence >= min_confidence

        return PointCloudData(
            points=self.points[mask],
            colors=self.colors[mask] if self.has_colors else None,
            normals=self.normals[mask] if self.has_normals else None,
            confidence=self.confidence[mask],
            num_points=int(mask.sum()),
            has_colors=self.has_colors,
        )

    def __repr__(self) -> str:
        """String representation of point cloud."""
        attrs = []
        if self.has_colors:
            attrs.append("colors")
        if self.has_normals:
            attrs.append("normals")
        if self.has_confidence:
            attrs.append("confidence")

        attr_str = f", {', '.join(attrs)}" if attrs else ""
        return f"PointCloudData(points={self.num_points}{attr_str})"
