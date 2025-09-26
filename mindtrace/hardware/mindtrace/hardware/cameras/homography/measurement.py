from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from mindtrace.core.types.bounding_box import BoundingBox
from mindtrace.hardware.cameras.homography.calibration import CalibrationData


@dataclass
class MeasuredBox:
    """Metric-space measurement of a box on the plane after homography inversion.

    Stores the projected polygon points and size in world units.
    """

    corners_world: np.ndarray
    width_world: float
    height_world: float
    area_world: float
    unit: str


class PlanarHomographyMeasurer:
    """A class for measuring the size of a box on a plane after homography inversion.

    Uses a planar homography calibration to project pixel points back to world plane coordinates and compute metric
    distances.
    """

    _UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}

    def __init__(self, calibration: CalibrationData):
        """Initialize the measurer.

        Args:
            calibration: The calibration data.
        """
        self.calibration = calibration
        if self.calibration.H.shape != (3, 3):
            raise ValueError("CalibrationData.H must be 3x3")
        # Precompute inverse for speed
        self._H_inv = np.linalg.inv(self.calibration.H)

    @classmethod
    def _unit_scale(cls, from_unit: str, to_unit: str) -> float:
        """Convert units to millimeters.

        Args:
            from_unit: The unit to convert from.
            to_unit: The unit to convert to.

        Returns:
            The scale factor.
        """
        if from_unit not in cls._UNIT_TO_MM or to_unit not in cls._UNIT_TO_MM:
            raise ValueError("Units must be one of {'mm','cm','m','in','ft'}")
        return cls._UNIT_TO_MM[from_unit] / cls._UNIT_TO_MM[to_unit]

    def pixels_to_world(self, points_px: np.ndarray) -> np.ndarray:
        """Map Nx2 pixel coordinates to world plane coordinates using H^{-1}.

        Returns:
            Nx2 world coordinates in calibration world unit.
        """
        pts = np.asarray(points_px, dtype=np.float64)
        if pts.ndim != 2 or pts.shape[1] != 2:
            raise ValueError("points_px must be Nx2")
        ones = np.ones((pts.shape[0], 1), dtype=np.float64)
        pts_h = np.hstack([pts, ones])
        mapped = (self._H_inv @ pts_h.T).T
        mapped /= mapped[:, [2]]
        return mapped[:, :2]

    def measure_bounding_box(self, box: BoundingBox, target_unit: Optional[str] = None) -> MeasuredBox:
        """Measure the size of a bounding box on the plane after homography inversion.

        Args:
            box: The bounding box to measure.
            target_unit: The unit to convert the measurements to.

        Returns:
            The measured box.
        """
        corners_px = np.array(box.to_corners(), dtype=np.float64)
        corners_world = self.pixels_to_world(corners_px)
        # Width: distance between top-right and top-left; Height: distance between top-left and bottom-left
        width_world = float(np.linalg.norm(corners_world[1] - corners_world[0]))
        height_world = float(np.linalg.norm(corners_world[3] - corners_world[0]))
        # Polygon area via shoelace formula
        x = corners_world[:, 0]
        y = corners_world[:, 1]
        area_world = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
        unit = self.calibration.world_unit
        if target_unit and target_unit != unit:
            s = self._unit_scale(unit, target_unit)
            corners_world = corners_world * s
            width_world *= s
            height_world *= s
            area_world *= s * s
            unit = target_unit
        return MeasuredBox(
            corners_world=corners_world,
            width_world=width_world,
            height_world=height_world,
            area_world=area_world,
            unit=unit,
        )

    def measure_bounding_boxes(
        self, boxes: Sequence[BoundingBox], target_unit: Optional[str] = None
    ) -> List[MeasuredBox]:
        """Measure the size of a list of bounding boxes on the plane after homography inversion.

        Args:
            boxes: The list of bounding boxes to measure.
            target_unit: The unit to convert the measurements to.

        Returns:
            The list of measured boxes.
        """
        return [self.measure_bounding_box(b, target_unit=target_unit) for b in boxes]
