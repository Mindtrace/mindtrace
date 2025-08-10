import numpy as np
import pytest

from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConnectionError,
    CameraTimeoutError,
)


@pytest.mark.asyncio
async def test_async_camera_configure_and_capture():
    manager = AsyncCameraManager(include_mocks=True)
    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        assert names
        name = names[0]

        cam = await manager.open(name)
        assert cam.is_connected

        # Configure exposure
        ok = await cam.set_exposure(1000)
        assert ok is True
        exp = await cam.get_exposure()
        assert isinstance(exp, float)

        # Capture single image
        img = await cam.capture()
        assert isinstance(img, np.ndarray)
        assert img.ndim == 3

        # Simple HDR capture (2 levels, no images back)
        res = await cam.capture_hdr(exposure_levels=2, return_images=False)
        assert isinstance(res, bool)
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_configure_all_settings(monkeypatch):
    manager = AsyncCameraManager(include_mocks=True)
    try:
        name = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][0]
        cam = await manager.open(name)

        # Patch backend methods to exercise all configure branches
        backend = cam.backend

        async def _set_exp(v):
            return True

        backend.set_exposure = _set_exp  # type: ignore[attr-defined]
        backend.set_gain = lambda v: True  # type: ignore[attr-defined]
        backend.set_ROI = lambda x, y, w, h: True  # type: ignore[attr-defined]

        async def _set_tm(v):
            return True

        backend.set_triggermode = _set_tm  # type: ignore[attr-defined]
        backend.set_pixel_format = lambda v: True  # type: ignore[attr-defined]

        async def _set_wb(v):
            return True

        backend.set_auto_wb_once = _set_wb  # type: ignore[attr-defined]
        backend.set_image_quality_enhancement = lambda v: True  # type: ignore[attr-defined]

        ok = await cam.configure(
            exposure=1234,
            gain=1.5,
            roi=(1, 2, 3, 4),
            trigger_mode="continuous",
            pixel_format="BGR8",
            white_balance="auto",
            image_enhancement=True,
        )
        assert ok is True
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_capture_retries_then_success(monkeypatch):
    manager = AsyncCameraManager(include_mocks=True)
    try:
        name = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][0]
        cam = await manager.open(name)

        # Speed up retry sleeps
        import mindtrace.hardware.cameras.core.async_camera as ac

        async def _noop_sleep(_delay, *a, **k):
            return None

        monkeypatch.setattr(ac.asyncio, "sleep", _noop_sleep, raising=False)

        attempts = {"n": 0}

        async def _cap():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise CameraTimeoutError("timeout")
            import numpy as np

            return True, np.zeros((8, 8, 3), dtype=np.uint8)

        cam.backend.retrieve_retry_count = 3  # type: ignore[attr-defined]
        monkeypatch.setattr(cam.backend, "capture", _cap, raising=False)

        img = await cam.capture()
        assert img is not None
    finally:
        await manager.close(None)


@pytest.mark.parametrize(
    "exc_cls",
    [CameraTimeoutError, CameraCaptureError, CameraConnectionError],
)
@pytest.mark.asyncio
async def test_async_camera_capture_exhausts_raises(exc_cls, monkeypatch):
    manager = AsyncCameraManager(include_mocks=True)
    try:
        name = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][0]
        cam = await manager.open(name)

        import mindtrace.hardware.cameras.core.async_camera as ac

        async def _noop_sleep(_delay, *a, **k):
            return None

        monkeypatch.setattr(ac.asyncio, "sleep", _noop_sleep, raising=False)

        async def _cap_fail():
            raise exc_cls("boom")

        cam.backend.retrieve_retry_count = 2  # type: ignore[attr-defined]
        monkeypatch.setattr(cam.backend, "capture", _cap_fail, raising=False)

        with pytest.raises(exc_cls):
            await cam.capture()
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_capture_generic_exception_exhausts(monkeypatch):
    manager = AsyncCameraManager(include_mocks=True)
    try:
        name = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][0]
        cam = await manager.open(name)

        import mindtrace.hardware.cameras.core.async_camera as ac

        async def _noop_sleep(_delay, *a, **k):
            return None

        monkeypatch.setattr(ac.asyncio, "sleep", _noop_sleep, raising=False)

        async def _cap_fail():
            raise RuntimeError("oops")

        cam.backend.retrieve_retry_count = 2  # type: ignore[attr-defined]
        monkeypatch.setattr(cam.backend, "capture", _cap_fail, raising=False)

        with pytest.raises(RuntimeError):
            await cam.capture()
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_hdr_partial_success_and_failure(monkeypatch):
    manager = AsyncCameraManager(include_mocks=True)
    try:
        name = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][0]
        cam = await manager.open(name)

        # Speed HDR settle sleep
        import mindtrace.hardware.cameras.core.async_camera as ac

        async def _noop_sleep(_delay, *a, **k):
            return None

        monkeypatch.setattr(ac.asyncio, "sleep", _noop_sleep, raising=False)

        # Setup backend methods
        async def _get_exp():
            return 1000.0

        async def _get_range():
            return [100.0, 100000.0]

        async def _set_exp(v):
            return True

        import numpy as np

        async def _cap_ok():
            return True, np.zeros((4, 4, 3), dtype=np.uint8)

        async def _cap_fail():
            return False, None

        # Partial success: two levels, one ok, one fail
        monkeypatch.setattr(cam.backend, "get_exposure", _get_exp, raising=False)
        monkeypatch.setattr(cam.backend, "get_exposure_range", _get_range, raising=False)
        monkeypatch.setattr(cam.backend, "set_exposure", _set_exp, raising=False)

        # Alternate between ok and fail
        calls = {"i": 0}

        async def _cap_alt():
            calls["i"] += 1
            return await (_cap_ok() if calls["i"] % 2 == 1 else _cap_fail())

        monkeypatch.setattr(cam.backend, "capture", _cap_alt, raising=False)

        imgs = await cam.capture_hdr(exposure_levels=3, return_images=True)
        assert isinstance(imgs, list)
        assert len(imgs) >= 1

        # All fail path -> raises CameraCaptureError
        async def _cap_all_fail():
            return False, None

        monkeypatch.setattr(cam.backend, "capture", _cap_all_fail, raising=False)
        with pytest.raises(CameraCaptureError):
            await cam.capture_hdr(exposure_levels=2, return_images=False)
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_async_context_manager(monkeypatch):
    manager = AsyncCameraManager(include_mocks=True)
    try:
        name = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][0]
        cam = await manager.open(name)
        async with cam as entered:
            assert entered is cam
    finally:
        await manager.close(None)
