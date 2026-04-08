"""Focused tests for BaslerStereoAceBackend point-cloud and error paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest

from mindtrace.hardware.core.exceptions import CameraConfigurationError
from mindtrace.hardware.stereo_cameras.backends.basler.basler_stereo_ace import BaslerStereoAceBackend
from mindtrace.hardware.stereo_cameras.core.models import StereoGrabResult


class _ValueNode:
    def __init__(self, value):
        self.Value = value

    def GetValue(self):
        return self.Value


def _bare_backend() -> BaslerStereoAceBackend:
    backend = BaslerStereoAceBackend.__new__(BaslerStereoAceBackend)
    backend._is_open = True
    backend._camera = Mock()
    backend._grab_strategy = object()
    backend._calibration = None
    backend._op_timeout_s = 1.0
    backend.serial_number = "12345"
    backend.logger = Mock()

    async def _run_blocking(func, *args, **kwargs):
        return func(*args, **kwargs)

    backend._run_blocking = _run_blocking
    return backend


@pytest.mark.asyncio
async def test_discover_async_delegates_to_sync_discover(monkeypatch):
    monkeypatch.setattr(BaslerStereoAceBackend, "discover", staticmethod(lambda: ["SER123", "SER456"]))

    result = await BaslerStereoAceBackend.discover_async()

    assert result == ["SER123", "SER456"]


@pytest.mark.asyncio
async def test_discover_detailed_async_delegates_to_sync_variant(monkeypatch):
    detailed = [{"serial_number": "SER123", "model_name": "Stereo ace", "friendly_name": "Left", "device_class": "cls"}]
    monkeypatch.setattr(BaslerStereoAceBackend, "discover_detailed", staticmethod(lambda: detailed))

    result = await BaslerStereoAceBackend.discover_detailed_async()

    assert result == detailed


@pytest.mark.asyncio
async def test_get_calibration_returns_structured_data():
    backend = _bare_backend()
    backend._camera = Mock(
        Scan3dBaseline=_ValueNode(0.12),
        Scan3dFocalLength=_ValueNode(2000.0),
        Scan3dPrincipalPointU=_ValueNode(320.0),
        Scan3dPrincipalPointV=_ValueNode(240.0),
        Scan3dCoordinateScale=_ValueNode(1.0),
        Scan3dCoordinateOffset=_ValueNode(-2.0),
    )

    calibration = await backend.get_calibration()

    assert calibration.baseline == 0.12
    assert calibration.focal_length == 2000.0
    assert calibration.principal_point_u == 320.0
    assert calibration.principal_point_v == 240.0
    assert calibration.offset3d == -2.0
    assert calibration.Q.shape == (4, 4)


@pytest.mark.asyncio
async def test_get_calibration_wraps_sdk_failures():
    backend = _bare_backend()
    backend._run_blocking = AsyncMock(side_effect=RuntimeError("sdk read failed"))

    with pytest.raises(CameraConfigurationError, match="Failed to read calibration: sdk read failed"):
        await backend.get_calibration()


@pytest.mark.asyncio
async def test_get_trigger_mode_wraps_runtime_errors():
    backend = _bare_backend()
    backend._run_blocking = AsyncMock(side_effect=RuntimeError("trigger query failed"))

    with pytest.raises(CameraConfigurationError, match="Failed to get trigger mode: trigger query failed"):
        await backend.get_trigger_mode()


@pytest.mark.asyncio
async def test_execute_trigger_wraps_runtime_errors():
    backend = _bare_backend()
    backend._run_blocking = AsyncMock(side_effect=RuntimeError("trigger execute failed"))

    with pytest.raises(CameraConfigurationError, match="Failed to execute trigger: trigger execute failed"):
        await backend.execute_trigger()


@pytest.mark.asyncio
async def test_capture_point_cloud_requires_calibration():
    backend = _bare_backend()
    backend._calibration = None

    with pytest.raises(CameraConfigurationError, match="Calibration data not available"):
        await backend.capture_point_cloud()


@pytest.mark.asyncio
async def test_capture_point_cloud_requires_disparity_data():
    backend = _bare_backend()
    backend._calibration = Mock()
    backend.capture = AsyncMock(
        return_value=StereoGrabResult(
            intensity=None,
            disparity=None,
            timestamp=1.0,
            frame_number=7,
            disparity_calibrated=None,
            has_intensity=False,
            has_disparity=False,
        )
    )

    with pytest.raises(CameraConfigurationError, match="Disparity data required for point cloud generation"):
        await backend.capture_point_cloud()


@pytest.mark.asyncio
async def test_capture_point_cloud_converts_grayscale_filters_invalid_points_and_downsamples():
    backend = _bare_backend()
    calibration = Mock()
    calibration.Q = np.eye(4, dtype=np.float64)
    calibration.calibrate_disparity.return_value = np.array([[1.0, 2.0], [0.0, 4.0]], dtype=np.float32)
    backend._calibration = calibration
    backend.capture = AsyncMock(
        return_value=StereoGrabResult(
            intensity=np.array([[10, 20], [30, 40]], dtype=np.uint8),
            disparity=np.array([[1, 2], [0, 4]], dtype=np.uint16),
            timestamp=1.0,
            frame_number=8,
            disparity_calibrated=None,
            has_intensity=True,
            has_disparity=True,
        )
    )

    points_3d = np.array(
        [
            [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
            [[np.inf, 0.0, 1.0], [7.0, 8.0, 9.0]],
        ],
        dtype=np.float32,
    )

    with patch(
        "mindtrace.hardware.stereo_cameras.backends.basler.basler_stereo_ace.cv2.reprojectImageTo3D",
        return_value=points_3d,
    ):
        cloud = await backend.capture_point_cloud(include_colors=True, downsample_factor=2)

    calibration.calibrate_disparity.assert_called_once()
    assert cloud.num_points == 2
    assert cloud.has_colors is True
    assert cloud.points.shape == (2, 3)
    assert cloud.colors.shape == (2, 3)
    assert np.all(np.isfinite(cloud.points))
    assert np.all((cloud.colors >= 0.0) & (cloud.colors <= 1.0))


@pytest.mark.asyncio
async def test_close_logs_errors_without_raising():
    backend = _bare_backend()
    backend._camera.IsGrabbing.return_value = True

    async def fail_run_blocking(func, *args, **kwargs):
        raise RuntimeError("close failed")

    backend._run_blocking = fail_run_blocking

    await backend.close()

    assert backend._is_open is True
    backend.logger.error.assert_called_once()
