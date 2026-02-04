import os
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from mindtrace.core.types.bounding_box import BoundingBox
from mindtrace.hardware.cameras.homography.calibrator import HomographyCalibrator
from mindtrace.hardware.cameras.homography.measurer import HomographyMeasurer
from mindtrace.hardware.core.exceptions import HardwareOperationError


class TestHomographyIntegration:
    """Integration tests that combine calibration and measurement workflows."""

    def setup_method(self):
        """Set up test fixtures."""
        self.calibrator = HomographyCalibrator()

    def test_full_workflow_synthetic_data(self):
        """Test complete workflow from calibration to measurement with synthetic data."""
        # Step 1: Create synthetic calibration data
        world_points = np.array(
            [
                [0.0, 0.0],  # Origin
                [100.0, 0.0],  # 100mm right
                [100.0, 50.0],  # 100mm right, 50mm up
                [0.0, 50.0],  # 50mm up
                [50.0, 25.0],  # Center point
            ],
            dtype=np.float64,
        )

        # Corresponding pixel coordinates (2x scale + offset)
        image_points = np.array(
            [
                [200.0, 300.0],  # (0,0) -> (200,300)
                [400.0, 300.0],  # (100,0) -> (400,300)
                [400.0, 400.0],  # (100,50) -> (400,400)
                [200.0, 400.0],  # (0,50) -> (200,400)
                [300.0, 350.0],  # (50,25) -> (300,350)
            ],
            dtype=np.float64,
        )

        # Step 2: Calibrate homography
        calibration_data = self.calibrator.calibrate_from_correspondences(
            world_points=world_points, image_points=image_points, world_unit="mm"
        )

        # Step 3: Create measurer
        measurer = HomographyMeasurer(calibration_data)

        # Step 4: Test measurement on a known bounding box
        # Box from (200,300) to (300,350) should map to (0,0) to (50,25) = 50x25mm
        test_bbox = BoundingBox(x=200, y=300, width=100, height=50)
        measured = measurer.measure_bounding_box(test_bbox)

        # Verify measurements (allowing for small numerical errors)
        assert abs(measured.width_world - 50.0) < 1.0, f"Expected width ~50mm, got {measured.width_world}"
        assert abs(measured.height_world - 25.0) < 1.0, f"Expected height ~25mm, got {measured.height_world}"
        assert abs(measured.area_world - 1250.0) < 50.0, f"Expected area ~1250mm², got {measured.area_world}"
        assert measured.unit == "mm"

    def test_workflow_with_unit_conversion(self):
        """Test workflow with unit conversion from calibration to measurement."""
        # Calibrate in millimeters
        world_points = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]], dtype=np.float64)

        image_points = np.array([[100.0, 100.0], [200.0, 100.0], [200.0, 200.0], [100.0, 200.0]], dtype=np.float64)

        calibration_data = self.calibrator.calibrate_from_correspondences(
            world_points=world_points, image_points=image_points, world_unit="mm"
        )

        measurer = HomographyMeasurer(calibration_data)

        # Measure in centimeters
        bbox = BoundingBox(x=100, y=100, width=100, height=100)  # Should be 10x10mm
        measured = measurer.measure_bounding_box(bbox, target_unit="cm")

        assert abs(measured.width_world - 1.0) < 0.1  # 10mm = 1cm
        assert abs(measured.height_world - 1.0) < 0.1
        assert measured.unit == "cm"

    def test_workflow_with_camera_intrinsics(self):
        """Test workflow including camera intrinsics and distortion correction."""
        # Create test data
        world_points = np.array([[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0]], dtype=np.float64)

        # Slightly distorted image points
        image_points = np.array([[150.0, 150.0], [250.0, 152.0], [248.0, 250.0], [152.0, 248.0]], dtype=np.float64)

        # Camera parameters
        camera_matrix = np.array([[800, 0, 320], [0, 800, 240], [0, 0, 1]], dtype=np.float64)
        dist_coeffs = np.array([0.05, -0.02, 0.001, 0.001], dtype=np.float64)

        # Calibrate with camera parameters
        calibration_data = self.calibrator.calibrate_from_correspondences(
            world_points=world_points,
            image_points=image_points,
            world_unit="mm",
            camera_matrix=camera_matrix,
            dist_coeffs=dist_coeffs,
        )

        # Verify camera parameters are preserved
        assert np.array_equal(calibration_data.camera_matrix, camera_matrix)
        assert np.array_equal(calibration_data.dist_coeffs, dist_coeffs)

        # Create measurer and test
        measurer = HomographyMeasurer(calibration_data)
        bbox = BoundingBox(x=150, y=150, width=100, height=100)
        measured = measurer.measure_bounding_box(bbox)

        # Should produce reasonable measurements
        assert measured.width_world > 0
        assert measured.height_world > 0
        assert measured.unit == "mm"

    def test_multiple_objects_workflow(self):
        """Test workflow measuring multiple objects after single calibration."""
        # Simple 1:1 pixel to mm mapping for easy verification
        world_points = np.array([[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]], dtype=np.float64)

        image_points = np.array([[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]], dtype=np.float64)

        calibration_data = self.calibrator.calibrate_from_correspondences(
            world_points=world_points, image_points=image_points, world_unit="mm"
        )

        measurer = HomographyMeasurer(calibration_data)

        # Create multiple test objects
        objects = [
            BoundingBox(x=10, y=10, width=20, height=30),  # 20x30mm
            BoundingBox(x=50, y=20, width=15, height=15),  # 15x15mm
            BoundingBox(x=80, y=60, width=10, height=25),  # 10x25mm
        ]

        measurements = measurer.measure_bounding_boxes(objects)

        assert len(measurements) == 3

        # Check approximate measurements (allowing for homography estimation errors)
        assert abs(measurements[0].width_world - 20.0) < 5.0
        assert abs(measurements[0].height_world - 30.0) < 5.0

        assert abs(measurements[1].width_world - 15.0) < 5.0
        assert abs(measurements[1].height_world - 15.0) < 5.0

        assert abs(measurements[2].width_world - 10.0) < 5.0
        assert abs(measurements[2].height_world - 25.0) < 5.0

    @patch("cv2.findChessboardCorners")
    @patch("cv2.cornerSubPix")
    def test_checkerboard_to_measurement_workflow(self, mock_refine, mock_find):
        """Test complete workflow from checkerboard calibration to measurement."""
        # Mock checkerboard detection
        corners = np.array(
            [
                [[100, 100]],
                [[150, 100]],
                [[200, 100]],
                [[100, 150]],
                [[150, 150]],
                [[200, 150]],
                [[100, 200]],
                [[150, 200]],
                [[200, 200]],
            ],
            dtype=np.float32,
        )

        mock_find.return_value = (True, corners)
        mock_refine.return_value = corners

        # Create dummy image
        image = np.zeros((400, 300, 3), dtype=np.uint8)

        # Calibrate using checkerboard
        calibration_data = self.calibrator.calibrate_checkerboard(
            image=image,
            board_size=(3, 3),  # 3x3 inner corners
            square_size=25.0,  # 25mm squares
            world_unit="mm",
            refine_corners=True,
        )

        # Create measurer and test measurement
        measurer = HomographyMeasurer(calibration_data)
        bbox = BoundingBox(x=100, y=100, width=50, height=50)
        measured = measurer.measure_bounding_box(bbox)

        # Should produce valid measurements
        assert measured.width_world > 0
        assert measured.height_world > 0
        assert measured.area_world > 0
        assert measured.unit == "mm"

    def test_real_checkerboard_workflow(self):
        """Test workflow with real checkerboard image if available."""
        image_path = "tests/resources/checkerboard.jpg"
        if not os.path.exists(image_path):
            pytest.skip("Checkerboard image not found")

        image = cv2.imread(image_path)
        if image is None:
            pytest.skip("Could not load checkerboard image")

        # Try to calibrate with the real checkerboard
        board_sizes_to_try = [(12, 12), (11, 11), (10, 10), (9, 6), (8, 8)]
        calibration_data = None

        for board_size in board_sizes_to_try:
            try:
                calibration_data = self.calibrator.calibrate_checkerboard(
                    image=image,
                    board_size=board_size,
                    square_size=25.0,  # Assume 25mm squares
                    world_unit="mm",
                    refine_corners=True,
                )
                break
            except ValueError:
                continue

        if calibration_data is None:
            pytest.skip("Could not detect checkerboard with any tested size")

        # Test measurement with the real calibration
        measurer = HomographyMeasurer(calibration_data)

        # Create a test bounding box
        bbox = BoundingBox(x=100, y=100, width=200, height=150)
        measured = measurer.measure_bounding_box(bbox)

        # Should produce reasonable measurements
        assert measured.width_world > 0
        assert measured.height_world > 0
        assert measured.area_world > 0
        assert measured.unit == "mm"

        # Test with unit conversion
        measured_cm = measurer.measure_bounding_box(bbox, target_unit="cm")
        assert measured_cm.unit == "cm"
        assert abs(measured_cm.width_world * 10 - measured.width_world) < 0.1

    def test_error_propagation(self):
        """Test how errors propagate from calibration to measurement."""
        # Test with degenerate calibration data (collinear points)
        world_points = np.array(
            [
                [0.0, 0.0],
                [1.0, 0.0],
                [2.0, 0.0],
                [3.0, 0.0],  # All on same line
            ],
            dtype=np.float64,
        )

        image_points = np.array([[0.0, 0.0], [100.0, 0.0], [200.0, 0.0], [300.0, 0.0]], dtype=np.float64)

        # This might fail during calibration or produce poor results
        try:
            calibration_data = self.calibrator.calibrate_from_correspondences(
                world_points=world_points, image_points=image_points, world_unit="mm"
            )

            # If calibration succeeds, measurement should still work
            measurer = HomographyMeasurer(calibration_data)
            bbox = BoundingBox(x=50, y=50, width=100, height=100)
            measured = measurer.measure_bounding_box(bbox)

            # Results might be poor, but should be valid numbers
            assert not np.isnan(measured.width_world)
            assert not np.isnan(measured.height_world)
            assert not np.isnan(measured.area_world)

        except HardwareOperationError:
            # Expected for degenerate cases
            pass

    def test_precision_and_accuracy(self):
        """Test precision and accuracy of the complete workflow."""
        # Create precise synthetic data
        world_points = np.array([[0.0, 0.0], [50.0, 0.0], [50.0, 30.0], [0.0, 30.0]], dtype=np.float64)

        # Perfect 2x scaling
        image_points = np.array([[100.0, 200.0], [200.0, 200.0], [200.0, 260.0], [100.0, 260.0]], dtype=np.float64)

        calibration_data = self.calibrator.calibrate_from_correspondences(
            world_points=world_points, image_points=image_points, world_unit="mm"
        )

        measurer = HomographyMeasurer(calibration_data)

        # Test measurement precision
        bbox = BoundingBox(x=100, y=200, width=100, height=60)  # Should be 50x30mm
        measured = measurer.measure_bounding_box(bbox)

        # With perfect synthetic data, should be very accurate
        assert abs(measured.width_world - 50.0) < 0.1
        assert abs(measured.height_world - 30.0) < 0.1
        assert abs(measured.area_world - 1500.0) < 10.0

    def test_workflow_robustness(self):
        """Test workflow robustness with noisy data."""
        # Add small amounts of noise to test robustness
        np.random.seed(42)  # For reproducible results

        world_points = np.array(
            [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0], [50.0, 50.0]], dtype=np.float64
        )

        # Add small noise to image points
        image_points = np.array(
            [[200.0, 200.0], [400.0, 200.0], [400.0, 400.0], [200.0, 400.0], [300.0, 300.0]], dtype=np.float64
        )

        noise = np.random.normal(0, 0.5, image_points.shape)  # Small pixel noise
        image_points += noise

        calibration_data = self.calibrator.calibrate_from_correspondences(
            world_points=world_points, image_points=image_points, world_unit="mm"
        )

        measurer = HomographyMeasurer(calibration_data)
        bbox = BoundingBox(x=200, y=200, width=200, height=200)  # Should be ~100x100mm
        measured = measurer.measure_bounding_box(bbox)

        # Should still be reasonably accurate despite noise
        assert abs(measured.width_world - 100.0) < 10.0
        assert abs(measured.height_world - 100.0) < 10.0
        assert measured.unit == "mm"
