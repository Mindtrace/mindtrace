import numpy as np
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


def test_open_default_without_mocks_raises():
    mgr = CameraManager(include_mocks=False)
    try:
        # Check if real cameras are available
        available_cameras = mgr.discover()
        if not available_cameras:
            # Only test for exception if no real cameras are present
            with pytest.raises(CameraNotFoundError):
                mgr.open(None)
        else:
            # If real cameras exist, verify that open(None) succeeds and returns a camera
            cam = mgr.open(None)
            assert cam is not None
            assert cam.name in available_cameras
            mgr.close(cam.name)
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


def test_diagnostics_after_open():
    mgr = CameraManager(include_mocks=True)
    try:
        names = [n for n in CameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][:2]
        if not names:
            pytest.skip("no mocks discovered")
        res = mgr.open(names)
        assert set(res.keys()) == set(names)
        d = mgr.diagnostics()
        assert isinstance(d, dict)
        assert d["active_cameras"] == len(names)
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
