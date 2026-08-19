import asyncio
from pathlib import Path

import numpy as np
import pytest

from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager
from mindtrace.hardware.core.exceptions import CameraConfigurationError, CameraConnectionError, CameraNotFoundError


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
async def test_close_waits_for_in_flight_open(monkeypatch):
    """close() must not return while an in-flight open is still registering the camera."""
    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

    manager = AsyncCameraManager(include_mocks=True)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]

    async def slow_check_connection(self):
        await asyncio.sleep(0.3)
        return True

    monkeypatch.setattr(MockBaslerCameraBackend, "check_connection", slow_check_connection)

    try:
        open_task = asyncio.create_task(manager.open(name, test_connection=True))
        await asyncio.sleep(0.05)
        assert name not in manager.active_cameras

        await manager.close(name)
        assert name not in manager.active_cameras

        proxy = await open_task
        assert proxy is not None
        assert name not in manager.active_cameras
        assert name in manager._open_locks
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_open_restores_saved_config_before_connection_test(monkeypatch, tmp_path):
    """Saved settings are restored on open; later runtime configure tweaks are not persisted."""
    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    config_path = manager.get_camera_config_path(name)

    try:
        camera = await manager.open(name, test_connection=False)
        assert (await camera.configure(exposure=15000)).success is True
        await camera.export_config(config_path)

        # Runtime configure does not update the saved file.
        assert (await camera.configure(exposure=25000)).success is True
        assert await camera.get_exposure() == 25000
        await manager.close(name)

        async def check_restored_config(self):
            assert self.exposure_time == 15000
            return True

        monkeypatch.setattr(MockBaslerCameraBackend, "check_connection", check_restored_config)

        reopened = await manager.open(name, test_connection=True)
        assert await reopened.get_exposure() == 15000
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_open_camera_config_overrides_saved_profile(tmp_path):
    """open(camera_config=...) applies after saved profile and wins on overlapping keys."""
    import json

    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    saved_path = manager.get_camera_config_path(name)
    override_path = tmp_path / "override.json"

    Path(saved_path).parent.mkdir(parents=True, exist_ok=True)
    with open(saved_path, "w", encoding="utf-8") as f:
        json.dump({"exposure_time": 15000, "gain": 1.0}, f)
    with open(override_path, "w", encoding="utf-8") as f:
        json.dump({"exposure_time": 28000}, f)

    try:
        camera = await manager.open(name, test_connection=False, camera_config=str(override_path))
        assert await camera.get_exposure() == 28000
        assert await camera.get_gain() == 1.0
        assert manager._runtime_configure[name] == {"exposure_time": 28000}
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_open_camera_config_applies_when_restore_disabled(tmp_path):
    """camera_config still applies when restore_saved_config_on_open is disabled."""
    import json

    manager = AsyncCameraManager(include_mocks=True, restore_saved_config_on_open=False)
    manager._camera_config_dir = str(tmp_path)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    override_path = tmp_path / "session.json"

    with open(override_path, "w", encoding="utf-8") as f:
        json.dump({"exposure_time": 22000}, f)

    try:
        camera = await manager.open(name, test_connection=False, camera_config=str(override_path))
        assert await camera.get_exposure() == 22000
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_open_missing_camera_config_path_raises(monkeypatch, tmp_path):
    """A missing camera_config path should fail open and close the backend."""
    from mindtrace.hardware.cameras.backends.camera_backend import CameraBackend

    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    created_backend: CameraBackend | None = None

    original_create = manager._create_camera_instance

    def create_camera_instance_spy(backend: str, device_name: str, **kwargs):
        nonlocal created_backend
        created_backend = original_create(backend, device_name, **kwargs)
        return created_backend

    try:
        monkeypatch.setattr(manager, "_create_camera_instance", create_camera_instance_spy)
        with pytest.raises(CameraConfigurationError, match="camera_config path not found"):
            await manager.open(
                name,
                test_connection=False,
                camera_config=str(tmp_path / "does_not_exist.json"),
            )
        assert created_backend is not None
        assert created_backend.initialized is False
        assert created_backend.camera is None
        assert name not in manager._cameras
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_open_restore_preserves_manager_performance_settings(tmp_path):
    """Saved profiles must not overwrite manager-owned timeout and retry settings."""
    import json

    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    config_path = manager.get_camera_config_path(name)

    # Legacy profile with stale manager-owned keys plus a real imaging default.
    config_path_obj = Path(config_path)
    config_path_obj.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path_obj, "w") as f:
        json.dump(
            {
                "exposure_time": 15000,
                "timeout_ms": 2000,
                "retrieve_retry_count": 1,
                "buffer_count": 10,
            },
            f,
        )

    manager.timeout_ms = 9000
    manager.retrieve_retry_count = 7

    try:
        reopened = await manager.open(name, test_connection=False)
        assert await reopened.get_exposure() == 15000
        assert reopened._backend.timeout_ms == 9000
        assert reopened._backend.retrieve_retry_count == 7

        await manager.close(name)

        explicit = await manager.open(
            name,
            test_connection=False,
            timeout_ms=12345,
            retrieve_retry_count=4,
        )
        assert explicit._backend.timeout_ms == 12345
        assert explicit._backend.retrieve_retry_count == 4
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_reset_saved_config_then_open_uses_backend_defaults(tmp_path):
    """Reset clears the saved profile so the next open uses backend defaults."""
    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    config_path = manager.get_camera_config_path(name)

    try:
        camera = await manager.open(name, test_connection=False)
        assert (await camera.configure(exposure=15000)).success is True
        await camera.export_config(config_path)
        assert (await camera.configure(exposure=25000)).success is True
        await manager.close(name)

        assert manager.reset_saved_config(name) is True
        assert not Path(config_path).exists()

        reopened = await manager.open(name, test_connection=False)
        assert await reopened.get_exposure() == 20000
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_reset_saved_config_is_idempotent_when_file_missing(tmp_path):
    """Reset succeeds when no saved configuration file exists."""
    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]

    assert manager.reset_saved_config(name) is False


def test_read_saved_config_returns_none_when_file_missing(tmp_path):
    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]

    assert manager.read_saved_config(name) is None


def test_read_saved_config_returns_parsed_json(tmp_path):
    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    config_path = Path(manager.get_camera_config_path(name))
    config_path.write_text(
        '{"exposure_time": 15000.0, "roi": {"x": 1, "y": 2, "width": 640, "height": 480}}',
        encoding="utf-8",
    )

    config = manager.read_saved_config(name)

    assert config["exposure_time"] == 15000.0
    assert config["roi"]["width"] == 640


def test_read_saved_config_raises_on_invalid_json(tmp_path):
    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    config_path = Path(manager.get_camera_config_path(name))
    config_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(CameraConfigurationError, match="Invalid saved config JSON"):
        manager.read_saved_config(name)


def test_validate_camera_name_accepts_known_backend():
    manager = AsyncCameraManager(include_mocks=True)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]

    manager.validate_camera_name(name)


def test_validate_camera_name_rejects_unknown_backend():
    manager = AsyncCameraManager(include_mocks=True)

    with pytest.raises(CameraNotFoundError, match="Backend 'UnknownBackend' not available"):
        manager.validate_camera_name("UnknownBackend:cam1")


def test_validate_camera_name_rejects_invalid_format():
    manager = AsyncCameraManager(include_mocks=True)

    with pytest.raises(CameraConfigurationError, match="Invalid camera name format"):
        manager.validate_camera_name("not-a-valid-name")


@pytest.mark.asyncio
async def test_reinit_replays_open_kwargs(monkeypatch):
    """Auto-reinit must reopen with the same constructor kwargs as the original open."""
    manager = AsyncCameraManager(include_mocks=True)
    manager._restore_saved_config_on_open = False
    manager._max_consecutive_failures = 3
    manager._reinitialization_cooldown = 0
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]

    async def failing_capture(self, save_path=None, output_format="pil"):
        raise CameraConnectionError("simulated capture failure")

    monkeypatch.setattr(
        "mindtrace.hardware.cameras.core.async_camera.AsyncCamera.capture",
        failing_capture,
    )

    try:
        camera = await manager.open(
            name,
            test_connection=False,
            synthetic_width=640,
            synthetic_height=480,
            buffer_count=12,
        )
        assert camera._backend.synthetic_width == 640
        assert camera._backend.synthetic_height == 480
        assert camera._backend.buffer_count == 12

        for _ in range(3):
            await manager.batch_capture([name])

        reopened = manager._cameras[name]
        assert reopened._backend.synthetic_width == 640
        assert reopened._backend.synthetic_height == 480
        assert reopened._backend.buffer_count == 12
        assert manager._open_kwargs[name] == {
            "synthetic_width": 640,
            "synthetic_height": 480,
            "buffer_count": 12,
        }
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_reinit_serializes_concurrent_open(monkeypatch):
    """Auto-reinit must hold the per-camera lock for the full close+reopen cycle."""
    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

    manager = AsyncCameraManager(include_mocks=True)
    manager._restore_saved_config_on_open = False
    manager._max_consecutive_failures = 3
    manager._reinitialization_cooldown = 0
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]

    create_calls: list[str] = []
    original_create = AsyncCameraManager._create_camera_instance

    def counting_create(self, backend, device_name, **kwargs):
        create_calls.append(f"{backend}:{device_name}")
        return original_create(self, backend, device_name, **kwargs)

    original_initialize = MockBaslerCameraBackend.initialize

    async def slow_initialize(self):
        await asyncio.sleep(0.3)
        return await original_initialize(self)

    monkeypatch.setattr(AsyncCameraManager, "_create_camera_instance", counting_create)
    monkeypatch.setattr(MockBaslerCameraBackend, "initialize", slow_initialize)

    try:
        await manager.open(name, test_connection=False)
        create_calls.clear()

        reinit_task = asyncio.create_task(manager._handle_camera_failure(name))
        await asyncio.sleep(0.05)
        ensure_open_task = asyncio.create_task(manager.open(name, test_connection=False))

        await asyncio.gather(reinit_task, ensure_open_task)

        assert create_calls.count(name) == 1
        assert name in manager.active_cameras
        assert name in manager._open_locks
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_reinit_replaces_camera_when_close_fails(monkeypatch):
    """Reinit must deregister a wedged camera even if backend close raises."""
    manager = AsyncCameraManager(include_mocks=True)
    manager._restore_saved_config_on_open = False
    manager._reinitialization_cooldown = 0
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]

    async def failing_close(self):
        raise CameraConnectionError("simulated close failure")

    monkeypatch.setattr(
        "mindtrace.hardware.cameras.core.async_camera.AsyncCamera.close",
        failing_close,
    )

    try:
        await manager.open(name, test_connection=False)
        original_proxy = manager._cameras[name]
        original_backend = original_proxy._backend

        await manager._handle_camera_failure(name)

        reopened = manager._cameras[name]
        assert reopened is not original_proxy
        assert reopened._backend is not original_backend
        assert manager._failure_counts.get(name, 0) == 0
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_reinit_replays_runtime_configure(monkeypatch, tmp_path):
    """Auto-reinit must replay accumulated runtime configure settings after profile restore."""
    import json

    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    manager._max_consecutive_failures = 3
    manager._reinitialization_cooldown = 0
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    config_path = manager.get_camera_config_path(name)

    async def failing_capture(self, save_path=None, output_format="pil"):
        raise CameraConnectionError("simulated capture failure")

    monkeypatch.setattr(
        "mindtrace.hardware.cameras.core.async_camera.AsyncCamera.capture",
        failing_capture,
    )

    try:
        camera = await manager.open(name, test_connection=False)
        assert (await manager.configure_camera(name, {"exposure": 15000})).success is True
        await camera.export_config(config_path)
        assert (await manager.configure_camera(name, {"exposure": 33333, "gain": 4.0})).success is True
        assert await camera.get_exposure() == 33333
        assert await camera.get_gain() == 4.0

        for _ in range(3):
            await manager.batch_capture([name])

        reopened = manager._cameras[name]
        assert await reopened.get_exposure() == 33333
        assert await reopened.get_gain() == 4.0
        assert manager._runtime_configure[name] == {"exposure_time": 33333, "gain": 4.0}

        with open(config_path) as f:
            saved = json.load(f)
        assert saved["exposure_time"] == 15000
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_reinit_replays_partial_runtime_configure_after_failed_keys(monkeypatch, tmp_path):
    """Successfully applied keys must be merged and replayed even when other keys in the same configure fail."""
    from mindtrace.hardware.core.exceptions import CameraConfigurationError

    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    manager._max_consecutive_failures = 3
    manager._reinitialization_cooldown = 0
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]

    async def failing_capture(self, save_path=None, output_format="pil"):
        raise CameraConnectionError("simulated capture failure")

    monkeypatch.setattr(
        "mindtrace.hardware.cameras.core.async_camera.AsyncCamera.capture",
        failing_capture,
    )

    try:
        camera = await manager.open(name, test_connection=False)
        original_set_gain = camera.backend.set_gain

        async def failing_set_gain(gain):
            raise CameraConfigurationError("gain out of range")

        camera.backend.set_gain = failing_set_gain

        result = await manager.configure_camera(name, {"exposure": 28000, "gain": 99.0})
        assert result.success is False
        assert result.applied == 1
        assert result.total == 2
        assert await camera.get_exposure() == 28000
        assert manager._runtime_configure[name] == {"exposure_time": 28000}
        assert "gain" not in manager._runtime_configure[name]

        camera.backend.set_gain = original_set_gain

        for _ in range(3):
            await manager.batch_capture([name])

        reopened = manager._cameras[name]
        assert await reopened.get_exposure() == 28000
        assert await reopened.get_gain() == 1.0
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_reinit_replays_partial_genicam_nodes_after_failed_nodes(monkeypatch, tmp_path):
    """Nodes that applied before a genicam_nodes failure must still replay after reinit."""
    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend
    from mindtrace.hardware.core.exceptions import CameraConfigurationError

    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    manager._max_consecutive_failures = 3
    manager._reinitialization_cooldown = 0
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    replayed: dict[str, object] = {}

    async def apply_genicam_nodes(self, node_config):
        if node_config.get("ReverseX") is True:
            applied = {key: value for key, value in node_config.items() if key != "ReverseX"}
            raise CameraConfigurationError(
                "Failed to apply GenICam nodes: ReverseX: not writable",
                details={"applied": applied},
            )
        replayed.clear()
        replayed.update(node_config)

    monkeypatch.setattr(MockBaslerCameraBackend, "apply_genicam_nodes", apply_genicam_nodes, raising=False)
    monkeypatch.setattr(
        MockBaslerCameraBackend, "nested_merge_config_keys", frozenset({"genicam_nodes"}), raising=False
    )

    async def failing_capture(self, save_path=None, output_format="pil"):
        raise CameraConnectionError("simulated capture failure")

    monkeypatch.setattr(
        "mindtrace.hardware.cameras.core.async_camera.AsyncCamera.capture",
        failing_capture,
    )

    try:
        await manager.open(name, test_connection=False)
        result = await manager.configure_camera(name, {"genicam_nodes": {"PixelFormat": "Mono8", "ReverseX": True}})
        assert result.success is False
        assert result.partial == {"genicam_nodes": {"PixelFormat": "Mono8"}}
        assert manager._runtime_configure[name] == {"genicam_nodes": {"PixelFormat": "Mono8"}}

        for _ in range(3):
            await manager.batch_capture([name])

        assert replayed == {"PixelFormat": "Mono8"}
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_reinit_replays_union_of_sequential_genicam_node_configures(monkeypatch, tmp_path):
    """Later genicam_nodes configures must accumulate nodes for auto-reinit replay."""
    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    manager._max_consecutive_failures = 3
    manager._reinitialization_cooldown = 0
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    replayed: dict[str, object] = {}

    async def apply_genicam_nodes(self, node_config):
        replayed.clear()
        replayed.update(node_config)

    monkeypatch.setattr(MockBaslerCameraBackend, "apply_genicam_nodes", apply_genicam_nodes, raising=False)
    monkeypatch.setattr(
        MockBaslerCameraBackend, "nested_merge_config_keys", frozenset({"genicam_nodes"}), raising=False
    )

    async def failing_capture(self, save_path=None, output_format="pil"):
        raise CameraConnectionError("simulated capture failure")

    monkeypatch.setattr(
        "mindtrace.hardware.cameras.core.async_camera.AsyncCamera.capture",
        failing_capture,
    )

    try:
        await manager.open(name, test_connection=False)
        first = await manager.configure_camera(name, {"genicam_nodes": {"PixelFormat": "Mono8"}})
        second = await manager.configure_camera(name, {"genicam_nodes": {"ReverseX": True}})

        assert first.success is True
        assert second.success is True
        assert manager._runtime_configure[name] == {
            "genicam_nodes": {"PixelFormat": "Mono8", "ReverseX": True},
        }

        for _ in range(3):
            await manager.batch_capture([name])

        assert replayed == {"PixelFormat": "Mono8", "ReverseX": True}
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_reinit_replays_union_of_sequential_focus_config_configures(monkeypatch, tmp_path):
    """Later focus_config configures must accumulate keys for auto-reinit replay."""
    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    manager._max_consecutive_failures = 3
    manager._reinitialization_cooldown = 0
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    replayed: dict[str, object] = {}

    async def set_focus_config(self, **settings):
        replayed.clear()
        replayed.update(settings)

    monkeypatch.setattr(MockBaslerCameraBackend, "set_focus_config", set_focus_config)

    async def failing_capture(self, save_path=None, output_format="pil"):
        raise CameraConnectionError("simulated capture failure")

    monkeypatch.setattr(
        "mindtrace.hardware.cameras.core.async_camera.AsyncCamera.capture",
        failing_capture,
    )

    try:
        await manager.open(name, test_connection=False)
        first = await manager.configure_camera(name, {"focus_config": {"accuracy": "Fast"}})
        second = await manager.configure_camera(name, {"focus_config": {"roi_size": "Large"}})

        assert first.success is True
        assert second.success is True
        assert manager._runtime_configure[name] == {
            "focus_config": {"accuracy": "Fast", "roi_size": "Large"},
        }

        for _ in range(3):
            await manager.batch_capture([name])

        assert replayed == {"accuracy": "Fast", "roi_size": "Large"}
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_reinit_replays_partial_focus_config_after_failed_keys(monkeypatch, tmp_path):
    """Focus keys that applied before a later failure must still replay after reinit."""
    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    manager._max_consecutive_failures = 3
    manager._reinitialization_cooldown = 0
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    replayed: dict[str, object] = {}

    async def set_focus_config(self, **settings):
        if "stepper" in settings:
            applied = {key: value for key, value in settings.items() if key != "stepper"}
            raise CameraConfigurationError(
                "Failed to set stepper",
                details={"applied": applied},
            )
        replayed.clear()
        replayed.update(settings)

    monkeypatch.setattr(MockBaslerCameraBackend, "set_focus_config", set_focus_config)

    async def failing_capture(self, save_path=None, output_format="pil"):
        raise CameraConnectionError("simulated capture failure")

    monkeypatch.setattr(
        "mindtrace.hardware.cameras.core.async_camera.AsyncCamera.capture",
        failing_capture,
    )

    try:
        await manager.open(name, test_connection=False)
        result = await manager.configure_camera(name, {"focus_config": {"accuracy": "Accurate", "stepper": 0.2}})
        assert result.success is False
        assert result.partial == {"focus_config": {"accuracy": "Accurate"}}
        assert manager._runtime_configure[name] == {"focus_config": {"accuracy": "Accurate"}}

        for _ in range(3):
            await manager.batch_capture([name])

        assert replayed == {"accuracy": "Accurate"}
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_apply_saved_config_updates_runtime_configure_for_reinit(monkeypatch, tmp_path):
    """apply_saved_config must refresh runtime configure so reinit does not replay stale settings."""
    import json

    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    manager._max_consecutive_failures = 3
    manager._reinitialization_cooldown = 0
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]

    async def failing_capture(self, save_path=None, output_format="pil"):
        raise CameraConnectionError("simulated capture failure")

    monkeypatch.setattr(
        "mindtrace.hardware.cameras.core.async_camera.AsyncCamera.capture",
        failing_capture,
    )

    with open(tmp_path / "imported.json", "w", encoding="utf-8") as f:
        json.dump({"exposure_time": 15000}, f)
    import_path = str(tmp_path / "imported.json")

    try:
        camera = await manager.open(name, test_connection=False)
        assert (await manager.configure_camera(name, {"exposure_time": 25000})).success is True
        assert await camera.get_exposure() == 25000
        assert manager._runtime_configure[name] == {"exposure_time": 25000}

        result = await manager.apply_saved_config(name, import_path)
        assert result.success is True
        assert await camera.get_exposure() == 15000
        assert manager._runtime_configure[name] == {"exposure_time": 15000}

        for _ in range(3):
            await manager.batch_capture([name])

        reopened = manager._cameras[name]
        assert await reopened.get_exposure() == 15000
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_open_skips_restore_when_disabled_at_manager_level(tmp_path):
    """Manager-level policy can disable auto-restore on open."""
    manager = AsyncCameraManager(include_mocks=True, restore_saved_config_on_open=False)
    manager._camera_config_dir = str(tmp_path)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    config_path = manager.get_camera_config_path(name)

    try:
        camera = await manager.open(name, test_connection=False)
        assert (await camera.configure(exposure=15000)).success is True
        await camera.export_config(config_path)
        await manager.close(name)

        reopened = await manager.open(name, test_connection=False)
        assert await reopened.get_exposure() == 20000
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_open_registers_camera_only_after_restore_and_connection_test(monkeypatch, tmp_path):
    """_cameras should only contain fully initialized cameras."""
    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]

    registered_during_restore: list[bool] = []
    registered_during_connection_test: list[bool] = []

    original_import = manager._auto_import_config

    async def track_import(camera_name: str, camera):
        registered_during_restore.append(camera_name in manager._cameras)
        await original_import(camera_name, camera)

    monkeypatch.setattr(manager, "_auto_import_config", track_import)

    async def check_connection_with_tracking(self):
        registered_during_connection_test.append(name in manager._cameras)
        return True

    monkeypatch.setattr(MockBaslerCameraBackend, "check_connection", check_connection_with_tracking)

    try:
        camera = await manager.open(name, test_connection=False)
        assert (await camera.configure(exposure=15000)).success is True
        await camera.export_config(manager.get_camera_config_path(name))
        await manager.close(name)

        await manager.open(name, test_connection=True)
        assert registered_during_restore == [False, False]
        assert registered_during_connection_test == [False]
        assert name in manager.active_cameras
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_open_connection_failure_does_not_register_camera(monkeypatch):
    """A failed connection test must not leave a half-open camera in _cameras."""
    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

    manager = AsyncCameraManager(include_mocks=True)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]

    async def failing_check_connection(self):
        return False

    async def failing_capture(self):
        return None

    monkeypatch.setattr(MockBaslerCameraBackend, "check_connection", failing_check_connection)
    monkeypatch.setattr(MockBaslerCameraBackend, "capture", failing_capture)

    with pytest.raises(CameraConnectionError):
        await manager.open(name, test_connection=True)

    assert name not in manager.active_cameras


@pytest.mark.asyncio
async def test_open_connection_failure_does_not_leak_camera_config_runtime(monkeypatch, tmp_path):
    """Failed open(camera_config=...) must not leave replay state for a later open."""
    import json

    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

    manager = AsyncCameraManager(include_mocks=True)
    manager._camera_config_dir = str(tmp_path)
    name = AsyncCameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
    override_path = tmp_path / "session.json"
    with open(override_path, "w", encoding="utf-8") as f:
        json.dump({"exposure_time": 28000}, f)

    async def failing_check_connection(self):
        return False

    async def failing_capture(self):
        return None

    monkeypatch.setattr(MockBaslerCameraBackend, "check_connection", failing_check_connection)
    monkeypatch.setattr(MockBaslerCameraBackend, "capture", failing_capture)

    with pytest.raises(CameraConnectionError):
        await manager.open(name, test_connection=True, camera_config=str(override_path))

    assert name not in manager.active_cameras
    assert name not in manager._runtime_configure

    try:
        camera = await manager.open(name, test_connection=False)
        assert name not in manager._runtime_configure
        assert await camera.get_exposure() == 20000
    finally:
        await manager.close(None)


@pytest.mark.asyncio
async def test_batch_capture_with_mock_backend(monkeypatch):
    """Test batch capture with controlled mock cameras instead of discovery-dependent."""
    manager = AsyncCameraManager(include_mocks=True, max_concurrent_captures=2)

    # Create controlled mock cameras
    mock_cameras = ["MockBasler:TestCam1", "MockBasler:TestCam2", "MockBasler:TestCam3"]

    def mock_discover(include_mocks=True, backends=None):
        return mock_cameras if include_mocks else []

    monkeypatch.setattr(manager, "discover", mock_discover)

    try:
        await manager.open(mock_cameras)

        # Ensure captures complete and produce ndarray images (request numpy format)
        results = await manager.batch_capture(mock_cameras, output_format="numpy")
        assert set(results.keys()) == set(mock_cameras)
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
        result = await camera_proxy.configure(exposure=20000, gain=2.0, trigger_mode="continuous")
        assert result.success is True
        exposure = await camera_proxy.get_exposure()
        assert exposure == 20000
        gain = await camera_proxy.get_gain()
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
async def test_open_default_no_cameras_raises(monkeypatch):
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
    mgr = AsyncCameraManager(include_mocks=True)

    # Mock discover to return empty list
    monkeypatch.setattr(mgr, "discover", lambda: [])

    try:
        # Should raise CameraNotFoundError when no cameras are available
        with pytest.raises(Exception, match="No cameras available to open by default"):
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
async def test_batch_capture_hdr_return_images(monkeypatch):
    """Test HDR capture with controlled mock cameras."""
    mgr = AsyncCameraManager(include_mocks=True, max_concurrent_captures=2)

    # Create controlled mock cameras
    mock_cameras = ["MockBasler:TestCam1", "MockBasler:TestCam2"]

    def mock_discover(include_mocks=True, backends=None):
        return mock_cameras if include_mocks else []

    monkeypatch.setattr(mgr, "discover", mock_discover)

    try:
        await mgr.open(mock_cameras)
        res = await mgr.batch_capture_hdr(camera_names=mock_cameras, exposure_levels=2, return_images=True)
        assert set(res.keys()) == set(mock_cameras)
        for camera_name, hdr_result in res.items():
            assert isinstance(hdr_result, dict)
            assert "success" in hdr_result
            assert "images" in hdr_result
            assert "exposure_levels" in hdr_result
            if hdr_result["success"]:
                assert isinstance(hdr_result["images"], list)
                assert len(hdr_result["exposure_levels"]) == 2  # Should have 2 exposure levels
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
            lambda include_details=False: (
                {"opencv_camera_0": {"index": 0, "width": 640, "height": 480, "fps": 30.0}}
                if include_details
                else ["opencv_camera_0"]
            )
        ),
    )

    recs = AsyncCameraManager.discover(details=True)
    assert any(r.get("name", "").startswith("OpenCV:") for r in recs)


def test_discover_opencv_list_mode(monkeypatch):
    from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import OpenCVCameraBackend

    monkeypatch.setattr(
        OpenCVCameraBackend, "get_available_cameras", staticmethod(lambda include_details=False: ["opencv_camera_0"])
    )
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
    [cam for cam in all_cameras if "MockBasler" in cam or "OpenCV" not in cam]

    basler_cameras = manager.__class__.discover(backends="MockBasler", include_mocks=True)
    manager.__class__.discover(backends="OpenCV", include_mocks=True)

    # For testing consistency, only compare mock cameras
    mock_basler_from_all = [cam for cam in all_cameras if "MockBasler" in cam]
    [cam for cam in all_cameras if cam.startswith("OpenCV:")]

    # Sort for comparison
    mock_basler_from_all_sorted = sorted(mock_basler_from_all)
    basler_cameras_sorted = sorted(basler_cameras)

    # Assert that backend-specific discovery finds the same mock cameras as full discovery
    assert mock_basler_from_all_sorted == basler_cameras_sorted


@pytest.mark.asyncio
async def test_convenience_function_with_backend_filtering():
    """Test convenience function with backend filtering."""
    AsyncCameraManager(include_mocks=True)
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
    import numpy as np

    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

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
async def test_close_subset_only(monkeypatch):
    """Test closing a subset of cameras with controlled mocks."""
    mgr = AsyncCameraManager(include_mocks=True)

    # Create controlled mock cameras
    mock_cameras = ["MockBasler:TestCam1", "MockBasler:TestCam2"]

    def mock_discover(include_mocks=True, backends=None):
        return mock_cameras if include_mocks else []

    monkeypatch.setattr(mgr, "discover", mock_discover)

    try:
        await mgr.open(mock_cameras)
        assert set(mgr.active_cameras) == set(mock_cameras)

        # Close only the first camera
        await mgr.close(mock_cameras[0])
        assert set(mgr.active_cameras) == {mock_cameras[1]}

        # Verify the remaining camera is still functional
        remaining_cam = await mgr.open(mock_cameras[1])
        assert remaining_cam.is_connected
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
        assert cfg_res[name].success is True
        assert cfg_res["UnknownBackend:dev"].success is False
        assert cfg_res["UnknownBackend:dev"].applied == 0
        assert cfg_res["UnknownBackend:dev"].total == 1
        assert "_error" in cfg_res["UnknownBackend:dev"].failures

        empty_res = await mgr.batch_configure({"UnknownBackend:dev": {}})
        assert empty_res["UnknownBackend:dev"].success is False
        assert empty_res["UnknownBackend:dev"].total == 0

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
    AsyncCameraManager(include_mocks=True, max_concurrent_captures=5)
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

        monkeypatch.setattr(
            OpenCVCameraBackend, "get_available_cameras", staticmethod(lambda include_details=False: [])
        )
    except Exception:
        pass
    lst = AsyncCameraManager.discover(backends=["MockBasler", "NonExistent"], include_mocks=True)
    # Should include only mock names, not error
    assert isinstance(lst, list)
    for n in lst:
        assert n.startswith("MockBasler:")


@pytest.mark.asyncio
async def test_batch_capture_save_path_pattern_returns_paths(tmp_path):
    """Batch save-path captures return per-camera file paths to written files."""
    manager = AsyncCameraManager(include_mocks=True, max_concurrent_captures=2)
    mock_cameras = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")][:2]
    if len(mock_cameras) < 2:
        pytest.skip("Need at least two mock Basler cameras")

    try:
        await manager.open(mock_cameras)
        pattern = str(tmp_path / "{camera}.jpg")
        results = await manager.batch_capture(
            mock_cameras,
            save_path_pattern=pattern,
            output_format="numpy",
        )
        assert set(results.keys()) == set(mock_cameras)
        for camera_name, path in results.items():
            safe_name = camera_name.replace(":", "_").replace("/", "_")
            assert path == str(tmp_path / f"{safe_name}.jpg")
            assert (tmp_path / f"{safe_name}.jpg").exists()
    finally:
        await manager.close(None)
