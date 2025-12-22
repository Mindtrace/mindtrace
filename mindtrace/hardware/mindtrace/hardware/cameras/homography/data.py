"""Data structures for homography calibration and measurement.

This module defines immutable data containers for homography-based measurement operations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class CalibrationData:
    """Immutable container for homography calibration data.

    Holds the homography matrix and optional camera intrinsics derived or provided
    during calibration. The homography maps world plane coordinates (Z=0) in metric
    units to image pixel coordinates.

    Attributes:
        H: 3x3 homography matrix from world plane (Z=0) to image pixels
        camera_matrix: 3x3 camera intrinsics matrix (K) if known or estimated
        dist_coeffs: Lens distortion coefficients if available
        world_unit: Unit used for world coordinates (e.g., 'mm', 'cm', 'm', 'in', 'ft')
        plane_normal_camera: Optional 3D normal of the plane in camera frame if recovered
    """

    H: np.ndarray
    camera_matrix: Optional[np.ndarray] = None
    dist_coeffs: Optional[np.ndarray] = None
    world_unit: str = "mm"
    plane_normal_camera: Optional[np.ndarray] = None

    def save(self, filepath: str) -> None:
        """Save calibration data to JSON file.

        Args:
            filepath: Path to save the calibration data

        Note:
            NumPy arrays are converted to lists for JSON serialization.
        """
        data = {
            "H": self.H.tolist(),
            "world_unit": self.world_unit,
        }

        if self.camera_matrix is not None:
            data["camera_matrix"] = self.camera_matrix.tolist()

        if self.dist_coeffs is not None:
            data["dist_coeffs"] = self.dist_coeffs.tolist()

        if self.plane_normal_camera is not None:
            data["plane_normal_camera"] = self.plane_normal_camera.tolist()

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> CalibrationData:
        """Load calibration data from JSON file.

        Args:
            filepath: Path to the calibration data file

        Returns:
            CalibrationData instance loaded from file

        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file format is invalid
        """
        with open(filepath, "r") as f:
            data = json.load(f)

        H = np.array(data["H"], dtype=np.float64)

        camera_matrix = None
        if "camera_matrix" in data:
            camera_matrix = np.array(data["camera_matrix"], dtype=np.float64)

        dist_coeffs = None
        if "dist_coeffs" in data:
            dist_coeffs = np.array(data["dist_coeffs"], dtype=np.float64)

        plane_normal_camera = None
        if "plane_normal_camera" in data:
            plane_normal_camera = np.array(data["plane_normal_camera"], dtype=np.float64)

        return cls(
            H=H,
            camera_matrix=camera_matrix,
            dist_coeffs=dist_coeffs,
            world_unit=data.get("world_unit", "mm"),
            plane_normal_camera=plane_normal_camera,
        )


@dataclass(frozen=True)
class MeasuredBox:
    """Immutable container for metric-space measurement of a bounding box.

    Stores the result of projecting a pixel-space bounding box to world coordinates
    on a planar surface using homography inversion. Contains the projected corner
    points and computed physical dimensions.

    Attributes:
        corners_world: 4x2 array of corner coordinates in world units (top-left, top-right, bottom-right, bottom-left)
        width_world: Width in world units (distance between top-left and top-right)
        height_world: Height in world units (distance between top-left and bottom-left)
        area_world: Area in square world units (computed via shoelace formula)
        unit: Unit of measurement (e.g., 'mm', 'cm', 'm', 'in', 'ft')
    """

    corners_world: np.ndarray
    width_world: float
    height_world: float
    area_world: float
    unit: str

    def to_dict(self) -> dict:
        """Convert measurement to dictionary.

        Returns:
            Dictionary representation with corners as list
        """
        return {
            "corners_world": self.corners_world.tolist(),
            "width_world": self.width_world,
            "height_world": self.height_world,
            "area_world": self.area_world,
            "unit": self.unit,
        }
