"""High-value behavioral tests for BaslerStereoAceBackend methods."""

from __future__ import annotations

from unittest.mock import Mock

import numpy as np
import pytest

from mindtrace.hardware.core.exceptions import CameraConfigurationError, CameraConnectionError
from mindtrace.hardware.stereo_cameras.backends.basler.basler_stereo_ace import BaslerStereoAceBackend


class _Param:
    def __init__(self, value):
        self.Value = value

    def GetValue(self):
        return self.Value

    def GetSymbolics(self):
        return ["RGB8", "Mono8"]


class _TriggerSoftware:
    def __init__(self):
        self.executed = False

    def Execute(self):
        self.executed = True


class _FakeCamera:
    def __init__(self):
        self.BslDepthMinDepth = _Param(0.2)
        self.BslDepthMaxDepth = _Param(3.0)
        self.BslIlluminationMode = _Param("AlwaysActive")
        self.BinningHorizontal = _Param(1)
        self.BinningVertical = _Param(1)
        self.BslDepthQuality = _Param("Normal")
        self.PixelFormat = _Param("RGB8")
        self.ExposureTime = _Param(1000.0)
        self.Gain = _Param(1.0)
        self.TriggerMode = _Param("Off")
        self.TriggerSource = _Param("Software")
        self.TriggerSelector = _Param("FrameStart")
        self.TriggerSoftware = _TriggerSoftware()
        self._grabbing = False

    def IsGrabbing(self):
        return self._grabbing

    def StartGrabbing(self, _):
        self._grabbing = True

    def StopGrabbing(self):
        self._grabbing = False

    def Close(self):
        self._closed = True


@pytest.fixture
def backend():
    b = BaslerStereoAceBackend.__new__(BaslerStereoAceBackend)
    b.logger = Mock()
    b._is_open = True
    b._camera = _FakeCamera()
    b._grab_strategy = object()
    b._calibration = Mock()
    b._op_timeout_s = 1.0

    async def _run_blocking(func, *args, **kwargs):
        return func(*args, **kwargs)

    b._run_blocking = _run_blocking
    return b


@pytest.mark.asyncio
async def test_set_and_get_depth_range(backend):
    await backend.set_depth_range(0.5, 4.0)
    got = await backend.get_depth_range()
    assert got == (0.5, 4.0)


@pytest.mark.asyncio
async def test_set_illumination_mode_validation_and_roundtrip(backend):
    with pytest.raises(CameraConfigurationError):
        await backend.set_illumination_mode("invalid")

    await backend.set_illumination_mode("AlternateActive")
    assert await backend.get_illumination_mode() == "AlternateActive"


@pytest.mark.asyncio
async def test_binning_depth_quality_and_gain_exposure_roundtrip(backend):
    await backend.set_binning(2, 3)
    await backend.set_depth_quality("Full")
    await backend.set_exposure_time(5555.0)
    await backend.set_gain(3.5)

    assert await backend.get_binning() == (2, 3)
    assert await backend.get_depth_quality() == "Full"
    assert await backend.get_exposure_time() == 5555.0
    assert await backend.get_gain() == 3.5


@pytest.mark.asyncio
async def test_set_pixel_format_validates_available(backend):
    with pytest.raises(CameraConfigurationError, match="not available"):
        await backend.set_pixel_format("BayerRG8")

    await backend.set_pixel_format("Mono8")
    assert await backend.get_pixel_format() == "Mono8"


@pytest.mark.asyncio
async def test_trigger_mode_set_get_and_start_execute(backend):
    await backend.set_trigger_mode("trigger")
    assert await backend.get_trigger_mode() == "trigger"

    # start_grabbing should change camera grabbing state
    await backend.start_grabbing()
    assert backend._camera.IsGrabbing() is True

    await backend.execute_trigger()
    assert backend._camera.TriggerSoftware.executed is True

    await backend.set_trigger_mode("continuous")
    assert await backend.get_trigger_mode() == "continuous"


@pytest.mark.asyncio
async def test_configure_handles_special_and_generic_params(backend):
    await backend.configure(
        trigger_mode="trigger",
        depth_range=(0.3, 2.5),
        illumination_mode="AlternateActive",
        binning=(2, 2),
        depth_quality="Full",
        ExposureTime=7777.0,
        Gain=2.2,
    )

    assert backend._camera.TriggerMode.Value == "On"
    assert backend._camera.BslDepthMinDepth.Value == 0.3
    assert backend._camera.BslDepthMaxDepth.Value == 2.5
    assert backend._camera.BslIlluminationMode.Value == "AlternateActive"
    assert backend._camera.BinningHorizontal.Value == 2
    assert backend._camera.BinningVertical.Value == 2
    assert backend._camera.BslDepthQuality.Value == "Full"
    assert backend._camera.ExposureTime.Value == 7777.0
    assert backend._camera.Gain.Value == 2.2


@pytest.mark.asyncio
async def test_capture_uses_calibration_when_enabled(backend):
    backend._calibration.calibrate_disparity.return_value = np.array([[1.0]], dtype=np.float32)

    async def fake_run_blocking(func, *args, **kwargs):
        name = getattr(func, "__name__", "")
        if name == "_capture_frame":
            return {
                "intensity": np.zeros((1, 1), dtype=np.uint8),
                "disparity": np.ones((1, 1), dtype=np.uint16),
                "timestamp": 1.2,
                "frame_number": 5,
                "has_intensity": True,
                "has_disparity": True,
            }
        return func(*args, **kwargs)

    backend._run_blocking = fake_run_blocking
    result = await backend.capture(calibrate_disparity=True)

    assert result.frame_number == 5
    assert result.disparity_calibrated is not None
    backend._calibration.calibrate_disparity.assert_called_once()


@pytest.mark.asyncio
async def test_close_transitions_state_without_raise(backend):
    backend._camera._grabbing = True
    await backend.close()
    assert backend.is_open is False


@pytest.mark.asyncio
async def test_methods_require_open_camera_for_reads(backend):
    backend._is_open = False
    backend._camera = None

    with pytest.raises(CameraConnectionError):
        await backend.get_exposure_time()
    with pytest.raises(CameraConnectionError):
        await backend.get_gain()
    with pytest.raises(CameraConnectionError):
        await backend.get_pixel_format()
