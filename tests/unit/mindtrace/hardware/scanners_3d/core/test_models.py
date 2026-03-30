"""Tests for 3D scanner data models."""

import sys
from unittest.mock import patch

import numpy as np
import pytest

from mindtrace.hardware.scanners_3d.core.models import (
    CodingQuality,
    CodingStrategy,
    CoordinateMap,
    OperationMode,
    PointCloudData,
    ScanComponent,
    ScannerCapabilities,
    ScannerConfiguration,
    ScanResult,
    TriggerMode,
)


class TestScanComponent:
    """Tests for ScanComponent enum."""

    def test_all_components_defined(self):
        """Test all expected components are defined."""
        components = [c.value for c in ScanComponent]
        assert "Range" in components
        assert "Intensity" in components
        assert "Confidence" in components
        assert "Normal" in components
        assert "ColorCamera" in components
        assert "Event" in components

    def test_component_from_string(self):
        """Test creating component from string value."""
        assert ScanComponent("Range") == ScanComponent.RANGE
        assert ScanComponent("Intensity") == ScanComponent.INTENSITY


class TestOperationMode:
    """Tests for OperationMode enum."""

    def test_all_modes_defined(self):
        """Test all operation modes are defined."""
        assert OperationMode.CAMERA.value == "Camera"
        assert OperationMode.SCANNER.value == "Scanner"
        assert OperationMode.MODE_2D.value == "Mode_2D"


class TestCodingStrategy:
    """Tests for CodingStrategy enum."""

    def test_all_strategies_defined(self):
        """Test all coding strategies are defined."""
        assert CodingStrategy.NORMAL.value == "Normal"
        assert CodingStrategy.INTERREFLECTIONS.value == "Interreflections"
        assert CodingStrategy.HIGH_FREQUENCY.value == "HighFrequency"


class TestCodingQuality:
    """Tests for CodingQuality enum."""

    def test_all_qualities_defined(self):
        """Test all coding qualities are defined."""
        assert CodingQuality.ULTRA.value == "Ultra"
        assert CodingQuality.HIGH.value == "High"
        assert CodingQuality.FAST.value == "Fast"


class TestScannerConfiguration:
    """Tests for ScannerConfiguration dataclass."""

    def test_create_empty_config(self):
        """Test creating empty configuration."""
        config = ScannerConfiguration()
        assert config.operation_mode is None
        assert config.exposure_time is None
        assert config.led_power is None

    def test_create_with_values(self):
        """Test creating configuration with values."""
        config = ScannerConfiguration(
            operation_mode=OperationMode.CAMERA,
            coding_quality=CodingQuality.ULTRA,
            exposure_time=20.0,
            led_power=4095,
            laser_power=4095,
        )
        assert config.operation_mode == OperationMode.CAMERA
        assert config.coding_quality == CodingQuality.ULTRA
        assert config.exposure_time == 20.0
        assert config.led_power == 4095
        assert config.laser_power == 4095

    def test_to_dict_excludes_none(self):
        """Test to_dict excludes None values."""
        config = ScannerConfiguration(
            coding_quality=CodingQuality.HIGH,
            exposure_time=15.0,
        )
        d = config.to_dict()
        assert "coding_quality" in d
        assert "exposure_time" in d
        assert "operation_mode" not in d
        assert "led_power" not in d

    def test_to_dict_converts_enums(self):
        """Test to_dict converts enums to string values."""
        config = ScannerConfiguration(
            operation_mode=OperationMode.SCANNER,
            coding_strategy=CodingStrategy.INTERREFLECTIONS,
            trigger_mode=TriggerMode.SOFTWARE,
        )
        d = config.to_dict()
        assert d["operation_mode"] == "Scanner"
        assert d["coding_strategy"] == "Interreflections"
        assert d["trigger_mode"] == "Software"

    def test_from_dict_basic(self):
        """Test from_dict with basic values."""
        data = {
            "exposure_time": 25.0,
            "led_power": 2000,
            "laser_power": 3000,
        }
        config = ScannerConfiguration.from_dict(data)
        assert config.exposure_time == 25.0
        assert config.led_power == 2000
        assert config.laser_power == 3000

    def test_from_dict_with_string_enums(self):
        """Test from_dict converts string values to enums."""
        data = {
            "operation_mode": "Camera",
            "coding_strategy": "Interreflections",
            "coding_quality": "Ultra",
            "trigger_mode": "Hardware",
        }
        config = ScannerConfiguration.from_dict(data)
        assert config.operation_mode == OperationMode.CAMERA
        assert config.coding_strategy == CodingStrategy.INTERREFLECTIONS
        assert config.coding_quality == CodingQuality.ULTRA
        assert config.trigger_mode == TriggerMode.HARDWARE

    def test_from_dict_ignores_unknown_keys(self):
        """Test from_dict ignores unknown keys."""
        data = {
            "exposure_time": 10.0,
            "unknown_key": "value",
        }
        config = ScannerConfiguration.from_dict(data)
        assert config.exposure_time == 10.0
        assert not hasattr(config, "unknown_key") or getattr(config, "unknown_key", None) is None


class TestScannerCapabilities:
    """Tests for ScannerCapabilities dataclass."""

    def test_default_values(self):
        """Test default capability values."""
        caps = ScannerCapabilities()
        assert caps.has_range is True
        assert caps.has_intensity is False
        assert caps.has_color is False
        assert caps.operation_modes == []
        assert caps.model == ""

    def test_create_with_values(self):
        """Test creating capabilities with values."""
        caps = ScannerCapabilities(
            has_range=True,
            has_intensity=True,
            has_confidence=True,
            has_normal=True,
            has_color=True,
            operation_modes=["Camera", "Scanner"],
            coding_qualities=["Ultra", "High", "Fast"],
            exposure_range=(10.24, 100.352),
            led_power_range=(0, 4095),
            model="MotionCam-3D Color",
            serial_number="DVJ-104",
        )
        assert caps.has_color is True
        assert "Camera" in caps.operation_modes
        assert caps.exposure_range == (10.24, 100.352)
        assert caps.model == "MotionCam-3D Color"


class TestScanResult:
    """Tests for ScanResult dataclass."""

    def test_create_with_range_only(self):
        """Test creating result with range data only."""
        range_map = np.random.rand(480, 640).astype(np.float32) * 1000
        result = ScanResult(
            range_map=range_map,
            timestamp=1.23,
            frame_number=42,
        )

        assert result.has_range is True
        assert result.has_intensity is False
        assert result.has_confidence is False
        assert result.has_normals is False
        assert result.has_color is False
        assert result.range_shape == (480, 640)

    def test_create_with_all_components(self):
        """Test creating result with all components."""
        range_map = np.random.rand(480, 640, 3).astype(np.float32)
        intensity = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        confidence = np.random.randint(0, 255, (480, 640), dtype=np.uint8)
        normal_map = np.random.rand(480, 640, 3).astype(np.float32)
        color = np.random.randint(0, 255, (1096, 1932, 3), dtype=np.uint8)

        result = ScanResult(
            range_map=range_map,
            intensity=intensity,
            confidence=confidence,
            normal_map=normal_map,
            color=color,
            timestamp=2.5,
            frame_number=100,
        )

        assert result.has_range is True
        assert result.has_intensity is True
        assert result.has_confidence is True
        assert result.has_normals is True
        assert result.has_color is True
        assert result.frame_number == 100

    def test_range_shape_property(self):
        """Test range_shape property."""
        range_map = np.zeros((800, 560, 3), dtype=np.float32)
        result = ScanResult(range_map=range_map, timestamp=0, frame_number=0)
        assert result.range_shape == (800, 560, 3)

    def test_intensity_shape_property(self):
        """Test intensity_shape property."""
        intensity = np.zeros((800, 560, 3), dtype=np.uint8)
        result = ScanResult(intensity=intensity, timestamp=0, frame_number=0)
        assert result.intensity_shape == (800, 560, 3)

    def test_shape_when_none(self):
        """Test shape properties when components are None."""
        result = ScanResult(timestamp=0, frame_number=0)
        assert result.range_shape == (0, 0)
        assert result.intensity_shape == (0, 0)

    def test_get_valid_mask_basic(self):
        """Test get_valid_mask basic functionality."""
        range_map = np.array([[0, 100, 200], [300, 0, 400]], dtype=np.float32)
        result = ScanResult(range_map=range_map, timestamp=0, frame_number=0)

        mask = result.get_valid_mask()
        expected = np.array([[False, True, True], [True, False, True]])
        np.testing.assert_array_equal(mask, expected)

    def test_get_valid_mask_with_confidence(self):
        """Test get_valid_mask with confidence threshold."""
        range_map = np.array([[100, 100, 100], [100, 100, 100]], dtype=np.float32)
        confidence = np.array([[50, 100, 150], [200, 25, 75]], dtype=np.uint8)
        result = ScanResult(
            range_map=range_map,
            confidence=confidence,
            timestamp=0,
            frame_number=0,
        )

        mask = result.get_valid_mask(min_confidence=100)
        expected = np.array([[False, True, True], [True, False, False]])
        np.testing.assert_array_equal(mask, expected)

    def test_get_valid_mask_no_range_raises(self):
        """Test get_valid_mask raises when no range data."""
        result = ScanResult(timestamp=0, frame_number=0)
        with pytest.raises(ValueError, match="No range data available"):
            result.get_valid_mask()

    def test_repr(self):
        """Test string representation."""
        range_map = np.zeros((480, 640, 3), dtype=np.float32)
        intensity = np.zeros((480, 640, 3), dtype=np.uint8)
        result = ScanResult(
            range_map=range_map,
            intensity=intensity,
            timestamp=1.5,
            frame_number=10,
        )

        repr_str = repr(result)
        assert "frame=10" in repr_str
        assert "range=" in repr_str
        assert "intensity=" in repr_str


class TestCoordinateMap:
    """Tests for CoordinateMap dataclass."""

    def test_create_invalid_by_default(self):
        """Test coordinate map is invalid by default."""
        coord_map = CoordinateMap()
        assert coord_map.is_valid is False
        assert coord_map.x_map is None
        assert coord_map.y_map is None

    def test_from_projected_c(self):
        """Test creating from ProjectedC data."""
        projected_c = np.random.rand(480, 640, 3).astype(np.float32)
        coord_map = CoordinateMap.from_projected_c(
            projected_c=projected_c,
            width=640,
            height=480,
            scale=0.001,
            offset=0.0,
        )

        assert coord_map.is_valid is True
        assert coord_map.x_map.shape == (480, 640)
        assert coord_map.y_map.shape == (480, 640)
        assert coord_map.width == 640
        assert coord_map.height == 480
        assert coord_map.scale == 0.001

    def test_from_projected_c_invalid_shape(self):
        """Test from_projected_c raises on invalid shape."""
        invalid_data = np.random.rand(480, 640).astype(np.float32)  # Missing channel dim
        with pytest.raises(ValueError, match="Expected"):
            CoordinateMap.from_projected_c(invalid_data, 640, 480)

    def test_compute_point_cloud(self):
        """Test computing point cloud from range map."""
        # Create simple coordinate map
        x_map = np.ones((100, 100), dtype=np.float32) * 0.5
        y_map = np.ones((100, 100), dtype=np.float32) * 0.3

        coord_map = CoordinateMap(
            x_map=x_map,
            y_map=y_map,
            width=100,
            height=100,
            scale=1.0,
            offset=0.0,
            is_valid=True,
        )

        range_map = np.ones((100, 100), dtype=np.float32) * 1000  # 1000mm
        points = coord_map.compute_point_cloud(range_map)

        assert points.shape[1] == 3  # (N, 3)
        assert len(points) == 10000  # All points valid

    def test_compute_point_cloud_with_mask(self):
        """Test computing point cloud with valid mask."""
        x_map = np.ones((10, 10), dtype=np.float32)
        y_map = np.ones((10, 10), dtype=np.float32)

        coord_map = CoordinateMap(
            x_map=x_map,
            y_map=y_map,
            width=10,
            height=10,
            is_valid=True,
        )

        range_map = np.ones((10, 10), dtype=np.float32) * 100
        mask = np.zeros((10, 10), dtype=bool)
        mask[5:, 5:] = True  # Only bottom-right 25 points

        points = coord_map.compute_point_cloud(range_map, valid_mask=mask)
        assert len(points) == 25

    def test_compute_point_cloud_invalid_map(self):
        """Test compute_point_cloud raises when map not initialized."""
        coord_map = CoordinateMap()
        range_map = np.ones((100, 100), dtype=np.float32)

        with pytest.raises(ValueError, match="not initialized"):
            coord_map.compute_point_cloud(range_map)

    def test_compute_point_cloud_shape_mismatch(self):
        """Test compute_point_cloud raises on shape mismatch."""
        coord_map = CoordinateMap(
            x_map=np.ones((100, 100), dtype=np.float32),
            y_map=np.ones((100, 100), dtype=np.float32),
            width=100,
            height=100,
            is_valid=True,
        )

        wrong_range = np.ones((50, 50), dtype=np.float32)
        with pytest.raises(ValueError, match="doesn't match"):
            coord_map.compute_point_cloud(wrong_range)

    def test_repr(self):
        """Test string representation."""
        coord_map = CoordinateMap(width=640, height=480, is_valid=True)
        repr_str = repr(coord_map)
        assert "640x480" in repr_str
        assert "valid" in repr_str


class TestPointCloudData:
    """Tests for PointCloudData dataclass."""

    def test_create_without_colors(self):
        """Test creating point cloud without colors."""
        points = np.random.rand(1000, 3).astype(np.float32)
        pcd = PointCloudData(points=points)

        assert pcd.num_points == 1000
        assert pcd.has_colors is False
        assert pcd.colors is None

    def test_create_with_colors(self):
        """Test creating point cloud with colors."""
        points = np.random.rand(1000, 3).astype(np.float32)
        colors = np.random.rand(1000, 3).astype(np.float32)
        pcd = PointCloudData(points=points, colors=colors)

        assert pcd.num_points == 1000
        assert pcd.has_colors is True
        assert pcd.colors is not None

    def test_create_with_normals(self):
        """Test creating point cloud with normals."""
        points = np.random.rand(1000, 3).astype(np.float32)
        normals = np.random.rand(1000, 3).astype(np.float32)
        pcd = PointCloudData(points=points, normals=normals)

        assert pcd.has_normals is True
        assert pcd.normals is not None

    def test_create_with_confidence(self):
        """Test creating point cloud with confidence."""
        points = np.random.rand(1000, 3).astype(np.float32)
        confidence = np.random.rand(1000).astype(np.float32)
        pcd = PointCloudData(points=points, confidence=confidence)

        assert pcd.has_confidence is True
        assert pcd.confidence is not None

    def test_create_with_explicit_num_points(self):
        """Test creating with explicitly specified num_points."""
        points = np.random.rand(1000, 3).astype(np.float32)
        pcd = PointCloudData(points=points, num_points=1000)

        assert pcd.num_points == 1000

    def test_mismatched_points_colors_raises(self):
        """Test that mismatched points and colors raises ValueError."""
        points = np.random.rand(1000, 3).astype(np.float32)
        colors = np.random.rand(500, 3).astype(np.float32)

        with pytest.raises(ValueError, match="Colors length"):
            PointCloudData(points=points, colors=colors)

    def test_mismatched_points_normals_raises(self):
        """Test that mismatched points and normals raises ValueError."""
        points = np.random.rand(1000, 3).astype(np.float32)
        normals = np.random.rand(500, 3).astype(np.float32)

        with pytest.raises(ValueError, match="Normals length"):
            PointCloudData(points=points, normals=normals)

    def test_mismatched_points_confidence_raises(self):
        """Test that mismatched points and confidence raises ValueError."""
        points = np.random.rand(1000, 3).astype(np.float32)
        confidence = np.random.rand(500).astype(np.float32)

        with pytest.raises(ValueError, match="Confidence length"):
            PointCloudData(points=points, confidence=confidence)

    def test_downsample(self):
        """Test downsampling point cloud."""
        points = np.arange(1000).reshape(-1, 1).repeat(3, axis=1).astype(np.float32)
        pcd = PointCloudData(points=points)

        downsampled = pcd.downsample(factor=2)

        assert downsampled.num_points == 500
        assert downsampled.has_colors is False
        # Check that we got every 2nd point
        np.testing.assert_array_equal(downsampled.points[0], [0, 0, 0])
        np.testing.assert_array_equal(downsampled.points[1], [2, 2, 2])

    def test_downsample_with_colors(self):
        """Test downsampling point cloud with colors."""
        points = np.arange(1000).reshape(-1, 1).repeat(3, axis=1).astype(np.float32)
        colors = np.random.rand(1000, 3).astype(np.float32)
        pcd = PointCloudData(points=points, colors=colors)

        downsampled = pcd.downsample(factor=4)

        assert downsampled.num_points == 250
        assert downsampled.has_colors is True
        assert downsampled.colors.shape[0] == 250

    def test_downsample_with_all_attributes(self):
        """Test downsampling preserves all attributes."""
        points = np.random.rand(1000, 3).astype(np.float32)
        colors = np.random.rand(1000, 3).astype(np.float32)
        normals = np.random.rand(1000, 3).astype(np.float32)
        confidence = np.random.rand(1000).astype(np.float32)

        pcd = PointCloudData(
            points=points,
            colors=colors,
            normals=normals,
            confidence=confidence,
        )

        downsampled = pcd.downsample(factor=5)

        assert downsampled.num_points == 200
        assert downsampled.has_colors is True
        assert downsampled.has_normals is True
        assert downsampled.has_confidence is True

    def test_filter_by_confidence(self):
        """Test filtering by confidence threshold."""
        points = np.random.rand(100, 3).astype(np.float32)
        confidence = np.linspace(0, 1, 100).astype(np.float32)
        pcd = PointCloudData(points=points, confidence=confidence)

        filtered = pcd.filter_by_confidence(min_confidence=0.5)

        # linspace(0, 1, 100) gives values 0/99, 1/99, ..., 99/99
        # Values >= 0.5 start at index 50 (value 50/99 = 0.505...) through 99
        # That's 50 values (indices 50-99)
        assert filtered.num_points == 50
        assert filtered.has_confidence is True

    def test_filter_by_confidence_no_confidence_raises(self):
        """Test filter_by_confidence raises when no confidence data."""
        points = np.random.rand(100, 3).astype(np.float32)
        pcd = PointCloudData(points=points)

        with pytest.raises(ValueError, match="No confidence data"):
            pcd.filter_by_confidence(min_confidence=0.5)

    def test_repr(self):
        """Test string representation."""
        points = np.random.rand(1500, 3).astype(np.float32)
        pcd = PointCloudData(points=points)

        repr_str = repr(pcd)
        assert "points=1500" in repr_str

        colors = np.random.rand(1500, 3).astype(np.float32)
        pcd_color = PointCloudData(points=points, colors=colors)
        repr_str = repr(pcd_color)
        assert "colors" in repr_str

    def test_save_ply_import_error(self):
        """Test save_ply raises ImportError when plyfile not available."""
        points = np.random.rand(100, 3).astype(np.float32)
        pcd = PointCloudData(points=points)

        with patch.dict(sys.modules, {"plyfile": None}):
            with pytest.raises(ImportError, match="plyfile package required"):
                pcd.save_ply("test.ply")
