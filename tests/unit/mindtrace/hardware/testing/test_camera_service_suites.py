"""Unit tests for CameraManagerService benchmark suites."""

from __future__ import annotations

import dataclasses

from mindtrace.core import BenchReporter
from mindtrace.core.testing.bench_suite import build_bench_suite_config
from mindtrace.hardware.testing.suites.camera_service import (
    HardwareCameraServiceCaptureSmokeSuite,
    HardwareCameraServiceCaptureStressSuite,
)


class FakeCameraManagerService:
    instances: list["FakeCameraManagerService"] = []

    def __init__(self, *, include_mocks: bool = False, **_kwargs):
        self.include_mocks = include_mocks
        self.open_calls: list[object] = []
        self.capture_calls: list[object] = []
        self.closed = False
        self.shutdown = False
        FakeCameraManagerService.instances.append(self)

    async def open_cameras_batch(self, request):
        self.open_calls.append(request)
        return {camera: True for camera in request.cameras}

    async def capture_images_batch(self, request):
        self.capture_calls.append(request)
        return {
            "data": {
                camera: {
                    "success": True,
                    "image_data": "abc123",
                    "image_size": (2, 3),
                    "file_size_bytes": 6,
                }
                for camera in request.cameras
            },
            "successful_count": len(request.cameras),
            "failed_count": 0,
        }

    async def close_all_cameras(self):
        self.closed = True
        return True

    async def shutdown_cleanup(self):
        self.shutdown = True


def _config_for(suite_cls, *, duration_seconds: float = 0.0):
    contrib = suite_cls.as_contribution()
    cfg = build_bench_suite_config(
        contrib,
        profile="smoke",
        run_id="unit-run",
        extra_parameters={
            "cameras": ["MockBasler:mock_basler_1", "MockBasler:mock_basler_2"],
            "include_mocks": True,
            "output_format": "png",
            "test_connection": False,
        },
        resources={},
    )
    return dataclasses.replace(cfg, duration_seconds=duration_seconds)


def test_camera_service_smoke_suite_opens_captures_and_closes(monkeypatch):
    import mindtrace.hardware.testing.suites.camera_service as module

    FakeCameraManagerService.instances.clear()
    monkeypatch.setattr(module, "CameraManagerService", FakeCameraManagerService)

    config = _config_for(HardwareCameraServiceCaptureSmokeSuite)
    reporter = BenchReporter(suite_id=HardwareCameraServiceCaptureSmokeSuite.suite_id)
    result = HardwareCameraServiceCaptureSmokeSuite().execute_bench(config, reporter)

    assert result.status == "passed"
    assert result.operations == 1
    assert result.successes == 1
    assert result.failures == 0
    assert result.bytes_processed == 12
    assert result.metrics["mode"] == "camera_manager_service"
    service = FakeCameraManagerService.instances[-1]
    assert service.include_mocks is True
    assert service.closed is True
    assert service.shutdown is True


def test_camera_service_stress_suite_repeats_until_deadline(monkeypatch):
    import mindtrace.hardware.testing.suites.camera_service as module

    FakeCameraManagerService.instances.clear()
    monkeypatch.setattr(module, "CameraManagerService", FakeCameraManagerService)

    config = _config_for(HardwareCameraServiceCaptureStressSuite, duration_seconds=0.01)
    reporter = BenchReporter(suite_id=HardwareCameraServiceCaptureStressSuite.suite_id)
    result = HardwareCameraServiceCaptureStressSuite().execute_bench(config, reporter)

    assert result.status == "passed"
    assert result.operations >= 1
    assert result.successes == result.operations
    assert FakeCameraManagerService.instances[-1].closed is True
