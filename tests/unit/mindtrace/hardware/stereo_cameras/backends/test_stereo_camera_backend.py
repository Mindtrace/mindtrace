"""Unit tests for the abstract StereoCameraBackend base class."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, Mock

import pytest

from mindtrace.hardware.core.exceptions import CameraConnectionError, CameraTimeoutError, HardwareOperationError
from mindtrace.hardware.stereo_cameras.backends.stereo_camera_backend import StereoCameraBackend
from mindtrace.hardware.stereo_cameras.core.models import StereoCalibrationData, StereoGrabResult


class MinimalStereoBackend(StereoCameraBackend):
    """Concrete test double for exercising base-class behavior."""

    @staticmethod
    def discover():
        return ["SER123", "SER456"]

    async def initialize(self) -> bool:
        self._is_open = True
        return True

    async def capture(
        self,
        timeout_ms: int = 20000,
        enable_intensity: bool = True,
        enable_disparity: bool = True,
        calibrate_disparity: bool = True,
    ) -> StereoGrabResult:
        return StereoGrabResult(
            intensity=None,
            disparity=None,
            timestamp=0.0,
            frame_number=1,
            has_intensity=enable_intensity,
            has_disparity=enable_disparity,
        )

    async def close(self) -> None:
        self._is_open = False

    @property
    def name(self) -> str:
        return f"MinimalStereoBackend:{self.serial_number or 'unknown'}"


def make_backend(serial_number: str | None = "SER123") -> MinimalStereoBackend:
    backend = MinimalStereoBackend(serial_number=serial_number, op_timeout_s=0.05)
    backend.logger = Mock()
    return backend


@pytest.mark.asyncio
async def test_run_blocking_returns_function_result():
    backend = make_backend()

    result = await backend._run_blocking(lambda x, y: x + y, 2, 3)

    assert result == 5


@pytest.mark.asyncio
async def test_run_blocking_wraps_timeout():
    backend = make_backend()

    def slow():
        time.sleep(0.02)

    with pytest.raises(CameraTimeoutError, match="timed out"):
        await backend._run_blocking(slow, timeout=0.001)


@pytest.mark.asyncio
async def test_run_blocking_wraps_generic_errors():
    backend = make_backend()

    def fail():
        raise RuntimeError("boom")

    with pytest.raises(HardwareOperationError, match="Stereo camera operation failed: boom"):
        await backend._run_blocking(fail)


@pytest.mark.asyncio
async def test_run_blocking_reraises_domain_errors():
    backend = make_backend()

    def fail():
        raise HardwareOperationError("already wrapped")

    with pytest.raises(HardwareOperationError, match="already wrapped"):
        await backend._run_blocking(fail)


@pytest.mark.asyncio
async def test_discover_async_uses_subclass_discover():
    result = await MinimalStereoBackend.discover_async()

    assert result == ["SER123", "SER456"]


def test_discover_detailed_default_uses_serial_numbers(monkeypatch):
    monkeypatch.setattr(StereoCameraBackend, "discover", staticmethod(lambda: ["A", "B"]))

    result = StereoCameraBackend.discover_detailed()

    assert result == [{"serial_number": "A"}, {"serial_number": "B"}]


@pytest.mark.asyncio
async def test_discover_detailed_async_wraps_default_discovery(monkeypatch):
    monkeypatch.setattr(StereoCameraBackend, "discover", staticmethod(lambda: ["X1"]))

    result = await MinimalStereoBackend.discover_detailed_async()

    assert result == [{"serial_number": "X1"}]


@pytest.mark.asyncio
async def test_get_calibration_returns_cached_calibration():
    backend = make_backend()
    backend._calibration = StereoCalibrationData.from_camera_params(
        {
            "Scan3dBaseline": 0.1,
            "Scan3dFocalLength": 1000.0,
            "Scan3dPrincipalPointU": 320.0,
            "Scan3dPrincipalPointV": 240.0,
            "Scan3dCoordinateScale": 1.0,
            "Scan3dCoordinateOffset": 0.0,
        }
    )

    calibration = await backend.get_calibration()

    assert calibration is backend._calibration


@pytest.mark.asyncio
async def test_get_calibration_raises_when_not_loaded():
    backend = make_backend()
    backend._calibration = None

    with pytest.raises(CameraConnectionError, match="Calibration not loaded"):
        await backend.get_calibration()


@pytest.mark.asyncio
async def test_get_trigger_modes_returns_default_modes():
    backend = make_backend()

    assert await backend.get_trigger_modes() == ["continuous", "trigger"]


@pytest.mark.asyncio
async def test_async_context_manager_initializes_and_closes():
    backend = make_backend()
    backend.initialize = AsyncMock(return_value=True)
    backend.close = AsyncMock(return_value=None)

    async with backend as entered:
        assert entered is backend

    backend.initialize.assert_awaited_once()
    backend.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "args", "kwargs", "warning_fragment", "error_fragment"),
    [
        (
            "capture_point_cloud",
            (),
            {"include_colors": True, "downsample_factor": 1},
            "not optimized",
            "not implemented",
        ),
        ("configure", (), {"ExposureTime": 1000}, "configure not implemented", "configure not supported"),
        ("set_exposure_time", (1000.0,), {}, "set_exposure_time not implemented", "set_exposure_time not supported"),
        ("get_exposure_time", (), {}, "get_exposure_time not implemented", "get_exposure_time not supported"),
        ("set_gain", (2.0,), {}, "set_gain not implemented", "set_gain not supported"),
        ("get_gain", (), {}, "get_gain not implemented", "get_gain not supported"),
        ("set_depth_range", (0.2, 3.0), {}, "set_depth_range not implemented", "set_depth_range not supported"),
        ("get_depth_range", (), {}, "get_depth_range not implemented", "get_depth_range not supported"),
        ("set_depth_quality", ("Full",), {}, "set_depth_quality not implemented", "set_depth_quality not supported"),
        ("get_depth_quality", (), {}, "get_depth_quality not implemented", "get_depth_quality not supported"),
        (
            "set_illumination_mode",
            ("AlwaysActive",),
            {},
            "set_illumination_mode not implemented",
            "set_illumination_mode not supported",
        ),
        (
            "get_illumination_mode",
            (),
            {},
            "get_illumination_mode not implemented",
            "get_illumination_mode not supported",
        ),
        ("set_binning", (2, 2), {}, "set_binning not implemented", "set_binning not supported"),
        ("get_binning", (), {}, "get_binning not implemented", "get_binning not supported"),
        ("set_pixel_format", ("Mono8",), {}, "set_pixel_format not implemented", "set_pixel_format not supported"),
        ("get_pixel_format", (), {}, "get_pixel_format not implemented", "get_pixel_format not supported"),
        ("set_trigger_mode", ("trigger",), {}, "set_trigger_mode not implemented", "set_trigger_mode not supported"),
        ("get_trigger_mode", (), {}, "get_trigger_mode not implemented", "get_trigger_mode not supported"),
        ("start_grabbing", (), {}, "start_grabbing not implemented", "start_grabbing not supported"),
        ("execute_trigger", (), {}, "execute_trigger not implemented", "execute_trigger not supported"),
    ],
)
async def test_default_optional_methods_warn_and_raise(
    method_name: str,
    args: tuple,
    kwargs: dict,
    warning_fragment: str,
    error_fragment: str,
):
    backend = make_backend()

    with pytest.raises(NotImplementedError, match=error_fragment):
        await getattr(backend, method_name)(*args, **kwargs)

    backend.logger.warning.assert_called_once()
    assert warning_fragment in backend.logger.warning.call_args[0][0]


@pytest.mark.asyncio
async def test_abstract_base_methods_raise_when_called_directly():
    backend = make_backend()

    with pytest.raises(NotImplementedError):
        StereoCameraBackend.discover()
    with pytest.raises(NotImplementedError):
        await StereoCameraBackend.initialize(backend)
    with pytest.raises(NotImplementedError):
        await StereoCameraBackend.capture(backend)
    with pytest.raises(NotImplementedError):
        await StereoCameraBackend.close(backend)
    with pytest.raises(NotImplementedError):
        StereoCameraBackend.name.fget(backend)


def test_repr_and_properties_reflect_state():
    backend = make_backend(serial_number="SER999")
    assert backend.is_open is False
    assert backend.calibration is None
    assert repr(backend) == "MinimalStereoBackend(serial_number=SER999, status=closed)"

    backend._is_open = True
    assert repr(backend) == "MinimalStereoBackend(serial_number=SER999, status=open)"


def test_del_warns_when_backend_destroyed_while_open():
    backend = make_backend(serial_number="SER999")
    backend._is_open = True

    backend.__del__()

    backend.logger.warning.assert_called_once()
    assert "destroyed without proper cleanup" in backend.logger.warning.call_args[0][0]
    backend._is_open = False
