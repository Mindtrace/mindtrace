"""Unit tests for synchronous StereoCamera wrapper."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

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


def test_submit_uses_run_coroutine_threadsafe():
    cam = StereoCamera.__new__(StereoCamera)
    cam._loop = Mock()
    future = Mock()
    future.result.return_value = "done"

    async def _sample():
        return "value"

    coro = _sample()
    try:
        with patch("asyncio.run_coroutine_threadsafe", return_value=future) as run_threadsafe:
            assert cam._submit(coro) == "done"

        run_threadsafe.assert_called_once_with(coro, cam._loop)
        future.result.assert_called_once_with()
    finally:
        coro.close()


def test_close_stops_owned_loop_and_joins_thread():
    cam = _make_sync_wrapper()
    cam._backend.close = AsyncMock(return_value=None)
    cam._owns_loop_thread = True
    cam._loop = Mock()
    cam._loop_thread = Mock()

    cam.close()

    cam._backend.close.assert_awaited_once_with()
    cam._loop.call_soon_threadsafe.assert_called_once_with(cam._loop.stop)
    cam._loop_thread.join.assert_called_once_with(timeout=2)


def test_context_manager_closes_on_exit():
    cam = _make_sync_wrapper()

    with patch.object(cam, "close") as close:
        assert cam.__enter__() is cam
        cam.__exit__(None, None, None)

    close.assert_called_once_with()


@pytest.mark.parametrize(
    ("method_name", "args", "kwargs", "return_value"),
    [
        ("capture_point_cloud", (), {"include_colors": False, "downsample_factor": 3}, "pcd"),
        ("set_depth_range", (0.5, 3.0), {}, None),
        ("set_illumination_mode", ("AlternateActive",), {}, None),
        ("set_binning", (2, 4), {}, None),
        ("set_depth_quality", ("Full",), {}, None),
        ("set_pixel_format", ("RGB8",), {}, None),
        ("set_exposure_time", (15000.0,), {}, None),
        ("set_gain", (2.5,), {}, None),
    ],
)
def test_wrapper_methods_delegate_to_async_backend(method_name, args, kwargs, return_value):
    cam = _make_sync_wrapper()
    backend_method = AsyncMock(return_value=return_value)
    setattr(cam._backend, method_name, backend_method)

    result = getattr(cam, method_name)(*args, **kwargs)

    backend_method.assert_awaited_once_with(*args, **kwargs)
    assert result == return_value


def test_repr_uses_status():
    cam = _make_sync_wrapper()
    assert "status=open" in repr(cam)
