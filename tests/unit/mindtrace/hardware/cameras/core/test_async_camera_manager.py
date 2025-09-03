import asyncio
import numpy as np
import pytest

from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager
from mindtrace.hardware.core.exceptions import CameraConfigurationError, CameraConnectionError


@pytest.mark.asyncio
async def test_discover_classmethod_includes_mocks():
    cameras = AsyncCameraManager.discover(include_mocks=True)
    assert isinstance(cameras, list)
    # Should list mock basler names when include_mocks=True
    assert any(name.startswith("MockBasler:") for name in cameras)


@pytest.mark.asyncio
async def test_open_idempotent_and_close():
    manager = AsyncCameraManager(include_mocks=True)
    try:
        names = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)
        assert len(names) > 0
        name = names[0]

        cam1 = await manager.open(name)
        cam2 = await manager.open(name)
        assert cam1 is cam2  # idempotent
        assert name in manager.active_cameras

        # Close single
        await manager.close(name)
        assert name not in manager.active_cameras

        # Re-open for batch test
        opened = await manager.open([name])
        assert set(opened.keys()) == {name}
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_batch_capture_with_mock_backend():
    manager = AsyncCameraManager(include_mocks=True, max_concurrent_captures=2)
    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][:3]
        if len(names) < 2:
            pytest.skip("Not enough mock cameras discovered")

        await manager.open(names)

        # Ensure captures complete and produce ndarray images
        results = await manager.batch_capture(names)
        assert set(results.keys()) == set(names)
        for img in results.values():
            assert isinstance(img, np.ndarray)
            assert img.ndim == 3
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_diagnostics_structure():
    manager = AsyncCameraManager(include_mocks=True, max_concurrent_captures=2)
    try:
        info = manager.diagnostics()
        assert "max_concurrent_captures" in info
        assert "active_cameras" in info
        assert "gige_cameras" in info
        assert "recommended_settings" in info

        # After opening, active_cameras should reflect count
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][:2]
        await manager.open(names)
        info2 = manager.diagnostics()
        assert info2["active_cameras"] == len(names)
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_camera_proxy_operations(camera_manager):
    manager = camera_manager
    cameras = manager.discover()
    mock_cameras = [cam for cam in cameras if "MockBasler" in cam]
    if mock_cameras:
        camera_name = mock_cameras[0]
        await manager.open(camera_name)
        camera_proxy = await manager.open(camera_name)
        assert camera_proxy is not None
        assert camera_proxy.name == camera_name
        assert camera_proxy.is_connected
        await camera_proxy.set_exposure(1000)
        image = await camera_proxy.capture()
        assert image is not None
        success = await camera_proxy.configure(exposure=20000, gain=2.0, trigger_mode="continuous")
        assert success is True
        exposure = await camera_proxy.get_exposure()
        assert exposure == 20000
        gain = camera_proxy.get_gain()
        assert gain == 2.0
        tm = await camera_proxy.get_trigger_mode()
        assert isinstance(tm, str)


@pytest.mark.asyncio
async def test_batch_operations(camera_manager):
    manager = camera_manager
    cameras = manager.discover()
    mock_cameras = [cam for cam in cameras if "Mock" in cam][:3]
    if len(mock_cameras) >= 2:
        opened = await manager.open(mock_cameras)
        assert set(opened.keys()) == set(mock_cameras)
        # re-open proxies and batch
        _ = await manager.open(mock_cameras)
        results = await manager.batch_configure({n: {"exposure": 15000} for n in mock_cameras})
        assert isinstance(results, dict)
        caps = await manager.batch_capture(mock_cameras)
        assert isinstance(caps, dict) and len(caps) == len(mock_cameras)


@pytest.mark.asyncio
async def test_manager_context_manager():
    async with AsyncCameraManager(include_mocks=True) as manager:
        cameras = manager.discover()
        assert isinstance(cameras, list)
        mock_cameras = [cam for cam in cameras if "Mock" in cam]
        if mock_cameras:
            camera_name = mock_cameras[0]
            await manager.open(camera_name)
            camera_proxy = await manager.open(camera_name)
            await camera_proxy.set_exposure(1000)
            image = await camera_proxy.capture()
            assert image is not None


@pytest.mark.asyncio
async def test_error_handling_and_idempotency(camera_manager):
    manager = camera_manager
    with pytest.raises(CameraConfigurationError):
        await manager.open("NonExistentCamera")
    cameras = manager.discover()
    if cameras:
        nm = cameras[0]
        first = await manager.open(nm)
        second = await manager.open(nm)
        assert first is second
        # after closing, capture should error
        await manager.close(nm)
        with pytest.raises(CameraConnectionError):
            await first.capture()


@pytest.mark.asyncio
async def test_discover_with_details_records():
    recs = AsyncCameraManager.discover(details=True, include_mocks=True)
    assert isinstance(recs, list)
    assert all(isinstance(r, dict) for r in recs)
    # Keys: name, backend, index, width, height, fps
    if recs:
        sample = recs[0]
        for k in ["name", "backend", "index", "width", "height", "fps"]:
            assert k in sample


@pytest.mark.asyncio
async def test_open_default_raises_when_no_devices():
    mgr = AsyncCameraManager(include_mocks=False)  # OpenCV returns empty via patches
    try:
        # Check if real cameras are available
        available_cameras = mgr.discover()
        if not available_cameras:
            # Only test for exception if no real cameras are present
            with pytest.raises(Exception):
                # Should raise because there are no default devices
                await mgr.open(None)
        else:
            # If real cameras exist, verify that open(None) succeeds and returns a camera
            cam = await mgr.open(None)
            assert cam is not None
            assert cam.name in available_cameras
            await mgr.close(cam.name)
    finally:
        await mgr.close(None)


@pytest.mark.asyncio
async def test_batch_open_partial_failure():
    mgr = AsyncCameraManager(include_mocks=True)
    try:
        valid = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
        assert valid
        targets = [valid[0], "UnknownBackend:dev"]
        opened = await mgr.open(targets)
        assert set(opened.keys()) == {valid[0]}
    finally:
        await mgr.close(None)


@pytest.mark.asyncio
async def test_close_unknown_name_noop():
    mgr = AsyncCameraManager(include_mocks=True)
    try:
        await mgr.close("NonExistentCamera")
    finally:
        await mgr.close(None)


@pytest.mark.asyncio
async def test_batch_capture_hdr_return_images():
    mgr = AsyncCameraManager(include_mocks=True, max_concurrent_captures=2)
    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][:2]
        if len(names) < 2:
            pytest.skip("Not enough mock cameras for HDR test")
        await mgr.open(names)
        res = await mgr.batch_capture_hdr(camera_names=names, exposure_levels=2, return_images=True)
        assert set(res.keys()) == set(names)
        for camera_name, hdr_result in res.items():
            assert isinstance(hdr_result, dict)
            assert "success" in hdr_result
            assert "images" in hdr_result
            assert "exposure_levels" in hdr_result
            if hdr_result["success"]:
                assert isinstance(hdr_result["images"], list)
    finally:
        await mgr.close(None)


@pytest.mark.asyncio
async def test_async_manager_context_manager():
    async with AsyncCameraManager(include_mocks=True) as m:
        cams = m.discover()
        assert isinstance(cams, list)


def test_discover_unknown_backend_returns_empty():
    lst = AsyncCameraManager.discover(backends=["DoesNotExist"], include_mocks=True)
    assert isinstance(lst, list)
    assert len(lst) == 0


@pytest.mark.asyncio
async def test_discover_opencv_details_with_device_dict(monkeypatch):
    # Return a dict so the details-building loop executes
    from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import OpenCVCameraBackend

    monkeypatch.setattr(
        OpenCVCameraBackend,
        "get_available_cameras",
        staticmethod(
            lambda include_details=False: {
                "opencv_camera_0": {"index": 0, "width": 640, "height": 480, "fps": 30.0}
            }
            if include_details
            else ["opencv_camera_0"]
        ),
    )

    recs = AsyncCameraManager.discover(details=True)
    assert any(r.get("name", "").startswith("OpenCV:") for r in recs)


def test_discover_opencv_list_mode(monkeypatch):
    from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import OpenCVCameraBackend

    monkeypatch.setattr(
        OpenCVCameraBackend, "get_available_cameras", staticmethod(lambda include_details=False: ["opencv_camera_0"]))
    names = AsyncCameraManager.discover(backends=["OpenCV"], details=False)
    assert names == ["OpenCV:opencv_camera_0"]


def test_discover_basler_details_via_mocked_backend(monkeypatch):
    class FakeBasler:
        @staticmethod
        def get_available_cameras():
            return ["B123"]

    monkeypatch.setattr(AsyncCameraManager, "_discover_backend", classmethod(lambda cls, n: (True, FakeBasler)))
    recs = AsyncCameraManager.discover(backends=["Basler"], details=True)
    assert recs and recs[0]["name"].startswith("Basler:")


def test_discover_mock_index_parse_fallback(monkeypatch):
    class FakeMockBasler:
        @staticmethod
        def get_available_cameras():
            return ["mock_name_no_index"]

    monkeypatch.setattr(AsyncCameraManager, "_get_mock_camera", classmethod(lambda cls, n: FakeMockBasler))
    recs = AsyncCameraManager.discover(backends=["MockBasler"], details=True, include_mocks=True)
    assert recs and recs[0]["index"] == -1


@pytest.mark.asyncio
async def test_open_default_prefers_opencv_with_mocked_backend(monkeypatch):
    mgr = AsyncCameraManager(include_mocks=True)
    try:
        # Make discover(["OpenCV"]) return a device
        orig_discover = mgr.discover

        def _disc(backends=None, details=False, include_mocks=False):  # noqa: ARG001
            if backends == ["OpenCV"]:
                return ["OpenCV:opencv_camera_0"]
            return []

        monkeypatch.setattr(AsyncCameraManager, "discover", classmethod(lambda cls, *a, **k: _disc(*a, **k)))

        class DummyBackend:
            async def initialize(self):
                return True, None, None

            async def setup_camera(self):
                return None

            async def check_connection(self):
                return True

            async def capture(self):
                return True, None

            async def close(self):
                return None

        monkeypatch.setattr(
            AsyncCameraManager,
            "_create_camera_instance",
            lambda self, backend, device, **kwargs: DummyBackend(),
            raising=False,
        )

        cam = await mgr.open(None)
        assert cam.name == "OpenCV:opencv_camera_0"
    finally:
        await mgr.close(None)


@pytest.mark.asyncio
async def test_max_concurrent_attr_fallback(monkeypatch):
    mgr = AsyncCameraManager(include_mocks=True)
    try:
        if hasattr(mgr, "_max_concurrent_captures"):
            delattr(mgr, "_max_concurrent_captures")
        assert mgr.max_concurrent_captures == 1
    finally:
        await mgr.close(None)


@pytest.mark.asyncio
async def test_batch_methods_baseexception_branch(monkeypatch):
    mgr = AsyncCameraManager(include_mocks=True)
    try:
        # Patch asyncio.gather in module namespace to return BaseException results
        import mindtrace.hardware.cameras.core.async_camera_manager as mod

        async def _fake_gather(*args, **kwargs):  # noqa: ARG001
            # Consume/close incoming coroutine objects to avoid warnings, then return BaseException-like results
            import asyncio as aio
            coros = []
            if args:
                if isinstance(args[0], (list, tuple)) and all(hasattr(x, "__await__") for x in args[0]):
                    coros = list(args[0])
                else:
                    coros = [a for a in args if hasattr(a, "__await__")]
            for c in coros:
                try:
                    c.close()
                except Exception:
                    pass
            await aio.sleep(0)
            return [RuntimeError("boom")]

        monkeypatch.setattr(mod.asyncio, "gather", _fake_gather, raising=False)

        # batch_configure
        res1 = await mgr.batch_configure({"MockBasler:cam": {"exposure": 1}})
        assert isinstance(res1, dict)

        # batch_capture
        res2 = await mgr.batch_capture(["MockBasler:cam"])
        assert isinstance(res2, dict)

        # batch_capture_hdr
        res3 = await mgr.batch_capture_hdr(["MockBasler:cam"], return_images=True)
        assert isinstance(res3, dict)
    finally:
        await mgr.close(None)


@pytest.mark.asyncio
async def test_manager_initialization(camera_manager):
    """Test camera manager initialization."""
    manager = camera_manager
    assert manager is not None
    backends = manager.backends()
    assert isinstance(backends, list)
    backend_info = manager.backend_info()
    assert isinstance(backend_info, dict)


@pytest.mark.asyncio
async def test_camera_discovery(camera_manager):
    """Test camera discovery functionality."""
    manager = camera_manager
    available = manager.__class__.discover(include_mocks=True)
    assert isinstance(available, list)
    mock_cameras = [cam for cam in available if "Mock" in cam]
    assert len(mock_cameras) > 0


@pytest.mark.asyncio
async def test_backend_specific_discovery(camera_manager):
    """Test backend-specific camera discovery functionality."""
    manager = camera_manager
    # Discover only MockBasler cameras
    basler_cameras = manager.__class__.discover(backends="MockBasler", include_mocks=True)
    assert isinstance(basler_cameras, list)
    for camera in basler_cameras:
        assert camera.startswith("MockBasler:")
    # Discover from multiple backends
    multi_backend_cameras = manager.__class__.discover(backends=["MockBasler", "OpenCV"], include_mocks=True)
    assert isinstance(multi_backend_cameras, list)
    for camera in multi_backend_cameras:
        assert camera.startswith("MockBasler:") or camera.startswith("OpenCV:")
    # Non-existent backend returns empty
    empty_cameras = manager.__class__.discover(backends="NonExistentBackend", include_mocks=True)
    assert isinstance(empty_cameras, list)
    assert len(empty_cameras) == 0
    # Invalid parameter type
    with pytest.raises(ValueError, match="Invalid backends parameter"):
        manager.__class__.discover(123, include_mocks=True)


@pytest.mark.asyncio
async def test_backend_specific_discovery_consistency(camera_manager):
    """Test that backend-specific discovery is consistent with full discovery."""
    manager = camera_manager
    all_cameras = manager.__class__.discover(include_mocks=True)
    
    # Filter out real hardware cameras for consistent testing
    mock_only_cameras = [cam for cam in all_cameras if "MockBasler" in cam or "OpenCV" not in cam]
    
    basler_cameras = manager.__class__.discover(backends="MockBasler", include_mocks=True)
    opencv_cameras = manager.__class__.discover(backends="OpenCV", include_mocks=True)
    
    # For testing consistency, only compare mock cameras
    mock_basler_from_all = [cam for cam in all_cameras if "MockBasler" in cam]
    mock_opencv_from_all = [cam for cam in all_cameras if cam.startswith("OpenCV:")]
    
    # Sort for comparison
    mock_basler_from_all_sorted = sorted(mock_basler_from_all)
    basler_cameras_sorted = sorted(basler_cameras)
    
    # Assert that backend-specific discovery finds the same mock cameras as full discovery
    assert mock_basler_from_all_sorted == basler_cameras_sorted


@pytest.mark.asyncio
async def test_convenience_function_with_backend_filtering():
    """Test convenience function with backend filtering."""
    mgr = AsyncCameraManager(include_mocks=True)
    all_cameras = AsyncCameraManager.discover(include_mocks=True)
    assert isinstance(all_cameras, list)
    assert len(all_cameras) > 0
    basler_cameras = AsyncCameraManager.discover(backends="MockBasler", include_mocks=True)
    assert isinstance(basler_cameras, list)
    for camera in basler_cameras:
        assert camera.startswith("MockBasler:")
    multi_cameras = AsyncCameraManager.discover(backends=["MockBasler", "OpenCV"])
    assert isinstance(multi_cameras, list)
    empty_cameras = AsyncCameraManager.discover(backends="NonExistentBackend")
    assert isinstance(empty_cameras, list)
    assert len(empty_cameras) == 0


# removed problematic default-open behavior test; default-open without include_mocks is expected to raise

@pytest.mark.asyncio
async def test_open_connection_fallback_to_capture(monkeypatch):
    # Force check_connection False -> capture path
    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend
    import numpy as np

    async def _false_check(self):
        return False

    async def _fast_cap(self):
        return True, np.zeros((10, 10, 3), dtype=np.uint8)

    monkeypatch.setattr(MockBaslerCameraBackend, "check_connection", _false_check, raising=False)
    monkeypatch.setattr(MockBaslerCameraBackend, "capture", _fast_cap, raising=False)

    mgr = AsyncCameraManager(include_mocks=True)
    try:
        name = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][0]
        cam = await mgr.open(name)
        assert cam.name == name
    finally:
        await mgr.close(None)


@pytest.mark.asyncio
async def test_open_connection_failure_raises(monkeypatch):
    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

    async def _boom(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(MockBaslerCameraBackend, "check_connection", _boom, raising=False)

    mgr = AsyncCameraManager(include_mocks=True)
    try:
        name = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][0]
        with pytest.raises(Exception):
            await mgr.open(name)
        # Should not be left active
        assert name not in mgr.active_cameras
    finally:
        await mgr.close(None)


@pytest.mark.asyncio
async def test_open_setup_failure_raises(monkeypatch):
    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

    async def _setup_boom(self):
        raise RuntimeError("setup fail")

    monkeypatch.setattr(MockBaslerCameraBackend, "setup_camera", _setup_boom, raising=False)

    mgr = AsyncCameraManager(include_mocks=True)
    try:
        name = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][0]
        with pytest.raises(Exception):
            await mgr.open(name)
    finally:
        await mgr.close(None)


@pytest.mark.asyncio
async def test_close_subset_only():
    mgr = AsyncCameraManager(include_mocks=True)
    try:
        names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][:2]
        if len(names) < 2:
            pytest.skip("Need at least two mocks")
        await mgr.open(names)
        assert set(mgr.active_cameras) == set(names)
        await mgr.close(names[0])
        assert set(mgr.active_cameras) == {names[1]}
    finally:
        await mgr.close(None)


@pytest.mark.asyncio
async def test_batch_configure_and_capture_with_unknown():
    mgr = AsyncCameraManager(include_mocks=True)
    try:
        name = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][0]
        await mgr.open(name)
        # Configure known + unknown
        cfg = {
            name: {"exposure": 1000},
            "UnknownBackend:dev": {"exposure": 1000},
        }
        cfg_res = await mgr.batch_configure(cfg)
        assert set(cfg_res.keys()) == {name, "UnknownBackend:dev"}
        # Unknown should be False
        assert cfg_res["UnknownBackend:dev"] is False

        # Capture known + unknown
        cap_res = await mgr.batch_capture([name, "UnknownBackend:dev"])
        assert set(cap_res.keys()) == {name, "UnknownBackend:dev"}
        assert cap_res["UnknownBackend:dev"] is None
    finally:
        await mgr.close(None)


@pytest.mark.asyncio
async def test_invalid_camera_name_no_colon():
    mgr = AsyncCameraManager(include_mocks=True)
    try:
        with pytest.raises(Exception):
            await mgr.open("InvalidNameNoColon")
    finally:
        await mgr.close(None)


@pytest.mark.asyncio
async def test_bandwidth_management_with_mixed_operations():
    """Test bandwidth management with mixed capture operations."""
    manager = AsyncCameraManager(include_mocks=True, max_concurrent_captures=2)
    try:
        cameras = manager.discover(include_mocks=True)
        mock_cameras = [cam for cam in cameras if "Mock" in cam][:3]
        if len(mock_cameras) >= 2:
            await manager.open(mock_cameras)
            # Test regular batch capture
            regular_results = await manager.batch_capture(mock_cameras)
            assert len(regular_results) == len(mock_cameras)
            # Test HDR batch capture
            hdr_results = await manager.batch_capture_hdr(
                camera_names=mock_cameras, exposure_levels=2, return_images=False
            )
            assert len(hdr_results) == len(mock_cameras)
            # Test individual camera captures
            camera_proxies = [await manager.open(name) for name in mock_cameras]
            individual_tasks = [proxy.capture() for proxy in camera_proxies]
            individual_results = await asyncio.gather(*individual_tasks)
            assert len(individual_results) == len(camera_proxies)
            # All operations should respect bandwidth limits
            bandwidth_info = manager.diagnostics()
            assert bandwidth_info["max_concurrent_captures"] == 2
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_bandwidth_management_persistence():
    """Test that bandwidth settings persist across operations."""
    manager = AsyncCameraManager(include_mocks=True, max_concurrent_captures=3)
    try:
        cameras = manager.discover(include_mocks=True)
        mock_cameras = [cam for cam in cameras if "Mock" in cam][:2]
        if len(mock_cameras) >= 2:
            await manager.open(mock_cameras)
            # Verify initial setting
            assert manager.max_concurrent_captures == 3
            # Perform multiple operations
            for i in range(3):
                results = await manager.batch_capture(mock_cameras)
                assert len(results) == len(mock_cameras)
                assert manager.max_concurrent_captures == 3
            # Change setting
            manager.max_concurrent_captures = 1
            assert manager.max_concurrent_captures == 1
            # Perform more operations
            for i in range(2):
                results = await manager.batch_capture(mock_cameras)
                assert len(results) == len(mock_cameras)
                assert manager.max_concurrent_captures == 1
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_bandwidth_management_with_convenience_functions():
    """Test bandwidth management with convenience functions."""
    mgr = AsyncCameraManager(include_mocks=True, max_concurrent_captures=5)
    cameras = AsyncCameraManager.discover(include_mocks=True)
    assert isinstance(cameras, list)
    assert len(cameras) > 0
    mock_cameras = [cam for cam in cameras if "Mock" in cam]
    assert len(mock_cameras) > 0
    mgr2 = AsyncCameraManager(include_mocks=True, max_concurrent_captures=3)
    basler_cameras = mgr2.discover(backends="MockBasler", include_mocks=True)
    assert isinstance(basler_cameras, list)
    for camera in basler_cameras:
        assert camera.startswith("MockBasler:")
    mgr3 = AsyncCameraManager(include_mocks=True, max_concurrent_captures=2)
    multi_cameras = mgr3.discover(backends=["MockBasler", "OpenCV"], include_mocks=True)
    assert isinstance(multi_cameras, list)
    for camera in multi_cameras:
        assert camera.startswith("MockBasler:") or camera.startswith("OpenCV:")


def test_discover_mixed_backends_filters(monkeypatch):
    # Ensure OpenCV returns empty; include mocks for valid path
    try:
        from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import OpenCVCameraBackend

        monkeypatch.setattr(OpenCVCameraBackend, "get_available_cameras", staticmethod(lambda include_details=False: []))
    except Exception:
        pass
    lst = AsyncCameraManager.discover(backends=["MockBasler", "NonExistent"], include_mocks=True)
    # Should include only mock names, not error
    assert isinstance(lst, list)
    for n in lst:
        assert n.startswith("MockBasler:")
