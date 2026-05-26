"""CameraManager benchmark suites."""

from __future__ import annotations

import time
from collections import Counter
from types import MappingProxyType

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema
from mindtrace.hardware.cameras.core.camera_manager import CameraManager
from mindtrace.hardware.testing.suites._camera_common import (
    HardwareCameraInput,
    camera_names_from_config,
    image_bytes_processed,
    make_result,
)


class _CameraManagerCaptureMixin(BenchTestSuite):
    tags = frozenset({"hardware", "camera"})
    requires = ("camera",)
    resource_schema = None

    def _run_capture_loop(
        self,
        config: BenchSuiteConfig,
        reporter: BenchReporter,
        *,
        capture_once: bool,
    ) -> BenchResult:
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        monotonic_start = time.perf_counter()
        cameras = camera_names_from_config(config)
        output_format = str(config.parameters.get("output_format", "numpy"))
        include_mocks = bool(config.parameters.get("include_mocks", True))
        test_connection = bool(config.parameters.get("test_connection", False))
        max_concurrent = config.parameters.get("max_concurrent_captures")
        max_concurrent_captures = int(max_concurrent) if max_concurrent is not None else None
        per_camera_successes: Counter[str] = Counter()
        per_camera_failures: Counter[str] = Counter()

        manager = CameraManager(include_mocks=include_mocks, max_concurrent_captures=max_concurrent_captures)
        try:
            manager.open(cameras, test_connection=test_connection)
            deadline = reporter.deadline(config.duration_seconds)
            while not reporter.is_cancelled():
                if not capture_once and time.perf_counter() >= deadline:
                    break
                for camera in cameras:
                    op_start = time.perf_counter()
                    try:
                        image = manager.open(camera, test_connection=False).capture(output_format=output_format)
                    except Exception as exc:  # noqa: BLE001 - benchmark records failures and continues.
                        per_camera_failures[camera] += 1
                        reporter.record_operation(
                            success=False,
                            latency_seconds=time.perf_counter() - op_start,
                            error=exc,
                            camera=camera,
                        )
                        continue
                    per_camera_successes[camera] += 1
                    reporter.record_operation(
                        success=True,
                        latency_seconds=time.perf_counter() - op_start,
                        bytes_processed=image_bytes_processed(image),
                        camera=camera,
                    )
                if capture_once:
                    break
        finally:
            manager.close()

        return make_result(
            config=config,
            reporter=reporter,
            started=started,
            monotonic_start=monotonic_start,
            cameras=cameras,
            mode="camera_manager",
            extra_metrics={
                "per_camera_successes": dict(per_camera_successes),
                "per_camera_failures": dict(per_camera_failures),
                "output_format": output_format,
            },
        )


class HardwareCameraManagerCaptureSmokeSuite(_CameraManagerCaptureMixin):
    suite_id = "hardware.smoke.camera_manager_capture"
    tags = frozenset({"smoke", "hardware", "camera"})
    title = "Hardware smoke — CameraManager capture"
    description = "Opens configured cameras through CameraManager, captures one image from each, and closes them."
    safety = "Defaults to mock cameras; physical cameras are touched only when explicitly named."
    task_schema = TaskSchema(name=suite_id, input_schema=HardwareCameraInput, output_schema=BenchResultSchema)
    profiles = MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 1.0,
                "cameras": ["MockBasler:mock_basler_1"],
                "include_mocks": True,
                "output_format": "numpy",
                "test_connection": False,
            },
            "stress": {
                "duration_seconds": 1.0,
                "cameras": ["MockBasler:mock_basler_1"],
                "include_mocks": True,
                "output_format": "numpy",
                "test_connection": False,
            },
        }
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        return self._run_capture_loop(config, reporter, capture_once=True)


class HardwareCameraManagerCaptureStressSuite(_CameraManagerCaptureMixin):
    suite_id = "hardware.stress.camera_manager_capture_ceiling"
    tags = frozenset({"stress", "hardware", "camera"})
    title = "Hardware stress — CameraManager capture ceiling"
    description = "Measures repeated CameraManager capture throughput and latency for configured cameras."
    safety = "Defaults to mock cameras; physical cameras are touched only when explicitly named."
    task_schema = TaskSchema(name=suite_id, input_schema=HardwareCameraInput, output_schema=BenchResultSchema)
    profiles = MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 1.0,
                "cameras": ["MockBasler:mock_basler_1"],
                "include_mocks": True,
                "output_format": "numpy",
                "test_connection": False,
            },
            "stress": {
                "duration_seconds": 10.0,
                "cameras": ["MockBasler:mock_basler_1"],
                "include_mocks": True,
                "output_format": "numpy",
                "test_connection": False,
            },
        }
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        return self._run_capture_loop(config, reporter, capture_once=False)
