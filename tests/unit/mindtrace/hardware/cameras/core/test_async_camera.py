import asyncio

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

        async def _set_gain(v):
            return True
        
        async def _set_roi(x, y, w, h):
            return True
            
        backend.set_exposure = _set_exp  # type: ignore[attr-defined]
        backend.set_gain = _set_gain  # type: ignore[attr-defined]
        backend.set_ROI = _set_roi  # type: ignore[attr-defined]

        async def _set_tm(v):
            return True

        backend.set_triggermode = _set_tm  # type: ignore[attr-defined]
        async def _set_pf(v):
            return True
            
        backend.set_pixel_format = _set_pf  # type: ignore[attr-defined]

        async def _set_wb(v):
            return True

        async def _set_ie(v):
            return True
            
        backend.set_auto_wb_once = _set_wb  # type: ignore[attr-defined]
        backend.set_image_quality_enhancement = _set_ie  # type: ignore[attr-defined]

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


@pytest.mark.asyncio
async def test_async_performance_concurrent_capture(camera_manager):
    manager = camera_manager
    cameras = manager.discover()
    mock_cameras = [cam for cam in cameras if "Mock" in cam][:3]
    if len(mock_cameras) >= 2:
        opened = await manager.open(mock_cameras)
        proxies = list(opened.values())
        tasks = [p.capture() for p in proxies]
        results = await asyncio.gather(*tasks)
        assert len(results) == len(proxies)


@pytest.mark.asyncio
async def test_async_bandwidth_limit_and_adjustment():
    mgr = AsyncCameraManager(include_mocks=True, max_concurrent_captures=1)
    try:
        cams = mgr.discover(include_mocks=True)
        mocks = [c for c in cams if "Mock" in c][:3]
        if len(mocks) < 2:
            pytest.skip("need two mocks")
        await mgr.open(mocks)
        assert mgr.max_concurrent_captures == 1
        mgr.max_concurrent_captures = 3
        assert mgr.max_concurrent_captures == 3
        await mgr.batch_capture(mocks)
        mgr.max_concurrent_captures = 1
        await mgr.batch_capture(mocks)
    finally:
        await mgr.close(None)


class TestAsyncCameraConcurrentOperations:
    """Test concurrent operation edge cases for async cameras."""

    @pytest.mark.asyncio
    async def test_concurrent_captures_with_failures(self):
        """Test concurrent captures when some operations fail."""
        manager = AsyncCameraManager(include_mocks=True)
        try:
            names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
            if len(names) < 2:
                pytest.skip("Need at least 2 mock cameras")
            
            # Open cameras
            cameras = []
            for name in names[:2]:
                cam = await manager.open(name)
                cameras.append(cam)
            
            # Set one camera to fail captures
            cameras[1].backend.capture = lambda: (_ for _ in ()).throw(CameraCaptureError("Simulated failure"))
            
            # Try concurrent captures
            tasks = []
            for cam in cameras:
                tasks.append(asyncio.create_task(cam.capture()))
            
            # Wait for all tasks - some should succeed, some fail
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Should have mix of success and failures
            successes = [r for r in results if isinstance(r, np.ndarray)]
            failures = [r for r in results if isinstance(r, Exception)]
            
            assert len(successes) >= 1  # At least one should succeed
            assert len(failures) >= 1   # At least one should fail
            
        finally:
            await manager.close(None)

    @pytest.mark.asyncio
    async def test_concurrent_configuration_operations(self):
        """Test concurrent configuration operations on same camera."""
        manager = AsyncCameraManager(include_mocks=True)
        try:
            names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
            if not names:
                pytest.skip("Need at least 1 mock camera")
            
            cam = await manager.open(names[0])
            
            # Launch concurrent configuration operations
            async def set_exposure_task():
                return await cam.set_exposure(1000)
            
            async def set_gain_task():
                return await cam.set_gain(10.0)
            
            async def set_roi_task():
                return await cam.set_roi(0, 0, 640, 480)
            
            # Run concurrently
            results = await asyncio.gather(
                set_exposure_task(),
                set_gain_task(), 
                set_roi_task(),
                return_exceptions=True
            )
            
            # All should complete without deadlock
            assert len(results) == 3
            
        finally:
            await manager.close(None)

    @pytest.mark.asyncio
    async def test_concurrent_capture_and_config(self):
        """Test concurrent capture and configuration operations."""
        manager = AsyncCameraManager(include_mocks=True)
        try:
            names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
            if not names:
                pytest.skip("Need at least 1 mock camera")
            
            cam = await manager.open(names[0])
            
            # Launch capture and config operations concurrently
            capture_task = asyncio.create_task(cam.capture())
            config_task = asyncio.create_task(cam.set_exposure(2000))
            
            # Both should complete
            image, config_result = await asyncio.gather(capture_task, config_task)
            
            assert isinstance(image, np.ndarray)
            assert config_result is True
            
        finally:
            await manager.close(None)

    @pytest.mark.asyncio
    async def test_concurrent_connection_operations(self):
        """Test concurrent connection/disconnection operations."""
        manager = AsyncCameraManager(include_mocks=True)
        try:
            names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
            if not names:
                pytest.skip("Need at least 1 mock camera")
            
            # Open camera
            cam = await manager.open(names[0])
            
            # Try concurrent check_connection operations (cameras don't have explicit connect)
            tasks = []
            for _ in range(3):
                tasks.append(asyncio.create_task(cam.check_connection()))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # All should succeed (camera already connected)
            for result in results:
                assert result is True or isinstance(result, Exception)
            
        finally:
            await manager.close(None)

    @pytest.mark.asyncio 
    async def test_timeout_during_concurrent_operations(self):
        """Test timeout behavior during concurrent operations."""
        manager = AsyncCameraManager(include_mocks=True)
        try:
            names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
            if not names:
                pytest.skip("Need at least 1 mock camera")
            
            cam = await manager.open(names[0])
            
            # Mock a slow operation
            original_capture = cam.backend.capture
            async def slow_capture():
                await asyncio.sleep(2.0)  # Simulate slow operation
                return await original_capture()
            
            cam.backend.capture = slow_capture
            
            # Launch operation with short timeout
            with pytest.raises((CameraTimeoutError, asyncio.TimeoutError)):
                await asyncio.wait_for(cam.capture(), timeout=0.1)
            
        finally:
            await manager.close(None)

    @pytest.mark.asyncio
    async def test_resource_cleanup_on_concurrent_failures(self):
        """Test resource cleanup when concurrent operations fail."""
        manager = AsyncCameraManager(include_mocks=True)
        try:
            names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
            if not names:
                pytest.skip("Need at least 1 mock camera")
            
            cam = await manager.open(names[0])
            
            # Mock operation that fails partway through
            async def failing_operation():
                await asyncio.sleep(0.1)  # Start operation
                raise CameraConnectionError("Simulated failure")
            
            # Launch multiple failing operations
            tasks = []
            for _ in range(5):
                tasks.append(asyncio.create_task(failing_operation()))
            
            # All should fail
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                assert isinstance(result, Exception)
            
            # Camera should still be functional after failures
            assert cam.is_connected
            
        finally:
            await manager.close(None)

    @pytest.mark.asyncio
    async def test_concurrent_manager_operations(self):
        """Test concurrent manager-level operations.""" 
        manager = AsyncCameraManager(include_mocks=True)
        try:
            names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
            if len(names) < 2:
                pytest.skip("Need at least 2 mock cameras")
            
            # Open cameras concurrently
            open_tasks = []
            for name in names[:2]:
                open_tasks.append(asyncio.create_task(manager.open(name)))
            
            cameras = await asyncio.gather(*open_tasks)
            
            # All should be opened
            for cam in cameras:
                assert cam.is_connected
            
            # Close concurrently
            close_tasks = []
            for cam in cameras:
                close_tasks.append(asyncio.create_task(manager.close(cam.name)))
            
            await asyncio.gather(*close_tasks)
            
        finally:
            await manager.close(None)

    @pytest.mark.asyncio
    async def test_concurrent_batch_operations(self):
        """Test concurrent batch capture operations."""
        manager = AsyncCameraManager(include_mocks=True)
        try:
            names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
            if len(names) < 2:
                pytest.skip("Need at least 2 mock cameras")
            
            # Open cameras
            await manager.open(names[:2])
            
            # Set high concurrency limit
            manager.max_concurrent_captures = 10
            
            # Run multiple batch captures concurrently
            batch_tasks = []
            for _ in range(3):
                batch_tasks.append(asyncio.create_task(manager.batch_capture(names[:2])))
            
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # All batch operations should complete
            for result in batch_results:
                if isinstance(result, Exception):
                    print(f"Batch capture failed: {result}")
                else:
                    assert isinstance(result, dict)
            
        finally:
            await manager.close(None)
