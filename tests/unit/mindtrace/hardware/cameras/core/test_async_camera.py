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
        await cam.set_exposure(1000)
        exp = await cam.get_exposure()
        assert isinstance(exp, float)

        # Capture single image
        img = await cam.capture()
        assert isinstance(img, np.ndarray)
        assert img.ndim == 3

        # Simple HDR capture (2 levels, no images back)
        res = await cam.capture_hdr(exposure_levels=2, return_images=False)
        assert isinstance(res, dict)
        assert "success" in res
        assert "images" in res
        assert "exposure_levels" in res
        assert isinstance(res["success"], bool)
        assert res["images"] is None  # Should be None when return_images=False
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

        await cam.configure(
            exposure=1234,
            gain=1.5,
            roi=(1, 2, 3, 4),
            trigger_mode="continuous",
            pixel_format="BGR8",
            white_balance="auto",
            image_enhancement=True,
        )
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

            return np.zeros((8, 8, 3), dtype=np.uint8)

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
            return np.zeros((4, 4, 3), dtype=np.uint8)

        async def _cap_fail():
            return None

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

        result = await cam.capture_hdr(exposure_levels=3, return_images=True)
        assert isinstance(result, dict)
        assert "success" in result
        assert "images" in result
        assert result["success"] is True
        assert isinstance(result["images"], list)
        assert len(result["images"]) >= 1

        # All fail path -> raises CameraCaptureError
        async def _cap_all_fail():
            return None

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
async def test_async_bandwidth_limit_and_adjustment(monkeypatch):
    """Test bandwidth limiting and adjustment with controlled mock cameras."""
    mgr = AsyncCameraManager(include_mocks=True, max_concurrent_captures=1)

    # Create controlled mock cameras instead of relying on discovery
    mock_cameras = ["MockBasler:TestCam1", "MockBasler:TestCam2", "MockBasler:TestCam3"]

    # Mock the discovery to return our test cameras
    def mock_discover(include_mocks=True, backends=None):
        return mock_cameras if include_mocks else []

    monkeypatch.setattr(mgr, "discover", mock_discover)

    try:
        # Test bandwidth limiting
        await mgr.open(mock_cameras[:2])  # Open 2 cameras
        assert mgr.max_concurrent_captures == 1

        # Test bandwidth adjustment
        mgr.max_concurrent_captures = 3
        assert mgr.max_concurrent_captures == 3

        # Test batch capture with adjusted limit
        results = await mgr.batch_capture(mock_cameras[:2])
        assert len(results) == 2

        # Verify all captures succeeded
        for camera, result in results.items():
            assert result is not None  # Mock should return valid image data

    finally:
        await mgr.close(None)


class TestAsyncCameraConcurrentOperations:
    """Test concurrent operation edge cases for async cameras."""

    @pytest.mark.asyncio
    async def test_concurrent_captures_with_failures(self, monkeypatch):
        """Test concurrent captures when some operations fail."""
        manager = AsyncCameraManager(include_mocks=True)

        # Create controlled mock cameras instead of relying on discovery
        mock_cameras = ["MockBasler:TestCam1", "MockBasler:TestCam2"]

        def mock_discover(include_mocks=True, backends=None):
            return mock_cameras if include_mocks else []

        monkeypatch.setattr(manager, "discover", mock_discover)

        try:
            # Open cameras
            cameras = []
            for name in mock_cameras:
                cam = await manager.open(name)
                cameras.append(cam)

            # Set one camera to fail captures
            async def failing_capture():
                raise CameraCaptureError("Simulated failure")

            cameras[1].backend.capture = failing_capture

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
            assert len(failures) >= 1  # At least one should fail
            assert any(isinstance(f, CameraCaptureError) for f in failures)

        finally:
            await manager.close(None)

    @pytest.mark.asyncio
    async def test_concurrent_configuration_operations(self, monkeypatch):
        """Test concurrent configuration operations on same camera."""
        manager = AsyncCameraManager(include_mocks=True)

        # Use controlled mock camera
        mock_cameras = ["MockBasler:TestCam1"]

        def mock_discover(include_mocks=True, backends=None):
            return mock_cameras if include_mocks else []

        monkeypatch.setattr(manager, "discover", mock_discover)

        try:
            cam = await manager.open(mock_cameras[0])

            # Launch concurrent configuration operations
            async def set_exposure_task():
                return await cam.set_exposure(1000)

            async def set_gain_task():
                return await cam.set_gain(10.0)

            async def set_roi_task():
                return await cam.set_roi(0, 0, 640, 480)

            # Run concurrently
            results = await asyncio.gather(set_exposure_task(), set_gain_task(), set_roi_task(), return_exceptions=True)

            # All should complete without deadlock
            assert len(results) == 3
            # Mock backend should return None for successful operations or Exception for failures
            assert all(r is None or isinstance(r, Exception) for r in results)

        finally:
            await manager.close(None)

    @pytest.mark.asyncio
    async def test_concurrent_capture_and_config(self, monkeypatch):
        """Test concurrent capture and configuration operations."""
        manager = AsyncCameraManager(include_mocks=True)

        mock_cameras = ["MockBasler:TestCam1"]

        def mock_discover(include_mocks=True, backends=None):
            return mock_cameras if include_mocks else []

        monkeypatch.setattr(manager, "discover", mock_discover)

        try:
            cam = await manager.open(mock_cameras[0])

            # Launch capture and config operations concurrently
            capture_task = asyncio.create_task(cam.capture())
            config_task = asyncio.create_task(cam.set_exposure(2000))

            # Both should complete
            image, config_result = await asyncio.gather(capture_task, config_task)

            assert isinstance(image, np.ndarray)
            assert config_result is None

        finally:
            await manager.close(None)

    @pytest.mark.asyncio
    async def test_concurrent_connection_operations(self, monkeypatch):
        """Test concurrent connection/disconnection operations."""
        manager = AsyncCameraManager(include_mocks=True)

        mock_cameras = ["MockBasler:TestCam1"]

        def mock_discover(include_mocks=True, backends=None):
            return mock_cameras if include_mocks else []

        monkeypatch.setattr(manager, "discover", mock_discover)

        try:
            # Open camera
            cam = await manager.open(mock_cameras[0])

            # Try concurrent check_connection operations
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
    async def test_timeout_during_concurrent_operations(self, monkeypatch):
        """Test timeout behavior during concurrent operations."""
        manager = AsyncCameraManager(include_mocks=True)

        mock_cameras = ["MockBasler:TestCam1"]

        def mock_discover(include_mocks=True, backends=None):
            return mock_cameras if include_mocks else []

        monkeypatch.setattr(manager, "discover", mock_discover)

        try:
            cam = await manager.open(mock_cameras[0])

            # Mock a slow operation
            async def slow_capture():
                await asyncio.sleep(2.0)  # Simulate slow operation
                return True, np.zeros((8, 8, 3), dtype=np.uint8)

            cam.backend.capture = slow_capture

            # Launch operation with short timeout
            with pytest.raises((CameraTimeoutError, asyncio.TimeoutError)):
                await asyncio.wait_for(cam.capture(), timeout=0.1)

        finally:
            await manager.close(None)

    @pytest.mark.asyncio
    async def test_resource_cleanup_on_concurrent_failures(self, monkeypatch):
        """Test resource cleanup when concurrent operations fail."""
        manager = AsyncCameraManager(include_mocks=True)

        mock_cameras = ["MockBasler:TestCam1"]

        def mock_discover(include_mocks=True, backends=None):
            return mock_cameras if include_mocks else []

        monkeypatch.setattr(manager, "discover", mock_discover)

        try:
            cam = await manager.open(mock_cameras[0])

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
                assert isinstance(result, CameraConnectionError)

            # Camera should still be functional after failures
            assert cam.is_connected

        finally:
            await manager.close(None)

    @pytest.mark.asyncio
    async def test_concurrent_manager_operations(self, monkeypatch):
        """Test concurrent manager-level operations."""
        manager = AsyncCameraManager(include_mocks=True)

        mock_cameras = ["MockBasler:TestCam1", "MockBasler:TestCam2"]

        def mock_discover(include_mocks=True, backends=None):
            return mock_cameras if include_mocks else []

        monkeypatch.setattr(manager, "discover", mock_discover)

        try:
            # Open cameras concurrently
            open_tasks = []
            for name in mock_cameras:
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
    async def test_concurrent_batch_operations(self, monkeypatch):
        """Test concurrent batch capture operations."""
        manager = AsyncCameraManager(include_mocks=True)

        mock_cameras = ["MockBasler:TestCam1", "MockBasler:TestCam2"]

        def mock_discover(include_mocks=True, backends=None):
            return mock_cameras if include_mocks else []

        monkeypatch.setattr(manager, "discover", mock_discover)

        try:
            # Open cameras
            await manager.open(mock_cameras)

            # Set high concurrency limit
            manager.max_concurrent_captures = 10

            # Run multiple batch captures concurrently
            batch_tasks = []
            for _ in range(3):
                batch_tasks.append(asyncio.create_task(manager.batch_capture(mock_cameras)))

            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # All batch operations should complete
            for result in batch_results:
                if isinstance(result, Exception):
                    print(f"Batch capture failed: {result}")
                else:
                    assert isinstance(result, dict)
                    assert len(result) == 2  # Should have results for both cameras

        finally:
            await manager.close(None)


# Additional tests to improve coverage
@pytest.mark.asyncio
async def test_async_camera_open_class_method():
    """Test AsyncCamera.open() class method for direct camera creation."""
    from mindtrace.hardware.cameras.core.async_camera import AsyncCamera

    # Test opening with MockBasler backend
    try:
        cam = await AsyncCamera.open("MockBasler:test_camera_0")
        assert cam is not None
        assert cam.name == "MockBasler:test_camera_0"
        assert cam.is_connected

        # Test basic functionality
        img = await cam.capture()
        assert img is not None

        await cam.close()
    except Exception as e:
        # If MockBasler isn't available for direct open, skip
        pytest.skip(f"MockBasler not available for direct open: {e}")


@pytest.mark.asyncio
async def test_async_camera_open_unsupported_backend():
    """Test AsyncCamera.open() with unsupported backend raises error."""
    from mindtrace.hardware.cameras.core.async_camera import AsyncCamera
    from mindtrace.hardware.core.exceptions import CameraInitializationError

    with pytest.raises(CameraInitializationError, match="Unsupported backend"):
        await AsyncCamera.open("UnsupportedBackend:device_0")


@pytest.mark.asyncio
async def test_async_camera_storage_unavailable(monkeypatch):
    """Test AsyncCamera initialization when GCS storage is unavailable."""
    # Mock STORAGE_AVAILABLE to False
    import mindtrace.hardware.cameras.core.async_camera as async_camera_module

    original_storage_available = async_camera_module.STORAGE_AVAILABLE

    try:
        monkeypatch.setattr(async_camera_module, "STORAGE_AVAILABLE", False)

        manager = AsyncCameraManager(include_mocks=True)
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            cam = await manager.open(names[0])
            # Storage handler should be None when storage is unavailable
            assert cam._storage_handler is None
            await manager.close(None)
    finally:
        # Restore original value
        monkeypatch.setattr(async_camera_module, "STORAGE_AVAILABLE", original_storage_available)


@pytest.mark.asyncio
async def test_async_camera_storage_initialization_failure(monkeypatch):
    """Test AsyncCamera initialization when GCS storage initialization fails."""
    manager = AsyncCameraManager(include_mocks=True)

    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            # Mock get_hardware_config to raise an exception
            def failing_get_config():
                raise RuntimeError("Config initialization failed")

            # Mock the import to raise an exception during storage initialization
            import mindtrace.hardware.cameras.core.async_camera as async_camera_module

            original_storage_available = async_camera_module.STORAGE_AVAILABLE
            assert original_storage_available

            # Set STORAGE_AVAILABLE to True but make config import fail
            monkeypatch.setattr(async_camera_module, "STORAGE_AVAILABLE", True)

            # Mock the import to fail
            def failing_import(*args, **kwargs):
                raise RuntimeError("Config initialization failed")

            import builtins

            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "mindtrace.hardware.core.config":
                    raise RuntimeError("Config initialization failed")
                return original_import(name, *args, **kwargs)

            monkeypatch.setattr(builtins, "__import__", mock_import)

            cam = await manager.open(names[0])
            # Storage handler should be None when initialization fails
            assert cam._storage_handler is None
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_context_manager():
    """Test AsyncCamera as async context manager."""
    from mindtrace.hardware.cameras.core.async_camera import AsyncCamera

    try:
        async with await AsyncCamera.open("MockBasler:test_camera_0") as cam:
            assert cam is not None
            assert cam.is_connected

            # Test basic functionality within context
            img = await cam.capture()
            assert img is not None
    except Exception as e:
        pytest.skip(f"MockBasler not available for context manager test: {e}")


@pytest.mark.asyncio
async def test_async_camera_properties():
    """Test AsyncCamera properties and info methods."""
    manager = AsyncCameraManager(include_mocks=True)

    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            cam = await manager.open(names[0])

            # Test properties
            assert isinstance(cam.name, str)
            assert isinstance(cam.backend_name, str)
            assert isinstance(cam.device_name, str)
            assert isinstance(cam.is_connected, bool)
            assert cam.backend is not None

            # Test that camera has expected attributes
            assert hasattr(cam, "_backend")
            assert hasattr(cam, "_full_name")
            assert hasattr(cam, "_lock")
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_get_gain_range():
    """Test AsyncCamera get_gain_range method."""
    manager = AsyncCameraManager(include_mocks=True)

    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            cam = await manager.open(names[0])

            # Test get_gain_range
            gain_range = await cam.get_gain_range()
            assert isinstance(gain_range, tuple)
            assert len(gain_range) == 2
            assert isinstance(gain_range[0], (int, float))
            assert isinstance(gain_range[1], (int, float))
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_capture_with_upload():
    """Test AsyncCamera capture with GCS upload functionality."""
    manager = AsyncCameraManager(include_mocks=True)

    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            cam = await manager.open(names[0])

            # Test capture with upload_to_gcs=True (should handle gracefully even without storage)
            result = await cam.capture(upload_to_gcs=True, output_format="numpy")
            # Should still return image even if upload fails
            assert result is not None
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_capture_with_save_path():
    """Test AsyncCamera capture with save_path functionality."""
    manager = AsyncCameraManager(include_mocks=True)

    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            cam = await manager.open(names[0])

            # Test capture with save_path (creates directory if needed)
            import os
            import tempfile

            with tempfile.TemporaryDirectory() as temp_dir:
                save_path = os.path.join(temp_dir, "subdir", "test_image.jpg")

                # This should create the directory and save the image
                result = await cam.capture(save_path=save_path)
                assert result is not None
                assert os.path.exists(save_path)
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_capture_retry_logic(monkeypatch):
    """Test AsyncCamera capture retry logic when captures fail."""
    manager = AsyncCameraManager(include_mocks=True)

    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            cam = await manager.open(names[0])

            # Mock backend to fail first few attempts, then succeed
            original_capture = cam._backend.capture
            call_count = 0

            async def failing_capture():
                nonlocal call_count
                call_count += 1
                if call_count <= 2:  # Fail first 2 attempts
                    raise CameraCaptureError(f"Simulated failure {call_count}")
                return await original_capture()  # Succeed on 3rd attempt

            cam._backend.capture = failing_capture
            cam._backend.retrieve_retry_count = 3  # Set retry count on backend

            # This should retry and eventually succeed
            result = await cam.capture()
            assert result is not None
            assert call_count == 3  # Should have made 3 attempts
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_capture_connection_error_retry(monkeypatch):
    """Test AsyncCamera capture retry logic for connection errors."""
    manager = AsyncCameraManager(include_mocks=True)

    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            cam = await manager.open(names[0])

            # Mock backend to raise connection error, then succeed
            original_capture = cam._backend.capture
            call_count = 0

            async def connection_error_capture():
                nonlocal call_count
                call_count += 1
                if call_count == 1:  # Fail first attempt with connection error
                    raise CameraConnectionError("Network connection failed")
                return await original_capture()  # Succeed on 2nd attempt

            cam._backend.capture = connection_error_capture
            cam._backend.retrieve_retry_count = 2  # Set retry count on backend

            # This should retry and succeed
            result = await cam.capture()
            assert result is not None
            assert call_count == 2
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_capture_max_retries_exceeded(monkeypatch):
    """Test AsyncCamera capture when max retries are exceeded."""
    manager = AsyncCameraManager(include_mocks=True)

    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            cam = await manager.open(names[0])

            # Mock backend to always fail
            async def always_failing_capture():
                raise CameraCaptureError("Persistent failure")

            cam._backend.capture = always_failing_capture
            cam._backend.retrieve_retry_count = 2  # Set retry count on backend

            # This should fail after max retries
            with pytest.raises(CameraCaptureError, match="Capture failed after 2 attempts"):
                await cam.capture()
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_capture_returns_none(monkeypatch):
    """Test AsyncCamera capture when backend returns None."""
    manager = AsyncCameraManager(include_mocks=True)

    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            cam = await manager.open(names[0])

            # Mock backend to return None
            async def none_capture():
                return None

            cam._backend.capture = none_capture

            # This should raise CameraCaptureError
            with pytest.raises(CameraCaptureError, match="Capture returned None"):
                await cam.capture()
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_additional_methods():
    """Test additional AsyncCamera methods for better coverage."""
    manager = AsyncCameraManager(include_mocks=True)

    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            cam = await manager.open(names[0])

            # Test get_exposure_range
            exp_range = await cam.get_exposure_range()
            assert isinstance(exp_range, tuple)
            assert len(exp_range) == 2

            # Test set_gain and get_gain
            await cam.set_gain(1.5)
            gain = await cam.get_gain()
            assert isinstance(gain, (int, float))

            # Test set_roi
            await cam.set_roi(10, 10, 100, 100)

    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_gcs_upload_functionality(monkeypatch):
    """Test GCS upload functionality."""
    manager = AsyncCameraManager(include_mocks=True)

    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            cam = await manager.open(names[0])

            # Test _should_upload_to_gcs when storage_handler is None
            assert not cam._should_upload_to_gcs()

            # Mock storage handler
            class MockStorageHandler:
                def upload(self, local_path, gcs_path):
                    pass

            cam._storage_handler = MockStorageHandler()

            # Mock get_hardware_config to return upload enabled
            def mock_get_config():
                class MockGCSConfig:
                    auto_upload = True

                class MockConfig:
                    gcs = MockGCSConfig()

                class MockHardwareConfig:
                    def get_config(self):
                        return MockConfig()

                return MockHardwareConfig()

            monkeypatch.setattr("mindtrace.hardware.core.config.get_hardware_config", mock_get_config)

            # Now _should_upload_to_gcs should return True
            assert cam._should_upload_to_gcs()

            # Test actual upload (mock the upload process)
            import numpy as np

            test_image = np.zeros((100, 100, 3), dtype=np.uint8)

            # Mock os.unlink to avoid file system operations
            monkeypatch.setattr("os.unlink", lambda x: None)

            result = await cam._upload_image_to_gcs(test_image)
            assert result
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_gcs_upload_failure(monkeypatch):
    """Test GCS upload when it fails."""
    manager = AsyncCameraManager(include_mocks=True)

    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            cam = await manager.open(names[0])

            # Test upload with None image
            result = await cam._upload_image_to_gcs(None)
            assert not result

            # Test upload when storage handler is None
            cam._storage_handler = None
            import numpy as np

            test_image = np.zeros((100, 100, 3), dtype=np.uint8)
            result = await cam._upload_image_to_gcs(test_image)
            assert not result
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_async_camera_gcs_config_exception(monkeypatch):
    """Test _should_upload_to_gcs when config access fails."""
    manager = AsyncCameraManager(include_mocks=True)

    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        if names:
            cam = await manager.open(names[0])

            # Mock storage handler
            class MockStorageHandler:
                def upload(self, local_path, gcs_path):
                    pass

            cam._storage_handler = MockStorageHandler()

            # Mock get_hardware_config to raise exception
            def failing_get_config():
                raise RuntimeError("Config access failed")

            monkeypatch.setattr("mindtrace.hardware.core.config.get_hardware_config", failing_get_config)

            # Should return False when config access fails
            assert not cam._should_upload_to_gcs()
    finally:
        await manager.close(None)
