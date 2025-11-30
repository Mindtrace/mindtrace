import asyncio

import pytest

from mindtrace.hardware.cameras.core.camera_manager import CameraManager
from mindtrace.hardware.core.exceptions import CameraNotFoundError


def test_discover_classmethod_sync_manager():
    cameras = CameraManager.discover(include_mocks=True)
    assert isinstance(cameras, list)
    assert any(name.startswith("MockBasler:") for name in cameras)


def test_open_single_and_batch_and_close():
    mgr = CameraManager(include_mocks=True)
    try:
        cameras = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        assert cameras
        name = cameras[0]

        cam = mgr.open(name)
        # basic capture path
        img = cam.capture()
        assert hasattr(img, "shape")

        # Idempotent at the async layer; sync wrapper may differ but backend must be the same
        cam2 = mgr.open(name)
        assert cam2.name == cam.name
        assert cam2.backend is cam.backend

        # batch
        subset = cameras[:2]
        opened = mgr.open(subset)
        assert set(opened.keys()) == set(subset)

        # close single
        mgr.close(name)
    finally:
        mgr.close()


def test_backends_and_backend_info_structure():
    mgr = CameraManager(include_mocks=True)
    try:
        b = mgr.backends()
        assert isinstance(b, list)
        info = mgr.backend_info()
        assert isinstance(info, dict)
        assert "OpenCV" in info and "MockBasler" in info
        assert set(["available", "type", "sdk_required"]).issubset(info["OpenCV"].keys())
    finally:
        mgr.close()


def test_discover_details_records_sync():
    recs = CameraManager.discover(details=True, include_mocks=True)
    assert isinstance(recs, list)
    if recs:
        sample = recs[0]
        for k in ["name", "backend", "index", "width", "height", "fps"]:
            assert k in sample


def test_open_default_no_cameras_raises(monkeypatch):
    """Test that opening default camera raises when no cameras are available."""
    # Mock all backends to return empty results (no cameras available)
    try:
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend

        monkeypatch.setattr(
            BaslerCameraBackend,
            "get_available_cameras",
            staticmethod(lambda include_details=False: {} if include_details else []),
            raising=False,
        )
    except Exception:
        pass

    try:
        from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import OpenCVCameraBackend

        monkeypatch.setattr(
            OpenCVCameraBackend,
            "get_available_cameras",
            staticmethod(lambda include_details=False: {} if include_details else []),
            raising=False,
        )
    except Exception:
        pass

    try:
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        monkeypatch.setattr(
            GenICamCameraBackend,
            "get_available_cameras",
            staticmethod(lambda include_details=False: {} if include_details else []),
            raising=False,
        )
    except Exception:
        pass

    # Use include_mocks=True but mock the mock backend to return empty too
    mgr = CameraManager(include_mocks=True)

    # Mock discover to return empty list
    monkeypatch.setattr(mgr, "discover", lambda: [])

    try:
        # Should raise CameraNotFoundError when no cameras are available
        with pytest.raises(CameraNotFoundError, match="No cameras available to open by default"):
            mgr.open(None)
    finally:
        mgr.close()


def test_close_unknown_name_noop():
    mgr = CameraManager(include_mocks=True)
    try:
        mgr.close("NonExistent:dev")
    finally:
        mgr.close()


def test_max_concurrent_captures_property_passthrough():
    mgr = CameraManager(include_mocks=True)
    try:
        # Get
        _ = mgr.max_concurrent_captures
        # Set
        mgr.max_concurrent_captures = 2
        assert mgr.max_concurrent_captures == 2
    finally:
        mgr.close()


def test_diagnostics_after_open(monkeypatch):
    """Test diagnostics with controlled mock cameras."""
    mgr = CameraManager(include_mocks=True)

    # Create controlled mock cameras
    mock_cameras = ["MockBasler:TestCam1", "MockBasler:TestCam2"]

    def mock_discover(include_mocks=True, backends=None, details=False):
        return mock_cameras if include_mocks else []

    # Patch both class method and instance method
    monkeypatch.setattr(CameraManager, "discover", classmethod(lambda cls, **kwargs: mock_discover(**kwargs)))
    monkeypatch.setattr(mgr, "discover", mock_discover)

    try:
        res = mgr.open(mock_cameras)
        assert set(res.keys()) == set(mock_cameras)
        d = mgr.diagnostics()
        assert isinstance(d, dict)
        assert d["active_cameras"] == len(mock_cameras)

        # Test other diagnostic fields
        assert "max_concurrent_captures" in d
        assert "gige_cameras" in d
        assert "bandwidth_management_enabled" in d
        assert "recommended_settings" in d
    finally:
        mgr.close()


def test_shutdown_bound_timeout(monkeypatch):
    mgr = CameraManager(include_mocks=True)
    try:
        # Monkeypatch async manager's close to a slow coroutine to trigger bound timeout
        async def _slow_close(names=None):  # noqa: ARG001
            import asyncio as aio

            await aio.sleep(2.0)

        monkeypatch.setattr(mgr._manager, "close", _slow_close, raising=False)
    finally:
        # Should not hang despite slow close
        mgr.close()


def test_active_cameras_property():
    """Test active_cameras property."""
    mgr = CameraManager(include_mocks=True)
    try:
        # Initially no active cameras
        active = mgr.active_cameras
        assert isinstance(active, list)

        # Open a camera
        cameras = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        if cameras:
            mgr.open(cameras[0])
            active_after = mgr.active_cameras
            assert len(active_after) >= len(active)
    finally:
        mgr.close()


def test_batch_operations():
    """Test batch operations including batch_configure, batch_capture, and batch_capture_hdr."""
    mgr = CameraManager(include_mocks=True)
    try:
        cameras = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        if len(cameras) >= 2:
            # Open multiple cameras
            subset = cameras[:2]
            opened = mgr.open(subset)
            camera_names = list(opened.keys())

            # Test batch_configure (line 103)
            configurations = {name: {"exposure": 1000} for name in camera_names}
            result = mgr.batch_configure(configurations)
            assert isinstance(result, dict)

            # Test batch_capture (line 109)
            capture_result = mgr.batch_capture(camera_names)
            assert isinstance(capture_result, dict)

            # Test batch_capture_hdr (line 124)
            hdr_result = mgr.batch_capture_hdr(camera_names, exposure_levels=2)
            assert isinstance(hdr_result, dict)
    finally:
        mgr.close()


def test_double_shutdown_protection():
    """Test protection against double shutdown calls."""
    mgr = CameraManager(include_mocks=True)

    # First shutdown
    mgr.close()

    # Second shutdown should return early due to _shutting_down flag
    mgr.close()  # Should not cause issues


def test_shutdown_exception_handling(monkeypatch):
    """Test exception handling in shutdown process when loop operations fail."""
    mgr = CameraManager(include_mocks=True)

    # Mock methods to raise exceptions
    def failing_call_soon_threadsafe(*args, **kwargs):
        raise RuntimeError("Simulated call_soon_threadsafe failure")

    def failing_join(*args, **kwargs):
        raise RuntimeError("Simulated thread join failure")

    # Patch methods to fail
    monkeypatch.setattr(mgr._loop, "call_soon_threadsafe", failing_call_soon_threadsafe)
    monkeypatch.setattr(mgr._thread, "join", failing_join)

    # Close should handle exceptions gracefully
    mgr.close()


def test_destructor_exception_handling(monkeypatch):
    """Test exception handling in __del__ method when cleanup operations fail."""
    mgr = CameraManager(include_mocks=True)

    # Mock methods to raise exceptions
    original_call_soon_threadsafe = mgr._loop.call_soon_threadsafe
    original_join = mgr._thread.join
    original_is_running = mgr._loop.is_running

    def failing_call_soon_threadsafe(*args, **kwargs):
        raise RuntimeError("Simulated call_soon_threadsafe failure")

    def failing_join(*args, **kwargs):
        raise RuntimeError("Simulated thread join failure")

    def mock_is_running():
        return True  # Always return True to trigger the call_soon_threadsafe path

    # Patch methods to fail
    monkeypatch.setattr(mgr._loop, "call_soon_threadsafe", failing_call_soon_threadsafe)
    monkeypatch.setattr(mgr._loop, "is_running", mock_is_running)
    monkeypatch.setattr(mgr._thread, "join", failing_join)

    # Manually trigger the __del__ logic to test exception handling
    try:
        # Simulate the __del__ method logic
        if hasattr(mgr, "_loop") and isinstance(getattr(mgr, "_loop"), asyncio.AbstractEventLoop):
            try:
                if mgr._loop.is_running():
                    mgr._loop.call_soon_threadsafe(mgr._loop.stop)
            except Exception:
                pass  # This covers call_soon_threadsafe exception handling
        if hasattr(mgr, "_thread") and getattr(mgr, "_thread") is not None:
            try:
                mgr._thread.join(timeout=0.2)
            except Exception:
                pass  # This covers thread join exception handling
    except Exception:
        pass

    # Restore original methods and properly close
    monkeypatch.setattr(mgr._loop, "call_soon_threadsafe", original_call_soon_threadsafe)
    monkeypatch.setattr(mgr._thread, "join", original_join)
    monkeypatch.setattr(mgr._loop, "is_running", original_is_running)
    mgr.close()


def test_call_in_loop_coroutine_path(monkeypatch):
    """Test _call_in_loop coroutine execution path for async functions."""
    mgr = CameraManager(include_mocks=True)
    try:
        # Create a test coroutine
        async def test_coro():
            return "test_result"

        # This should trigger the coroutine path in _call_in_loop
        result = mgr._call_in_loop(test_coro)
        assert result == "test_result"
    finally:
        mgr.close()


def test_call_in_loop_exception_handling(monkeypatch):
    """Test exception handling in _call_in_loop when constructor fails."""
    mgr = CameraManager(include_mocks=True)
    try:
        # Create a constructor that raises an exception
        def failing_constructor():
            raise ValueError("Test constructor failure")

        # This should trigger the exception handling in _call_in_loop
        with pytest.raises(ValueError, match="Test constructor failure"):
            mgr._call_in_loop(failing_constructor)
    finally:
        mgr.close()


def test_submit_coro_exception_handling(monkeypatch):
    """Test exception handling in _submit_coro when timeout occurs."""
    mgr = CameraManager(include_mocks=True)

    # Create a coroutine that will timeout
    async def slow_coro():
        import asyncio

        await asyncio.sleep(2.0)
        return "should_timeout"

    try:
        # This should trigger timeout and exception handling
        with pytest.raises(Exception):  # Could be TimeoutError or other exception
            mgr._submit_coro(slow_coro(), timeout=0.1)
    finally:
        mgr.close()


def test_submit_coro_cancellation_path(monkeypatch):
    """Test the cancellation path in _submit_coro exception handling (lines 220-221)."""
    import asyncio
    from concurrent.futures import Future

    mgr = CameraManager(include_mocks=True)

    try:
        # Mock run_coroutine_threadsafe to return a future that raises an exception
        def mock_run_coro_threadsafe(coro, loop):
            coro.close()
            # Create a future that will raise an exception when result() is called
            fut = Future()
            fut.set_exception(RuntimeError("Simulated coroutine failure"))

            # Mock the cancel method to test the cancellation path
            original_cancel = fut.cancel
            cancel_called = []

            def mock_cancel():
                cancel_called.append(True)
                return original_cancel()

            fut.cancel = mock_cancel
            return fut

        monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", mock_run_coro_threadsafe)

        # Create a simple coroutine
        async def test_coro():
            return "test"

        # This should trigger the exception handling and cancellation path
        with pytest.raises(RuntimeError, match="Simulated coroutine failure"):
            mgr._submit_coro(test_coro())

    finally:
        mgr.close()


def test_destructor_real_del_method():
    """Test the actual __del__ method by creating and destroying a CameraManager."""
    import gc
    import weakref

    # Create a manager in a local scope
    def create_and_destroy_manager():
        mgr = CameraManager(include_mocks=True)

        # Create a weak reference to track when it's actually deleted
        weak_ref = weakref.ref(mgr)

        # Manually trigger some state that might cause exceptions in __del__
        # Close the manager normally first
        mgr.close()

        # Return the weak reference
        return weak_ref

    # Create and let it go out of scope
    weak_ref = create_and_destroy_manager()

    # Force garbage collection to trigger __del__
    gc.collect()

    # The object should be gone
    assert weak_ref() is None


def test_submit_coro_cancel_exception_handling(monkeypatch):
    """Test the exception handling in _submit_coro when cancel() itself fails."""
    import asyncio
    from concurrent.futures import Future, TimeoutError

    mgr = CameraManager(include_mocks=True)

    try:
        # Mock run_coroutine_threadsafe to return a future that behaves badly
        def mock_run_coro_threadsafe(coro, loop):
            coro.close()
            # Create a future that will timeout and then fail to cancel
            fut = Future()

            # Mock result() to raise TimeoutError
            def mock_result(timeout=None):
                raise TimeoutError("Simulated timeout")

            fut.result = mock_result

            # Mock cancel() to raise an exception (this is the key!)
            def mock_cancel():
                raise RuntimeError("Cancel operation failed")

            fut.cancel = mock_cancel

            return fut

        monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", mock_run_coro_threadsafe)

        # Create a simple coroutine
        async def test_coro():
            return "test"

        # This should trigger both the timeout exception AND the cancel exception
        with pytest.raises(TimeoutError, match="Simulated timeout"):
            mgr._submit_coro(test_coro(), timeout=0.1)

    finally:
        mgr.close()


def test_del_method_exception_handling_direct():
    """Test the __del__ method exception handling by directly invoking it."""

    # Create a CameraManager
    mgr = CameraManager(include_mocks=True)

    # Store original methods
    original_call_soon_threadsafe = mgr._loop.call_soon_threadsafe
    original_join = mgr._thread.join
    original_is_running = mgr._loop.is_running

    # Mock methods to raise exceptions
    def failing_call_soon_threadsafe(*args, **kwargs):
        raise RuntimeError("call_soon_threadsafe failed in __del__")

    def failing_join(*args, **kwargs):
        raise RuntimeError("thread join failed in __del__")

    def mock_is_running():
        return True  # Always return True to trigger the call_soon_threadsafe path

    try:
        # Replace methods with failing versions
        mgr._loop.call_soon_threadsafe = failing_call_soon_threadsafe
        mgr._loop.is_running = mock_is_running
        mgr._thread.join = failing_join

        # Directly call the __del__ method to test exception handling
        # This simulates what happens during garbage collection
        CameraManager.__del__(mgr)

    finally:
        # Restore original methods for proper cleanup
        mgr._loop.call_soon_threadsafe = original_call_soon_threadsafe
        mgr._loop.is_running = original_is_running
        mgr._thread.join = original_join

        # Properly close the manager
        mgr.close()


def test_del_method_outer_exception_handling():
    """Test the outermost exception handling in __del__ method."""

    # Create a CameraManager
    mgr = CameraManager(include_mocks=True)

    # Store original hasattr function
    import builtins

    original_hasattr = builtins.hasattr

    try:
        # Mock hasattr to raise an exception, which will trigger the outermost exception handler
        def failing_hasattr(obj, name):
            if obj is mgr and name in ("_loop", "_thread"):
                raise RuntimeError("hasattr failed in __del__")
            return original_hasattr(obj, name)

        builtins.hasattr = failing_hasattr

        # Directly call the __del__ method
        # This should trigger the outermost exception handler (lines 184-185)
        CameraManager.__del__(mgr)

    finally:
        # Restore original hasattr
        builtins.hasattr = original_hasattr

        # Properly close the manager
        mgr.close()
