"""Unit tests for CameraManager benchmark suites."""

from __future__ import annotations

import dataclasses

import numpy as np

from mindtrace.core import BenchReporter
from mindtrace.core.testing.bench_suite import build_bench_suite_config
from mindtrace.hardware.testing.suites.camera_manager import (
    HardwareCameraManagerCaptureSmokeSuite,
    HardwareCameraManagerCaptureStressSuite,
)


class FakeCamera:
    name = "MockBasler:mock_basler_1"

    def capture(self, output_format: str = "numpy"):
        assert output_format == "numpy"
        return np.zeros((4, 5, 3), dtype=np.uint8)


class FakeCameraManager:
    instances: list["FakeCameraManager"] = []

    def __init__(self, *, include_mocks: bool = False, max_concurrent_captures: int | None = None):
        self.include_mocks = include_mocks
        self.max_concurrent_captures = max_concurrent_captures
        self.open_calls: list[object] = []
        self.closed = False
        FakeCameraManager.instances.append(self)

    def open(self, names=None, test_connection: bool = True, **_kwargs):
        self.open_calls.append((names, test_connection))
        if isinstance(names, list):
            return {name: FakeCamera() for name in names}
        return FakeCamera()

    def batch_capture(self, camera_names, output_format: str = "numpy"):
        assert output_format == "numpy"
        return {name: np.zeros((4, 5, 3), dtype=np.uint8) for name in camera_names}

    def close(self, names=None):  # noqa: ARG002
        self.closed = True


def _config_for(suite_cls, *, duration_seconds: float = 0.0):
    contrib = suite_cls.as_contribution()
    cfg = build_bench_suite_config(
        contrib,
        profile="smoke",
        run_id="unit-run",
        extra_parameters={
            "cameras": ["MockBasler:mock_basler_1", "MockBasler:mock_basler_2"],
            "include_mocks": True,
            "output_format": "numpy",
            "test_connection": False,
            "max_concurrent_captures": 2,
        },
        resources={},
    )
    return dataclasses.replace(cfg, duration_seconds=duration_seconds)


def test_camera_manager_smoke_suite_opens_captures_and_closes(monkeypatch):
    import mindtrace.hardware.testing.suites.camera_manager as module

    FakeCameraManager.instances.clear()
    monkeypatch.setattr(module, "CameraManager", FakeCameraManager)

    config = _config_for(HardwareCameraManagerCaptureSmokeSuite)
    reporter = BenchReporter(suite_id=HardwareCameraManagerCaptureSmokeSuite.suite_id)
    result = HardwareCameraManagerCaptureSmokeSuite().execute_bench(config, reporter)

    assert result.status == "passed"
    assert result.operations == 2
    assert result.successes == 2
    assert result.failures == 0
    assert result.bytes_processed == 2 * 4 * 5 * 3
    assert result.metrics["mode"] == "camera_manager"
    assert result.metrics["camera_count"] == 2
    manager = FakeCameraManager.instances[-1]
    assert manager.include_mocks is True
    assert manager.max_concurrent_captures == 2
    assert manager.closed is True


def test_camera_manager_stress_suite_repeats_until_deadline(monkeypatch):
    import mindtrace.hardware.testing.suites.camera_manager as module

    FakeCameraManager.instances.clear()
    monkeypatch.setattr(module, "CameraManager", FakeCameraManager)

    config = _config_for(HardwareCameraManagerCaptureStressSuite, duration_seconds=0.01)
    reporter = BenchReporter(suite_id=HardwareCameraManagerCaptureStressSuite.suite_id)
    result = HardwareCameraManagerCaptureStressSuite().execute_bench(config, reporter)

    assert result.status == "passed"
    assert result.operations >= 2
    assert result.successes == result.operations
    assert FakeCameraManager.instances[-1].closed is True
