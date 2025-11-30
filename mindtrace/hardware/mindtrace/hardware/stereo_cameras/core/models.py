"""Data models for stereo camera operations.

This module provides data structures for handling stereo camera data including
multi-component capture results, calibration parameters, and 3D point clouds.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class StereoGrabResult:
    """Result from stereo camera capture containing multi-component data.

    Attributes:
        intensity: Intensity image - RGB8 (H, W, 3) or Mono8 (H, W)
        disparity: Disparity map - uint16 (H, W)
        timestamp: Capture timestamp in seconds
        frame_number: Sequential frame number
        disparity_calibrated: Calibrated disparity map - float32 (H, W), optional
        has_intensity: Flag indicating if intensity data is present
        has_disparity: Flag indicating if disparity data is present
    """

    intensity: Optional[np.ndarray]
    disparity: Optional[np.ndarray]
    timestamp: float
    frame_number: int
    disparity_calibrated: Optional[np.ndarray] = None
    has_intensity: bool = True
    has_disparity: bool = True

    @property
    def intensity_shape(self) -> tuple:
        """Get shape of intensity image."""
        return self.intensity.shape if self.has_intensity and self.intensity is not None else (0, 0)

    @property
    def disparity_shape(self) -> tuple:
        """Get shape of disparity map."""
        return self.disparity.shape if self.has_disparity and self.disparity is not None else (0, 0)

    @property
    def is_color_intensity(self) -> bool:
        """Check if intensity is color (RGB) vs grayscale."""
        if not self.has_intensity or self.intensity is None:
            return False
        return self.intensity.ndim == 3 and self.intensity.shape[2] == 3

    def __repr__(self) -> str:
        """String representation of grab result."""
        return (
            f"StereoGrabResult(frame={self.frame_number}, "
            f"intensity={self.intensity_shape}, "
            f"disparity={self.disparity_shape}, "
            f"calibrated={self.disparity_calibrated is not None})"
        )


@dataclass
class StereoCalibrationData:
    """Factory calibration parameters for stereo camera.

    These parameters are provided by the camera manufacturer and used for
    3D reconstruction from disparity maps.

    Attributes:
        baseline: Stereo baseline in meters (distance between camera pair)
        focal_length: Focal length in pixels
        principal_point_u: Principal point U coordinate in pixels
        principal_point_v: Principal point V coordinate in pixels
        scale3d: Scale factor for disparity conversion
        offset3d: Offset for disparity conversion
        Q: 4x4 reprojection matrix for point cloud generation
    """

    baseline: float
    focal_length: float
    principal_point_u: float
    principal_point_v: float
    scale3d: float
    offset3d: float
    Q: np.ndarray = field(repr=False)

    @classmethod
    def from_camera_params(cls, params: dict) -> "StereoCalibrationData":
        """Create calibration data from camera parameter dictionary.

        Args:
            params: Dictionary containing calibration parameters:
                - Scan3dBaseline: Baseline in meters
                - Scan3dFocalLength: Focal length in pixels
                - Scan3dPrincipalPointU: Principal point U in pixels
                - Scan3dPrincipalPointV: Principal point V in pixels
                - Scan3dCoordinateScale: Scale factor
                - Scan3dCoordinateOffset: Offset

        Returns:
            StereoCalibrationData instance
        """
        baseline = params["Scan3dBaseline"]
        focal = params["Scan3dFocalLength"]
        pp_u = params["Scan3dPrincipalPointU"]
        pp_v = params["Scan3dPrincipalPointV"]
        scale = params["Scan3dCoordinateScale"]
        offset = params["Scan3dCoordinateOffset"]

        # Construct Q matrix for cv2.reprojectImageTo3D
        Q = np.array([[1, 0, 0, -pp_u], [0, -1, 0, pp_v], [0, 0, 0, -focal], [0, 0, 1 / baseline, 0]], dtype=np.float64)

        return cls(
            baseline=baseline,
            focal_length=focal,
            principal_point_u=pp_u,
            principal_point_v=pp_v,
            scale3d=scale,
            offset3d=offset,
            Q=Q,
        )

    def calibrate_disparity(self, disparity: np.ndarray) -> np.ndarray:
        """Apply calibration to raw disparity map.

        Args:
            disparity: Raw disparity map (uint16)

        Returns:
            Calibrated disparity map (float32)
        """
        # Apply scale and offset
        disp_cal = np.float32(disparity * self.scale3d + self.offset3d)

        # Reset invalid pixels (zero disparity means no valid depth)
        if self.offset3d != 0:
            disp_cal = np.where(disparity == 0, 0, disp_cal)

        return disp_cal

    def __repr__(self) -> str:
        """String representation of calibration data."""
        return (
            f"StereoCalibrationData(baseline={self.baseline * 1000:.2f}mm, "
            f"focal={self.focal_length:.1f}px, "
            f"pp=({self.principal_point_u:.1f}, {self.principal_point_v:.1f}))"
        )


@dataclass
class PointCloudData:
    """3D point cloud data with optional color information.

    Attributes:
        points: Array of 3D points (N, 3) - (x, y, z) in meters
        colors: Optional array of RGB colors (N, 3) - values in [0, 1]
        num_points: Number of valid points
        has_colors: Flag indicating if color information is present
    """

    points: np.ndarray
    colors: Optional[np.ndarray] = None
    num_points: int = 0
    has_colors: bool = False

    def __post_init__(self):
        """Validate and set derived attributes."""
        if self.num_points == 0:
            self.num_points = len(self.points)

        if self.colors is not None:
            self.has_colors = True
            if len(self.colors) != self.num_points:
                raise ValueError(f"Points and colors must have same length: {self.num_points} vs {len(self.colors)}")

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

        # Prepare vertex data
        vertices = np.zeros(
            self.num_points,
            dtype=[
                ("x", "f4"),
                ("y", "f4"),
                ("z", "f4"),
                ("red", "u1"),
                ("green", "u1"),
                ("blue", "u1"),
            ],
        )

        vertices["x"] = self.points[:, 0]
        vertices["y"] = self.points[:, 1]
        vertices["z"] = self.points[:, 2]

        if self.has_colors:
            # Convert from [0, 1] to [0, 255]
            colors_uint8 = (self.colors * 255).astype(np.uint8)
            vertices["red"] = colors_uint8[:, 0]
            vertices["green"] = colors_uint8[:, 1]
            vertices["blue"] = colors_uint8[:, 2]
        else:
            # Default white color
            vertices["red"] = 255
            vertices["green"] = 255
            vertices["blue"] = 255

        # Create PLY element
        vertex_element = PlyElement.describe(vertices, "vertex")
        ply_data = PlyData([vertex_element])

        # Write to file
        if binary:
            with open(path, "wb") as f:
                ply_data.write(f)
        else:
            # ASCII format requires text mode
            with open(path, "w") as f:
                ply_data.text = True
                ply_data.write(f)

    def to_open3d(self):
        """Convert to Open3D PointCloud object.

        Returns:
            open3d.geometry.PointCloud instance

        Raises:
            ImportError: If open3d is not installed
        """
        try:
            import open3d as o3d
        except ImportError:
            raise ImportError("open3d package required for visualization. Install with: pip install open3d") from None

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(self.points)

        if self.has_colors:
            pcd.colors = o3d.utility.Vector3dVector(self.colors)

        return pcd

    def downsample(self, factor: int) -> "PointCloudData":
        """Downsample point cloud by given factor.

        Args:
            factor: Downsampling factor (e.g., 2 = keep every 2nd point)

        Returns:
            New PointCloudData with downsampled points
        """
        indices = np.arange(0, self.num_points, factor)
        points_ds = self.points[indices]
        colors_ds = self.colors[indices] if self.has_colors else None

        return PointCloudData(points=points_ds, colors=colors_ds, num_points=len(points_ds), has_colors=self.has_colors)

    def remove_statistical_outliers(self, nb_neighbors: int = 20, std_ratio: float = 2.0) -> "PointCloudData":
        """Remove statistical outliers from point cloud.

        Args:
            nb_neighbors: Number of neighbors to consider
            std_ratio: Standard deviation ratio threshold

        Returns:
            New PointCloudData with outliers removed

        Raises:
            ImportError: If open3d is not installed
        """
        if importlib.util.find_spec("open3d") is None:
            raise ImportError("open3d package required for outlier removal. Install with: pip install open3d")

        pcd = self.to_open3d()
        pcd_clean, inlier_indices = pcd.remove_statistical_outlier(nb_neighbors=nb_neighbors, std_ratio=std_ratio)

        # Extract inlier points and colors
        inlier_mask = np.zeros(self.num_points, dtype=bool)
        inlier_mask[inlier_indices] = True

        points_clean = self.points[inlier_mask]
        colors_clean = self.colors[inlier_mask] if self.has_colors else None

        return PointCloudData(
            points=points_clean, colors=colors_clean, num_points=len(points_clean), has_colors=self.has_colors
        )

    def __repr__(self) -> str:
        """String representation of point cloud."""
        color_str = "with colors" if self.has_colors else "no colors"
        return f"PointCloudData(points={self.num_points}, {color_str})"
