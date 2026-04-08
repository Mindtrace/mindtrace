"""Unit tests for AsyncStereoCamera wrapper behavior."""

from unittest.mock import AsyncMock, Mock, patch

import cv2
import numpy as np
import pytest

from mindtrace.hardware.core.exceptions import CameraConfigurationError
from mindtrace.hardware.stereo_cameras.core.async_stereo_camera import AsyncStereoCamera
from mindtrace.hardware.stereo_cameras.core.models import PointCloudData, StereoCalibrationData, StereoGrabResult


def _make_calibration():
    return StereoCalibrationData.from_camera_params(
        {
            "Scan3dBaseline": 0.1,
            "Scan3dFocalLength": 100.0,
            "Scan3dPrincipalPointU": 1.0,
            "Scan3dPrincipalPointV": 1.0,
            "Scan3dCoordinateScale": 1.0,
            "Scan3dCoordinateOffset": 0.0,
        }
    )


@pytest.mark.asyncio
async def test_capture_point_cloud_requires_calibration():
    backend = Mock()
    cam = AsyncStereoCamera(backend)

    with pytest.raises(CameraConfigurationError, match="Calibration data not available"):
        await cam.capture_point_cloud()


@pytest.mark.asyncio
async def test_generate_point_cloud_requires_disparity():
    backend = Mock()
    cam = AsyncStereoCamera(backend)
    cam._calibration = _make_calibration()

    result = StereoGrabResult(
        intensity=None,
        disparity=None,
        timestamp=0.0,
        frame_number=1,
        has_intensity=False,
        has_disparity=False,
    )

    with pytest.raises(CameraConfigurationError, match="Disparity data required"):
        cam._generate_point_cloud(result, include_colors=False)


@pytest.mark.asyncio
async def test_capture_point_cloud_happy_path_with_colors():
    backend = Mock()
    cam = AsyncStereoCamera(backend)
    cam._calibration = _make_calibration()

    disparity = np.array([[1, 2], [3, 4]], dtype=np.uint16)
    intensity = np.array([[10, 20], [30, 40]], dtype=np.uint8)
    cam.capture = AsyncMock(
        return_value=StereoGrabResult(
            intensity=intensity,
            disparity=disparity,
            timestamp=1.0,
            frame_number=2,
            has_intensity=True,
            has_disparity=True,
        )
    )

    cloud = await cam.capture_point_cloud(include_colors=True, downsample_factor=1)

    assert cloud.num_points > 0
    assert cloud.has_colors is True
    assert cloud.colors is not None


@pytest.mark.asyncio
async def test_initialize_sets_calibration_on_success():
    backend = Mock()
    backend.initialize = AsyncMock(return_value=True)
    calibration = _make_calibration()
    backend.get_calibration = AsyncMock(return_value=calibration)
    cam = AsyncStereoCamera(backend)

    assert await cam.initialize() is True

    backend.initialize.assert_awaited_once_with()
    backend.get_calibration.assert_awaited_once_with()
    assert cam.calibration is calibration


@pytest.mark.asyncio
async def test_initialize_keeps_calibration_unset_on_failure():
    backend = Mock()
    backend.initialize = AsyncMock(return_value=False)
    backend.get_calibration = AsyncMock()
    cam = AsyncStereoCamera(backend)

    assert await cam.initialize() is False

    backend.initialize.assert_awaited_once_with()
    backend.get_calibration.assert_not_called()
    assert cam.calibration is None


@pytest.mark.asyncio
async def test_close_delegates_to_backend():
    backend = Mock()
    backend.close = AsyncMock(return_value=None)
    cam = AsyncStereoCamera(backend)

    await cam.close()

    backend.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_capture_point_cloud_passes_capture_flags_and_downsamples():
    backend = Mock()
    cam = AsyncStereoCamera(backend)
    cam._calibration = _make_calibration()

    result = StereoGrabResult(
        intensity=None,
        disparity=np.ones((2, 2), dtype=np.uint16),
        timestamp=1.0,
        frame_number=7,
        has_intensity=False,
        has_disparity=True,
    )
    point_cloud = Mock(spec=PointCloudData)
    downsampled = Mock(spec=PointCloudData)
    point_cloud.downsample.return_value = downsampled
    cam.capture = AsyncMock(return_value=result)
    cam._generate_point_cloud = Mock(return_value=point_cloud)

    output = await cam.capture_point_cloud(include_colors=False, downsample_factor=3)

    cam.capture.assert_awaited_once_with(
        enable_intensity=False,
        enable_disparity=True,
        calibrate_disparity=True,
    )
    cam._generate_point_cloud.assert_called_once_with(result, False)
    point_cloud.downsample.assert_called_once_with(3)
    assert output is downsampled


def test_generate_point_cloud_calibrates_raw_disparity_when_needed():
    backend = Mock()
    cam = AsyncStereoCamera(backend)
    calibration = Mock()
    calibration.Q = object()
    disp_cal = np.array([[1.0]], dtype=np.float32)
    calibration.calibrate_disparity.return_value = disp_cal
    cam._calibration = calibration
    result = StereoGrabResult(
        intensity=None,
        disparity=np.array([[5]], dtype=np.uint16),
        timestamp=0.0,
        frame_number=1,
        has_intensity=False,
        has_disparity=True,
    )

    with patch("mindtrace.hardware.stereo_cameras.core.async_stereo_camera.cv2.reprojectImageTo3D", return_value=np.array([[[1.0, 2.0, 3.0]]])):
        cloud = cam._generate_point_cloud(result, include_colors=False)

    calibration.calibrate_disparity.assert_called_once_with(result.disparity)
    assert cloud.num_points == 1
    np.testing.assert_array_equal(cloud.points, np.array([[1.0, 2.0, 3.0]]))
    assert cloud.has_colors is False


def test_generate_point_cloud_uses_calibrated_disparity_filters_invalid_points_and_colors():
    backend = Mock()
    cam = AsyncStereoCamera(backend)
    calibration = Mock()
    calibration.Q = object()
    cam._calibration = calibration
    disparity = np.array([[1, 2], [3, 4]], dtype=np.uint16)
    disparity_calibrated = np.array([[0.5, 1.5], [2.5, 3.5]], dtype=np.float32)
    result = StereoGrabResult(
        intensity=np.array([[32]], dtype=np.uint8),
        disparity=disparity,
        disparity_calibrated=disparity_calibrated,
        timestamp=0.0,
        frame_number=2,
        has_intensity=True,
        has_disparity=True,
    )
    points_3d = np.array(
        [
            [[1.0, 2.0, 3.0], [np.inf, 0.0, 0.0]],
            [[4.0, 5.0, 6.0], [7.0, 8.0, 9.0]],
        ],
        dtype=np.float32,
    )
    resized = np.array([[10, 20], [30, 40]], dtype=np.uint8)
    rgb = np.stack([resized, resized + 1, resized + 2], axis=-1)

    with (
        patch("mindtrace.hardware.stereo_cameras.core.async_stereo_camera.cv2.reprojectImageTo3D", return_value=points_3d) as reproject,
        patch("mindtrace.hardware.stereo_cameras.core.async_stereo_camera.cv2.resize", return_value=resized) as resize,
        patch("mindtrace.hardware.stereo_cameras.core.async_stereo_camera.cv2.cvtColor", return_value=rgb) as cvt_color,
    ):
        cloud = cam._generate_point_cloud(result, include_colors=True)

    calibration.calibrate_disparity.assert_not_called()
    reproject.assert_called_once_with(disparity_calibrated, calibration.Q)
    resize.assert_called_once_with(result.intensity, (2, 2), interpolation=cv2.INTER_LINEAR)
    cvt_color.assert_called_once_with(resized, cv2.COLOR_GRAY2RGB)
    assert cloud.num_points == 3
    np.testing.assert_array_equal(
        cloud.points,
        np.array(
            [
                [1.0, 2.0, 3.0],
                [4.0, 5.0, 6.0],
                [7.0, 8.0, 9.0],
            ]
        ),
    )
    np.testing.assert_allclose(
        cloud.colors,
        np.array(
            [
                [10.0, 11.0, 12.0],
                [30.0, 31.0, 32.0],
                [40.0, 41.0, 42.0],
            ]
        )
        / 255.0,
    )
    assert cloud.has_colors is True


def test_repr_uses_name_and_state():
    backend = Mock()
    backend.name = "BaslerStereoAce:123"
    backend.is_open = True
    cam = AsyncStereoCamera(backend)
    assert "BaslerStereoAce:123" in repr(cam)
    assert "open" in repr(cam)
