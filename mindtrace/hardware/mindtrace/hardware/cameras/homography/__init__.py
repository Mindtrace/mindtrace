"""Homography-based planar measurement system.

This module provides homography calibration and measurement capabilities for
converting pixel-space object detections to real-world metric dimensions on
planar surfaces.

Features:
    - Automatic checkerboard calibration
    - Manual point correspondence calibration
    - RANSAC-based robust homography estimation
    - Multi-unit measurement support (mm, cm, m, in, ft)
    - Batch processing for multiple objects
    - Framework-integrated logging and configuration

Typical Usage::

    from mindtrace.hardware import HomographyCalibrator, HomographyMeasurer

    # One-time calibration
    calibrator = HomographyCalibrator()
    calibration = calibrator.calibrate_checkerboard(
        image=checkerboard_image,
        board_size=(12, 12),
        square_size=25.0,
        world_unit="mm"
    )
    calibration.save("camera_calibration.json")

    # Repeated measurement
    measurer = HomographyMeasurer(calibration)
    detections = yolo.detect(frame)
    measurements = measurer.measure_bounding_boxes(detections, target_unit="cm")

    for measured in measurements:
        print(f"Size: {measured.width_world:.1f} × {measured.height_world:.1f} cm")
"""

from mindtrace.hardware.cameras.homography.calibrator import HomographyCalibrator
from mindtrace.hardware.cameras.homography.data import CalibrationData, MeasuredBox
from mindtrace.hardware.cameras.homography.measurer import HomographyMeasurer

# Backward compatibility aliases
PlanarHomographyMeasurer = HomographyMeasurer

__all__ = [
    "HomographyCalibrator",
    "HomographyMeasurer",
    "CalibrationData",
    "MeasuredBox",
    # Backward compatibility
    "PlanarHomographyMeasurer",
]
