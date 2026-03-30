"""Tests for stereo camera data models."""

import numpy as np
import pytest

from mindtrace.hardware.stereo_cameras.core.models import (
    PointCloudData,
    StereoCalibrationData,
    StereoGrabResult,
)


class TestStereoGrabResult:
    """Tests for StereoGrabResult dataclass."""

    def test_create_with_both_components(self):
        """Test creating result with intensity and disparity."""
        intensity = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        disparity = np.random.randint(0, 65535, (480, 640), dtype=np.uint16)

        result = StereoGrabResult(
            intensity=intensity,
            disparity=disparity,
            timestamp=1.23,
            frame_number=42,
            has_intensity=True,
            has_disparity=True,
        )

        assert result.intensity is intensity
        assert result.disparity is disparity
        assert result.timestamp == 1.23
        assert result.frame_number == 42
        assert result.has_intensity
        assert result.has_disparity
        assert result.disparity_calibrated is None

    def test_intensity_shape_property(self):
        """Test intensity_shape property."""
        intensity = np.zeros((480, 640, 3), dtype=np.uint8)
        result = StereoGrabResult(intensity=intensity, disparity=None, timestamp=0, frame_number=0)

        assert result.intensity_shape == (480, 640, 3)

    def test_disparity_shape_property(self):
        """Test disparity_shape property."""
        disparity = np.zeros((480, 640), dtype=np.uint16)
        result = StereoGrabResult(intensity=None, disparity=disparity, timestamp=0, frame_number=0)

        assert result.disparity_shape == (480, 640)

    def test_shape_when_none(self):
        """Test shape properties when components are None."""
        result = StereoGrabResult(
            intensity=None,
            disparity=None,
            timestamp=0,
            frame_number=0,
            has_intensity=False,
            has_disparity=False,
        )

        assert result.intensity_shape == (0, 0)
        assert result.disparity_shape == (0, 0)

    def test_is_color_intensity_rgb(self):
        """Test is_color_intensity for RGB image."""
        intensity = np.zeros((480, 640, 3), dtype=np.uint8)
        result = StereoGrabResult(intensity=intensity, disparity=None, timestamp=0, frame_number=0)

        assert result.is_color_intensity is True

    def test_is_color_intensity_grayscale(self):
        """Test is_color_intensity for grayscale image."""
        intensity = np.zeros((480, 640), dtype=np.uint8)
        result = StereoGrabResult(intensity=intensity, disparity=None, timestamp=0, frame_number=0)

        assert result.is_color_intensity is False

    def test_is_color_intensity_none(self):
        """Test is_color_intensity when intensity is None."""
        result = StereoGrabResult(intensity=None, disparity=None, timestamp=0, frame_number=0, has_intensity=False)

        assert result.is_color_intensity is False

    def test_repr(self):
        """Test string representation."""
        intensity = np.zeros((480, 640, 3), dtype=np.uint8)
        disparity = np.zeros((480, 640), dtype=np.uint16)
        result = StereoGrabResult(intensity=intensity, disparity=disparity, timestamp=1.5, frame_number=10)

        repr_str = repr(result)
        assert "frame=10" in repr_str
        assert "480, 640" in repr_str
        assert "calibrated=False" in repr_str

    def test_with_calibrated_disparity(self):
        """Test result with calibrated disparity map."""
        intensity = np.zeros((480, 640, 3), dtype=np.uint8)
        disparity = np.zeros((480, 640), dtype=np.uint16)
        disparity_cal = np.zeros((480, 640), dtype=np.float32)

        result = StereoGrabResult(
            intensity=intensity,
            disparity=disparity,
            disparity_calibrated=disparity_cal,
            timestamp=0,
            frame_number=0,
        )

        assert result.disparity_calibrated is not None
        repr_str = repr(result)
        assert "calibrated=True" in repr_str


class TestStereoCalibrationData:
    """Tests for StereoCalibrationData dataclass."""

    def test_create_from_camera_params(self):
        """Test creating calibration from camera parameters."""
        params = {
            "Scan3dBaseline": 0.120,  # 120mm baseline
            "Scan3dFocalLength": 2000.0,
            "Scan3dPrincipalPointU": 320.0,
            "Scan3dPrincipalPointV": 240.0,
            "Scan3dCoordinateScale": 0.00390625,
            "Scan3dCoordinateOffset": -128.0,
        }

        calib = StereoCalibrationData.from_camera_params(params)

        assert calib.baseline == 0.120
        assert calib.focal_length == 2000.0
        assert calib.principal_point_u == 320.0
        assert calib.principal_point_v == 240.0
        assert calib.scale3d == 0.00390625
        assert calib.offset3d == -128.0
        assert calib.Q.shape == (4, 4)
        assert calib.Q.dtype == np.float64

    def test_q_matrix_structure(self):
        """Test Q matrix has correct structure."""
        params = {
            "Scan3dBaseline": 0.1,
            "Scan3dFocalLength": 1000.0,
            "Scan3dPrincipalPointU": 320.0,
            "Scan3dPrincipalPointV": 240.0,
            "Scan3dCoordinateScale": 1.0,
            "Scan3dCoordinateOffset": 0.0,
        }

        calib = StereoCalibrationData.from_camera_params(params)
        Q = calib.Q

        # Check Q matrix structure for cv2.reprojectImageTo3D
        assert Q[0, 0] == 1
        assert Q[0, 3] == -320.0  # -pp_u
        assert Q[1, 1] == -1
        assert Q[1, 3] == 240.0  # pp_v
        assert Q[2, 3] == -1000.0  # -focal
        assert Q[3, 2] == 1 / 0.1  # 1/baseline

    def test_calibrate_disparity_basic(self):
        """Test basic disparity calibration."""
        params = {
            "Scan3dBaseline": 0.1,
            "Scan3dFocalLength": 1000.0,
            "Scan3dPrincipalPointU": 320.0,
            "Scan3dPrincipalPointV": 240.0,
            "Scan3dCoordinateScale": 2.0,
            "Scan3dCoordinateOffset": 0.0,
        }

        calib = StereoCalibrationData.from_camera_params(params)
        disparity = np.array([[100, 200], [300, 400]], dtype=np.uint16)
        calib_disp = calib.calibrate_disparity(disparity)

        assert calib_disp.dtype == np.float32
        assert calib_disp.shape == disparity.shape
        # Check scale is applied: value * scale + offset
        np.testing.assert_array_equal(calib_disp, disparity * 2.0)

    def test_calibrate_disparity_with_offset(self):
        """Test disparity calibration with offset."""
        params = {
            "Scan3dBaseline": 0.1,
            "Scan3dFocalLength": 1000.0,
            "Scan3dPrincipalPointU": 320.0,
            "Scan3dPrincipalPointV": 240.0,
            "Scan3dCoordinateScale": 1.0,
            "Scan3dCoordinateOffset": -100.0,
        }

        calib = StereoCalibrationData.from_camera_params(params)
        disparity = np.array([[0, 150], [200, 0]], dtype=np.uint16)
        calib_disp = calib.calibrate_disparity(disparity)

        # Zero disparity should stay zero
        assert calib_disp[0, 0] == 0
        assert calib_disp[1, 1] == 0
        # Non-zero should have scale + offset
        assert calib_disp[0, 1] == 50.0  # 150 - 100
        assert calib_disp[1, 0] == 100.0  # 200 - 100

    def test_repr(self):
        """Test string representation."""
        params = {
            "Scan3dBaseline": 0.120,
            "Scan3dFocalLength": 2000.5,
            "Scan3dPrincipalPointU": 320.25,
            "Scan3dPrincipalPointV": 240.75,
            "Scan3dCoordinateScale": 1.0,
            "Scan3dCoordinateOffset": 0.0,
        }

        calib = StereoCalibrationData.from_camera_params(params)
        repr_str = repr(calib)

        assert "baseline=120.00mm" in repr_str
        assert "focal=2000.5px" in repr_str
        assert "(320.2, 240.8)" in repr_str


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

    def test_create_with_explicit_num_points(self):
        """Test creating with explicitly specified num_points."""
        points = np.random.rand(1000, 3).astype(np.float32)
        pcd = PointCloudData(points=points, num_points=1000)

        assert pcd.num_points == 1000

    def test_mismatched_points_colors_raises(self):
        """Test that mismatched points and colors raises ValueError."""
        points = np.random.rand(1000, 3).astype(np.float32)
        colors = np.random.rand(500, 3).astype(np.float32)

        with pytest.raises(ValueError, match="Points and colors must have same length"):
            PointCloudData(points=points, colors=colors)

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

    def test_repr(self):
        """Test string representation."""
        points = np.random.rand(1500, 3).astype(np.float32)
        pcd = PointCloudData(points=points)

        repr_str = repr(pcd)
        assert "points=1500" in repr_str
        assert "no colors" in repr_str

        colors = np.random.rand(1500, 3).astype(np.float32)
        pcd_color = PointCloudData(points=points, colors=colors)
        repr_str = repr(pcd_color)
        assert "with colors" in repr_str

    def test_save_ply_import_error(self):
        """Test save_ply raises ImportError when plyfile not available."""
        points = np.random.rand(100, 3).astype(np.float32)
        pcd = PointCloudData(points=points)

        # Mock plyfile as unavailable
        import sys
        from unittest.mock import patch

        with patch.dict(sys.modules, {"plyfile": None}):
            with pytest.raises(ImportError, match="plyfile package required"):
                pcd.save_ply("test.ply")

    @pytest.mark.skip(reason="to_open3d method not yet implemented in stereo PointCloudData")
    def test_to_open3d_import_error(self):
        """Test to_open3d raises ImportError when open3d not available."""
        points = np.random.rand(100, 3).astype(np.float32)
        pcd = PointCloudData(points=points)

        import sys
        from unittest.mock import patch

        with patch.dict(sys.modules, {"open3d": None}):
            with pytest.raises(ImportError, match="open3d package required"):
                pcd.to_open3d()

    @pytest.mark.skip(reason="remove_statistical_outliers method not yet implemented in stereo PointCloudData")
    def test_remove_statistical_outliers_import_error(self):
        """Test remove_statistical_outliers raises ImportError when open3d not available."""
        points = np.random.rand(100, 3).astype(np.float32)
        pcd = PointCloudData(points=points)

        from unittest.mock import patch

        with patch("importlib.util.find_spec", return_value=None):
            with pytest.raises(ImportError, match="open3d package required"):
                pcd.remove_statistical_outliers()
