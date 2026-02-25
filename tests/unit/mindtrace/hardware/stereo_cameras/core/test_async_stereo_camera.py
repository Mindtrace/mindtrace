"""Unit tests for AsyncStereoCamera wrapper behavior."""

from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest

from mindtrace.hardware.core.exceptions import CameraConfigurationError
from mindtrace.hardware.stereo_cameras.core.async_stereo_camera import AsyncStereoCamera
from mindtrace.hardware.stereo_cameras.core.models import StereoCalibrationData, StereoGrabResult


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
    cam._calibration = StereoCalibrationData.from_camera_params(
        {
            "Scan3dBaseline": 0.1,
            "Scan3dFocalLength": 100.0,
            "Scan3dPrincipalPointU": 1.0,
            "Scan3dPrincipalPointV": 1.0,
            "Scan3dCoordinateScale": 1.0,
            "Scan3dCoordinateOffset": 0.0,
        }
    )

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
    cam._calibration = StereoCalibrationData.from_camera_params(
        {
            "Scan3dBaseline": 0.1,
            "Scan3dFocalLength": 100.0,
            "Scan3dPrincipalPointU": 1.0,
            "Scan3dPrincipalPointV": 1.0,
            "Scan3dCoordinateScale": 1.0,
            "Scan3dCoordinateOffset": 0.0,
        }
    )

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

    cloud = await cam.capture_point_cloud(include_colors=True, downsample_factor=1, remove_outliers=False)

    assert cloud.num_points > 0
    assert cloud.has_colors is True
    assert cloud.colors is not None


def test_repr_uses_name_and_state():
    backend = Mock()
    backend.name = "BaslerStereoAce:123"
    backend.is_open = True
    cam = AsyncStereoCamera(backend)
    assert "BaslerStereoAce:123" in repr(cam)
    assert "open" in repr(cam)
