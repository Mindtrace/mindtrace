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
