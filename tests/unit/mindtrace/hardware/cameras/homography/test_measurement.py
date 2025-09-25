from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from mindtrace.core.types.bounding_box import BoundingBox
from mindtrace.hardware.cameras.homography.calibration import CalibrationData
from mindtrace.hardware.cameras.homography.measurement import PlanarHomographyMeasurer, MeasuredBox


class TestMeasuredBox:
    """Test the MeasuredBox dataclass."""

    def test_measured_box_creation(self):
        """Test basic MeasuredBox creation and properties."""
        corners = np.array([[0, 0], [10, 0], [10, 5], [0, 5]], dtype=np.float64)
        
        measured_box = MeasuredBox(
            corners_world=corners,
            width_world=10.0,
            height_world=5.0,
            area_world=50.0,
            unit="mm"
        )
        
        assert np.array_equal(measured_box.corners_world, corners)
        assert measured_box.width_world == 10.0
        assert measured_box.height_world == 5.0
        assert measured_box.area_world == 50.0
        assert measured_box.unit == "mm"

    def test_measured_box_different_units(self):
        """Test MeasuredBox with different units."""
        corners = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
        
        for unit in ["mm", "cm", "m", "in", "ft"]:
            measured_box = MeasuredBox(
                corners_world=corners,
                width_world=1.0,
                height_world=1.0,
                area_world=1.0,
                unit=unit
            )
            assert measured_box.unit == unit


class TestPlanarHomographyMeasurer:
    """Test the PlanarHomographyMeasurer class."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create a simple identity-like homography for testing
        # This maps world coordinates (in mm) to pixel coordinates with 2:1 scaling
        self.H = np.array([
            [2.0, 0.0, 100.0],  # x_pixel = 2*x_world + 100
            [0.0, 2.0, 50.0],   # y_pixel = 2*y_world + 50
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)
        
        self.calibration_data = CalibrationData(
            H=self.H,
            world_unit="mm"
        )
        
        self.measurer = PlanarHomographyMeasurer(self.calibration_data)

    def test_measurer_creation(self):
        """Test PlanarHomographyMeasurer instantiation."""
        assert self.measurer is not None
        assert np.array_equal(self.measurer.calibration.H, self.H)
        assert self.measurer.calibration.world_unit == "mm"

    def test_measurer_invalid_homography_shape(self):
        """Test error handling for invalid homography matrix shape."""
        invalid_H = np.eye(2, dtype=np.float64)  # 2x2 instead of 3x3
        invalid_calib = CalibrationData(H=invalid_H)
        
        with pytest.raises(ValueError, match="CalibrationData.H must be 3x3"):
            PlanarHomographyMeasurer(invalid_calib)

    def test_unit_scale_conversion(self):
        """Test unit scaling conversion factors."""
        # Test all supported unit conversions
        assert PlanarHomographyMeasurer._unit_scale("mm", "mm") == 1.0
        assert PlanarHomographyMeasurer._unit_scale("mm", "cm") == 0.1
        assert PlanarHomographyMeasurer._unit_scale("mm", "m") == 0.001
        
        assert PlanarHomographyMeasurer._unit_scale("cm", "mm") == 10.0
        assert PlanarHomographyMeasurer._unit_scale("cm", "cm") == 1.0
        assert PlanarHomographyMeasurer._unit_scale("cm", "m") == 0.01
        
        assert PlanarHomographyMeasurer._unit_scale("m", "mm") == 1000.0
        assert PlanarHomographyMeasurer._unit_scale("m", "cm") == 100.0
        assert PlanarHomographyMeasurer._unit_scale("m", "m") == 1.0
        
        # Test inches conversions
        assert abs(PlanarHomographyMeasurer._unit_scale("mm", "in") - (1.0 / 25.4)) < 1e-10
        assert abs(PlanarHomographyMeasurer._unit_scale("in", "mm") - 25.4) < 1e-10
        assert abs(PlanarHomographyMeasurer._unit_scale("in", "in") - 1.0) < 1e-10
        assert abs(PlanarHomographyMeasurer._unit_scale("in", "cm") - 2.54) < 1e-10
        assert abs(PlanarHomographyMeasurer._unit_scale("cm", "in") - (1.0 / 2.54)) < 1e-10
        
        # Test feet conversions
        assert abs(PlanarHomographyMeasurer._unit_scale("mm", "ft") - (1.0 / 304.8)) < 1e-10
        assert abs(PlanarHomographyMeasurer._unit_scale("ft", "mm") - 304.8) < 1e-10
        assert abs(PlanarHomographyMeasurer._unit_scale("ft", "ft") - 1.0) < 1e-10
        assert abs(PlanarHomographyMeasurer._unit_scale("ft", "in") - 12.0) < 1e-10
        assert abs(PlanarHomographyMeasurer._unit_scale("in", "ft") - (1.0 / 12.0)) < 1e-10

    def test_unit_scale_invalid_units(self):
        """Test error handling for invalid units."""
        with pytest.raises(ValueError, match="Units must be one of"):
            PlanarHomographyMeasurer._unit_scale("mm", "inches")  # Should be "in", not "inches"
        
        with pytest.raises(ValueError, match="Units must be one of"):
            PlanarHomographyMeasurer._unit_scale("feet", "mm")    # Should be "ft", not "feet"
        
        with pytest.raises(ValueError, match="Units must be one of"):
            PlanarHomographyMeasurer._unit_scale("mm", "yards")   # Unsupported unit

    def test_pixels_to_world_basic(self):
        """Test basic pixel to world coordinate conversion."""
        # Test points that should map cleanly with our test homography
        pixel_points = np.array([
            [100.0, 50.0],   # Should map to (0, 0) in world
            [200.0, 150.0],  # Should map to (50, 50) in world
            [120.0, 70.0]    # Should map to (10, 10) in world
        ], dtype=np.float64)
        
        world_points = self.measurer.pixels_to_world(pixel_points)
        
        assert world_points.shape == (3, 2)
        
        # Check approximate mappings (allowing for small numerical errors)
        np.testing.assert_allclose(world_points[0], [0.0, 0.0], atol=1e-10)
        np.testing.assert_allclose(world_points[1], [50.0, 50.0], atol=1e-10)
        np.testing.assert_allclose(world_points[2], [10.0, 10.0], atol=1e-10)

    def test_pixels_to_world_single_point(self):
        """Test pixel to world conversion with a single point."""
        pixel_point = np.array([[100.0, 50.0]], dtype=np.float64)
        world_point = self.measurer.pixels_to_world(pixel_point)
        
        assert world_point.shape == (1, 2)
        np.testing.assert_allclose(world_point[0], [0.0, 0.0], atol=1e-10)

    def test_pixels_to_world_errors(self):
        """Test error handling in pixel to world conversion."""
        # Test wrong dimensionality
        with pytest.raises(ValueError, match="points_px must be Nx2"):
            self.measurer.pixels_to_world(np.array([100.0, 50.0]))  # 1D array
        
        with pytest.raises(ValueError, match="points_px must be Nx2"):
            self.measurer.pixels_to_world(np.array([[[100.0, 50.0]]]))  # 3D array
        
        with pytest.raises(ValueError, match="points_px must be Nx2"):
            self.measurer.pixels_to_world(np.array([[100.0, 50.0, 0.0]]))  # Nx3 array

    def test_measure_bounding_box_basic(self):
        """Test basic bounding box measurement."""
        # Create a bounding box in pixel coordinates
        # Box from (100,50) to (200,150) should map to (0,0) to (50,50) in world coordinates
        bbox = BoundingBox(x=100, y=50, width=100, height=100)
        
        measured = self.measurer.measure_bounding_box(bbox)
        
        assert isinstance(measured, MeasuredBox)
        assert measured.unit == "mm"
        
        # Check dimensions (should be 50x50 mm based on our homography)
        assert abs(measured.width_world - 50.0) < 1e-10
        assert abs(measured.height_world - 50.0) < 1e-10
        assert abs(measured.area_world - 2500.0) < 1e-6  # 50*50 = 2500
        
        # Check corner coordinates
        expected_corners = np.array([[0, 0], [50, 0], [50, 50], [0, 50]], dtype=np.float64)
        np.testing.assert_allclose(measured.corners_world, expected_corners, atol=1e-10)

    def test_measure_bounding_box_with_unit_conversion(self):
        """Test bounding box measurement with unit conversion."""
        bbox = BoundingBox(x=100, y=50, width=100, height=100)
        
        # Measure in centimeters (should convert from mm)
        measured = self.measurer.measure_bounding_box(bbox, target_unit="cm")
        
        assert measured.unit == "cm"
        assert abs(measured.width_world - 5.0) < 1e-10  # 50mm = 5cm
        assert abs(measured.height_world - 5.0) < 1e-10
        assert abs(measured.area_world - 25.0) < 1e-6   # 5*5 = 25 cm²

    def test_measure_bounding_box_different_shapes(self):
        """Test measuring bounding boxes of different shapes."""
        # Rectangular box (2:1 aspect ratio in pixels)
        bbox = BoundingBox(x=100, y=50, width=200, height=100)
        measured = self.measurer.measure_bounding_box(bbox)
        
        # Should be 100x50 mm in world coordinates
        assert abs(measured.width_world - 100.0) < 1e-10
        assert abs(measured.height_world - 50.0) < 1e-10
        assert abs(measured.area_world - 5000.0) < 1e-6

    def test_measure_bounding_box_small_box(self):
        """Test measuring a very small bounding box."""
        bbox = BoundingBox(x=100, y=50, width=10, height=10)
        measured = self.measurer.measure_bounding_box(bbox)
        
        # Should be 5x5 mm in world coordinates
        assert abs(measured.width_world - 5.0) < 1e-10
        assert abs(measured.height_world - 5.0) < 1e-10
        assert abs(measured.area_world - 25.0) < 1e-6

    def test_measure_bounding_boxes_multiple(self):
        """Test measuring multiple bounding boxes."""
        boxes = [
            BoundingBox(x=100, y=50, width=100, height=100),    # 50x50 mm
            BoundingBox(x=200, y=100, width=200, height=100),   # 100x50 mm
            BoundingBox(x=150, y=75, width=50, height=50)       # 25x25 mm
        ]
        
        measurements = self.measurer.measure_bounding_boxes(boxes)
        
        assert len(measurements) == 3
        
        # Check first box
        assert abs(measurements[0].width_world - 50.0) < 1e-10
        assert abs(measurements[0].height_world - 50.0) < 1e-10
        
        # Check second box
        assert abs(measurements[1].width_world - 100.0) < 1e-10
        assert abs(measurements[1].height_world - 50.0) < 1e-10
        
        # Check third box
        assert abs(measurements[2].width_world - 25.0) < 1e-10
        assert abs(measurements[2].height_world - 25.0) < 1e-10

    def test_measure_bounding_boxes_with_unit_conversion(self):
        """Test measuring multiple boxes with unit conversion."""
        boxes = [
            BoundingBox(x=100, y=50, width=100, height=100),
            BoundingBox(x=200, y=100, width=200, height=100)
        ]
        
        measurements = self.measurer.measure_bounding_boxes(boxes, target_unit="cm")
        
        assert len(measurements) == 2
        assert all(m.unit == "cm" for m in measurements)
        
        # Check converted values
        assert abs(measurements[0].width_world - 5.0) < 1e-10  # 50mm = 5cm
        assert abs(measurements[1].width_world - 10.0) < 1e-10 # 100mm = 10cm

    def test_measure_bounding_box_with_inches(self):
        """Test measuring bounding box with inch conversion."""
        bbox = BoundingBox(x=100, y=50, width=100, height=100)
        
        # Measure in inches (should convert from mm)
        measured = self.measurer.measure_bounding_box(bbox, target_unit="in")
        
        assert measured.unit == "in"
        # 50mm = ~1.968 inches (50 / 25.4)
        expected_width_in = 50.0 / 25.4
        expected_height_in = 50.0 / 25.4
        expected_area_in = (50.0 * 50.0) / (25.4 * 25.4)
        
        assert abs(measured.width_world - expected_width_in) < 1e-10
        assert abs(measured.height_world - expected_height_in) < 1e-10
        assert abs(measured.area_world - expected_area_in) < 1e-10

    def test_measure_bounding_box_with_feet(self):
        """Test measuring bounding box with feet conversion."""
        bbox = BoundingBox(x=100, y=50, width=100, height=100)
        
        # Measure in feet (should convert from mm)
        measured = self.measurer.measure_bounding_box(bbox, target_unit="ft")
        
        assert measured.unit == "ft"
        # 50mm = ~0.164 feet (50 / 304.8)
        expected_width_ft = 50.0 / 304.8
        expected_height_ft = 50.0 / 304.8
        expected_area_ft = (50.0 * 50.0) / (304.8 * 304.8)
        
        assert abs(measured.width_world - expected_width_ft) < 1e-10
        assert abs(measured.height_world - expected_height_ft) < 1e-10
        assert abs(measured.area_world - expected_area_ft) < 1e-10

    def test_measure_bounding_boxes_with_imperial_units(self):
        """Test measuring multiple boxes with imperial unit conversions."""
        boxes = [
            BoundingBox(x=100, y=50, width=100, height=100),  # 50x50 mm
            BoundingBox(x=200, y=100, width=200, height=100), # 100x50 mm
        ]
        
        # Test with inches
        measurements_in = self.measurer.measure_bounding_boxes(boxes, target_unit="in")
        
        assert len(measurements_in) == 2
        assert all(m.unit == "in" for m in measurements_in)
        
        # Check converted values
        assert abs(measurements_in[0].width_world - (50.0 / 25.4)) < 1e-10  # 50mm to inches
        assert abs(measurements_in[1].width_world - (100.0 / 25.4)) < 1e-10 # 100mm to inches
        
        # Test with feet
        measurements_ft = self.measurer.measure_bounding_boxes(boxes, target_unit="ft")
        
        assert len(measurements_ft) == 2
        assert all(m.unit == "ft" for m in measurements_ft)
        
        # Check converted values
        assert abs(measurements_ft[0].width_world - (50.0 / 304.8)) < 1e-10  # 50mm to feet
        assert abs(measurements_ft[1].width_world - (100.0 / 304.8)) < 1e-10 # 100mm to feet

    def test_measure_empty_bounding_box_list(self):
        """Test measuring an empty list of bounding boxes."""
        measurements = self.measurer.measure_bounding_boxes([])
        assert measurements == []

    def test_different_calibration_units(self):
        """Test measurer with different calibration units."""
        # Create calibration data with centimeters
        calib_cm = CalibrationData(H=self.H, world_unit="cm")
        measurer_cm = PlanarHomographyMeasurer(calib_cm)
        
        bbox = BoundingBox(x=100, y=50, width=100, height=100)
        measured = measurer_cm.measure_bounding_box(bbox)
        
        assert measured.unit == "cm"
        # Same homography matrix, but different unit interpretation
        # The measurement will be the same numerical value, just in different units
        assert abs(measured.width_world - 50.0) < 1e-10  # Same value, but now in cm instead of mm

    def test_area_calculation_shoelace_formula(self):
        """Test that area calculation uses shoelace formula correctly."""
        # Create a known shape for area testing
        bbox = BoundingBox(x=100, y=50, width=100, height=100)
        measured = self.measurer.measure_bounding_box(bbox)
        
        # For a rectangle, shoelace formula should give width * height
        expected_area = measured.width_world * measured.height_world
        assert abs(measured.area_world - expected_area) < 1e-6

    def test_complex_homography(self):
        """Test with a more complex homography matrix."""
        # Create a homography with rotation and scaling
        theta = np.pi / 6  # 30 degrees
        scale = 3.0
        H_complex = np.array([
            [scale * np.cos(theta), -scale * np.sin(theta), 200.0],
            [scale * np.sin(theta),  scale * np.cos(theta), 100.0],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)
        
        calib_complex = CalibrationData(H=H_complex, world_unit="mm")
        measurer_complex = PlanarHomographyMeasurer(calib_complex)
        
        bbox = BoundingBox(x=200, y=100, width=60, height=60)
        measured = measurer_complex.measure_bounding_box(bbox)
        
        # Should still produce valid measurements
        assert measured.width_world > 0
        assert measured.height_world > 0
        assert measured.area_world > 0
        assert measured.unit == "mm"

    def test_homography_inverse_computation(self):
        """Test that homography inverse is computed correctly."""
        # The inverse should be precomputed during initialization
        expected_H_inv = np.linalg.inv(self.H)
        np.testing.assert_allclose(self.measurer._H_inv, expected_H_inv, atol=1e-10)

    def test_unit_conversion_edge_cases(self):
        """Test unit conversion edge cases."""
        bbox = BoundingBox(x=100, y=50, width=100, height=100)
        
        # Test converting to same unit (should be no-op)
        measured_same = self.measurer.measure_bounding_box(bbox, target_unit="mm")
        measured_none = self.measurer.measure_bounding_box(bbox, target_unit=None)
        
        assert measured_same.unit == "mm"
        assert measured_none.unit == "mm"
        assert abs(measured_same.width_world - measured_none.width_world) < 1e-15

    def test_corner_ordering(self):
        """Test that corner ordering is consistent with BoundingBox.to_corners()."""
        bbox = BoundingBox(x=100, y=50, width=100, height=100)
        measured = self.measurer.measure_bounding_box(bbox)
        
        # BoundingBox.to_corners() returns [(x1,y1), (x2,y1), (x2,y2), (x1,y2)]
        # which should be [top-left, top-right, bottom-right, bottom-left]
        corners_px = np.array(bbox.to_corners(), dtype=np.float64)
        expected_world = self.measurer.pixels_to_world(corners_px)
        
        np.testing.assert_allclose(measured.corners_world, expected_world, atol=1e-10)

    def test_numerical_precision(self):
        """Test numerical precision with very small and very large values."""
        # Test with very small bounding box
        tiny_bbox = BoundingBox(x=100.1, y=50.1, width=0.2, height=0.2)
        tiny_measured = self.measurer.measure_bounding_box(tiny_bbox)
        
        assert tiny_measured.width_world > 0
        assert tiny_measured.height_world > 0
        assert tiny_measured.area_world > 0
        
        # Test with large bounding box
        large_bbox = BoundingBox(x=100, y=50, width=2000, height=1000)
        large_measured = self.measurer.measure_bounding_box(large_bbox)
        
        assert large_measured.width_world > 0
        assert large_measured.height_world > 0
        assert large_measured.area_world > 0

    def test_measurer_with_camera_parameters(self):
        """Test measurer with calibration data that includes camera parameters."""
        camera_matrix = np.array([[800, 0, 320], [0, 800, 240], [0, 0, 1]], dtype=np.float64)
        dist_coeffs = np.array([0.1, -0.1, 0.001, 0.001], dtype=np.float64)
        
        calib_with_camera = CalibrationData(
            H=self.H,
            camera_matrix=camera_matrix,
            dist_coeffs=dist_coeffs,
            world_unit="mm"
        )
        
        measurer_with_camera = PlanarHomographyMeasurer(calib_with_camera)
        
        bbox = BoundingBox(x=100, y=50, width=100, height=100)
        measured = measurer_with_camera.measure_bounding_box(bbox)
        
        # Should still work normally (camera params used during calibration, not measurement)
        assert measured.width_world > 0
        assert measured.height_world > 0
        assert measured.unit == "mm"
