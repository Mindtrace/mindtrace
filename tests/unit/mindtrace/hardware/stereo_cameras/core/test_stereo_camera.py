"""Unit tests for synchronous StereoCamera wrapper."""

import asyncio
from unittest.mock import AsyncMock, Mock

from mindtrace.hardware.stereo_cameras.core.stereo_camera import StereoCamera


def _make_sync_wrapper():
    cam = StereoCamera.__new__(StereoCamera)
    cam._backend = Mock()
    cam._backend.name = "BaslerStereoAce:999"
    cam._backend.calibration = None
    cam._backend.is_open = True
    cam._owns_loop_thread = False
    cam._loop = None
    cam._loop_thread = None

    def _submit(coro):
        return asyncio.run(coro)

    cam._submit = _submit
    return cam


def test_property_proxies():
    cam = _make_sync_wrapper()
    assert cam.name == "BaslerStereoAce:999"
    assert cam.is_open is True
    assert cam.calibration is None


def test_capture_delegates_to_backend():
    cam = _make_sync_wrapper()
    cam._backend.capture = AsyncMock(return_value="ok")

    result = cam.capture(timeout_ms=123)

    assert result == "ok"
    cam._backend.capture.assert_awaited_once()


def test_configure_delegates_kwargs():
    cam = _make_sync_wrapper()
    cam._backend.configure = AsyncMock(return_value=None)

    cam.configure(ExposureTime=1000, Gain=2.0)

    cam._backend.configure.assert_awaited_once_with(ExposureTime=1000, Gain=2.0)


def test_repr_uses_status():
    cam = _make_sync_wrapper()
    assert "status=open" in repr(cam)
