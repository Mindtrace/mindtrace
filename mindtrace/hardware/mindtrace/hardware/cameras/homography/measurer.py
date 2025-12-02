"""Homography-based measurement for planar objects.

This module provides measurement operations that project pixel-space bounding boxes
to real-world metric coordinates using calibrated homography transformations.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple, Union

import numpy as np

from mindtrace.core import Mindtrace
from mindtrace.core.types.bounding_box import BoundingBox
from mindtrace.hardware.cameras.homography.data import CalibrationData, MeasuredBox
from mindtrace.hardware.core.config import get_hardware_config
from mindtrace.hardware.core.exceptions import CameraConfigurationError


class HomographyMeasurer(Mindtrace):
    """Measures physical dimensions of objects using planar homography.

    Projects pixel-space bounding boxes from object detection to real-world metric
    coordinates on a planar surface using a pre-calibrated homography matrix. Enables
    accurate physical size measurements from camera images.

    The measurer uses the inverse homography (H⁻¹) to map image pixels back to world
    coordinates, then computes Euclidean distances and polygon areas for size measurements.

    Features:
        - Pixel-to-world coordinate projection
        - Bounding box dimension measurement (width, height, area)
        - Multi-unit support with automatic conversion
        - Batch processing for multiple detections
        - Pre-computed inverse homography for performance

    Typical Workflow:
        1. Calibrate camera view to obtain HomographyCalibrator.calibrate_*()
        2. Create measurer with calibration data
        3. Detect objects with vision model (YOLO, etc.)
        4. Measure physical dimensions from bounding boxes
        5. Apply size-based filtering or quality control

    Usage::

        from mindtrace.hardware import HomographyCalibrator, HomographyMeasurer
        from mindtrace.core.types import BoundingBox

        # One-time calibration
        calibrator = HomographyCalibrator()
        calibration = calibrator.calibrate_checkerboard(
            image=checkerboard_image,
            board_size=(12, 12),
            square_size=25.0,
            world_unit="mm"
        )

        # Create measurer (reuse for all measurements)
        measurer = HomographyMeasurer(calibration)

        # Measure objects from detection results
        detections = yolo.detect(frame)  # List[BoundingBox]
        measurements = measurer.measure_bounding_boxes(detections, target_unit="cm")

        for measured in measurements:
            print(f"Width: {measured.width_world:.2f} cm")
            print(f"Height: {measured.height_world:.2f} cm")
            print(f"Area: {measured.area_world:.2f} cm²")

            # Size-based filtering
            if measured.width_world > 10.0:
                reject_oversized_part(measured)

    Configuration:
        - Supported units: mm, cm, m, in, ft (configurable via hardware config)
        - Default world unit: Inherited from calibration data

    Limitations:
        - Only works for planar surfaces (Z=0 assumption)
        - Accuracy depends on calibration quality and viewing angle
        - Assumes objects lie flat on the calibrated plane
        - Camera must remain fixed after calibration
    """

    # Unit conversion factors (all relative to millimeters)
    _UNIT_TO_MM = {
        "mm": 1.0,
        "cm": 10.0,
        "m": 1000.0,
        "in": 25.4,
        "ft": 304.8,
    }

    def __init__(self, calibration: CalibrationData, **kwargs):
        """Initialize homography measurer with calibration data.

        Args:
            calibration: CalibrationData from HomographyCalibrator
            **kwargs: Additional arguments passed to Mindtrace base class

        Raises:
            CameraConfigurationError: If homography matrix is invalid
        """
        super().__init__(**kwargs)

        # Validate calibration data
        if calibration.H.shape != (3, 3):
            raise CameraConfigurationError(f"Invalid homography matrix shape: {calibration.H.shape}. Expected (3, 3)")

        self.calibration = calibration

        # Precompute inverse homography for efficient repeated measurements
        try:
            self._H_inv = np.linalg.inv(self.calibration.H)
        except np.linalg.LinAlgError as e:
            raise CameraConfigurationError(f"Homography matrix is singular and cannot be inverted: {e}")

        # Load configuration
        hw_config = get_hardware_config().get_config()
        self._config = hw_config.homography

        self.logger.info(
            f"HomographyMeasurer initialized "
            f"(calibration_unit={self.calibration.world_unit}, "
            f"supported_units={self._config.supported_units})"
        )

    @classmethod
    def _unit_scale(cls, from_unit: str, to_unit: str) -> float:
        """Calculate scaling factor for unit conversion.

        Args:
            from_unit: Source unit (e.g., 'mm', 'cm')
            to_unit: Target unit (e.g., 'cm', 'm')

        Returns:
            Scaling factor to multiply measurements by

        Raises:
            CameraConfigurationError: If unit is not supported

        Example::

            scale = HomographyMeasurer._unit_scale('mm', 'cm')  # Returns 0.1
        """
        if from_unit not in cls._UNIT_TO_MM or to_unit not in cls._UNIT_TO_MM:
            raise CameraConfigurationError(
                f"Unsupported unit. Got '{from_unit}' or '{to_unit}', expected one of: {list(cls._UNIT_TO_MM.keys())}"
            )
        return cls._UNIT_TO_MM[from_unit] / cls._UNIT_TO_MM[to_unit]

    def pixels_to_world(self, points_px: np.ndarray) -> np.ndarray:
        """Project pixel coordinates to world plane coordinates.

        Maps Nx2 pixel coordinates to world plane coordinates using the inverse
        homography matrix H⁻¹. This is the core projection operation for all
        measurement functionality.

        Args:
            points_px: Nx2 array of pixel coordinates (u, v)

        Returns:
            Nx2 array of world coordinates (X, Y) in calibration world unit

        Raises:
            CameraConfigurationError: If input array has wrong shape

        Example::

            # Project single point
            world_point = measurer.pixels_to_world(np.array([[320, 240]]))

            # Project multiple points
            pixel_corners = np.array([[100, 50], [500, 50], [500, 400], [100, 400]])
            world_corners = measurer.pixels_to_world(pixel_corners)
        """
        pts = np.asarray(points_px, dtype=np.float64)

        if pts.ndim != 2 or pts.shape[1] != 2:
            raise CameraConfigurationError(f"points_px must be Nx2 array, got shape {pts.shape}")

        # Convert to homogeneous coordinates
        ones = np.ones((pts.shape[0], 1), dtype=np.float64)
        pts_h = np.hstack([pts, ones])

        # Apply inverse homography
        mapped = (self._H_inv @ pts_h.T).T

        # Normalize homogeneous coordinates
        mapped /= mapped[:, [2]]

        self.logger.debug(f"Projected {pts.shape[0]} pixel points to world coordinates")

        return mapped[:, :2]

    def measure_bounding_box(self, box: BoundingBox, target_unit: Optional[str] = None) -> MeasuredBox:
        """Measure physical dimensions of a bounding box on the calibrated plane.

        Projects the four corners of a pixel-space bounding box to world coordinates,
        then computes width, height, and area in the specified unit.

        Args:
            box: BoundingBox from object detection (x, y, width, height in pixels)
            target_unit: Unit for output measurements (e.g., 'cm', 'm').
                        Uses calibration unit if None.

        Returns:
            MeasuredBox with physical dimensions and corner coordinates

        Example::

            # From object detection
            detection = BoundingBox(x=100, y=50, width=400, height=350)
            measured = measurer.measure_bounding_box(detection, target_unit="cm")

            print(f"Object is {measured.width_world:.1f} × {measured.height_world:.1f} cm")
            print(f"Area: {measured.area_world:.1f} cm²")
        """
        # Convert bounding box to corner coordinates
        corners_px = np.array(box.to_corners(), dtype=np.float64)

        # Project to world coordinates
        corners_world = self.pixels_to_world(corners_px)

        # Compute dimensions from projected corners
        # Width: distance between top-right and top-left
        # Height: distance between top-left and bottom-left
        width_world = float(np.linalg.norm(corners_world[1] - corners_world[0]))
        height_world = float(np.linalg.norm(corners_world[3] - corners_world[0]))

        # Compute area using shoelace formula for polygon area
        # This accounts for perspective distortion better than width * height
        x = corners_world[:, 0]
        y = corners_world[:, 1]
        area_world = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

        unit = self.calibration.world_unit

        # Apply unit conversion if requested
        if target_unit and target_unit != unit:
            scale = self._unit_scale(unit, target_unit)
            corners_world = corners_world * scale
            width_world *= scale
            height_world *= scale
            area_world *= scale * scale
            unit = target_unit

        self.logger.debug(
            f"Measured box: {width_world:.2f} × {height_world:.2f} {unit} (area={area_world:.2f} {unit}²)"
        )

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
        """Measure physical dimensions of multiple bounding boxes.

        Batch processing of multiple object detections. More efficient than
        calling measure_bounding_box() in a loop.

        Args:
            boxes: Sequence of BoundingBox objects from object detection
            target_unit: Unit for output measurements. Uses calibration unit if None.

        Returns:
            List of MeasuredBox objects with physical dimensions

        Example::

            # Batch measurement from multiple detections
            detections = yolo.detect(frame)  # List[BoundingBox]
            measurements = measurer.measure_bounding_boxes(detections, target_unit="cm")

            # Size-based filtering
            large_objects = [m for m in measurements if m.width_world > 15.0]

            # Quality control
            for measured in measurements:
                if not (10.0 <= measured.width_world <= 20.0):
                    reject_part(measured)
        """
        self.logger.debug(f"Batch measuring {len(boxes)} bounding boxes (target_unit={target_unit})")

        measurements = [self.measure_bounding_box(box, target_unit=target_unit) for box in boxes]

        self.logger.info(f"Completed batch measurement of {len(measurements)} objects")

        return measurements

    def measure_distance(
        self,
        point1: Union[Tuple[float, float], np.ndarray],
        point2: Union[Tuple[float, float], np.ndarray],
        target_unit: Optional[str] = None,
    ) -> Tuple[float, str]:
        """Measure Euclidean distance between two points on the calibrated plane.

        Converts pixel coordinates to world coordinates and computes the distance.
        Useful for measuring gaps, spacing, or verifying known distances.

        Args:
            point1: First point as (x, y) pixel coordinates
            point2: Second point as (x, y) pixel coordinates
            target_unit: Unit for output distance. Uses calibration unit if None.

        Returns:
            Tuple of (distance, unit)

        Raises:
            ValueError: If target_unit is not supported

        Example::

            # Measure distance between two detected points
            point1 = (150, 200)  # pixels
            point2 = (350, 200)  # pixels
            distance, unit = measurer.measure_distance(point1, point2, target_unit="mm")
            print(f"Distance: {distance:.2f} {unit}")

            # Verify calibration accuracy
            known_distance_mm = 100.0
            measured_distance, _ = measurer.measure_distance(ref_point1, ref_point2, "mm")
            error_percent = abs(measured_distance - known_distance_mm) / known_distance_mm * 100
            print(f"Calibration error: {error_percent:.2f}%")
        """
        # Convert inputs to numpy array
        points_px = np.array([point1, point2], dtype=np.float64)

        # Validate points
        if points_px.shape != (2, 2):
            raise ValueError("Points must be (x, y) coordinates")

        # Project to world coordinates
        points_world = self.pixels_to_world(points_px)

        # Calculate Euclidean distance
        distance = float(np.linalg.norm(points_world[1] - points_world[0]))

        unit = self.calibration.world_unit

        # Apply unit conversion if requested
        if target_unit and target_unit != unit:
            scale = self._unit_scale(unit, target_unit)
            distance *= scale
            unit = target_unit

        self.logger.debug(f"Measured distance: {distance:.2f} {unit} (from {point1} to {point2} pixels)")

        return distance, unit
