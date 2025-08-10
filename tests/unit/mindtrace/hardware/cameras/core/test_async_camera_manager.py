import asyncio
import numpy as np
import pytest

from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager


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
        with pytest.raises(Exception):
            # Should raise because there are no default devices
            await mgr.open(None)
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
        for v in res.values():
            assert isinstance(v, list)
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
