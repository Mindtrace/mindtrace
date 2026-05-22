"""CameraManagerService benchmark suites."""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from types import MappingProxyType
from typing import Any

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema
from mindtrace.hardware.services.cameras.models import CameraOpenBatchRequest, CaptureBatchRequest
from mindtrace.hardware.services.cameras.service import CameraManagerService
from mindtrace.hardware.testing.suites._camera_common import (
    HardwareCameraInput,
    HardwareCameraServiceResources,
    camera_names_from_config,
    make_result,
    service_capture_bytes,
)


class _CameraServiceCaptureMixin(BenchTestSuite):
    tags = frozenset({"hardware", "camera", "service"})
    requires = ("camera_service",)
    resource_schema = HardwareCameraServiceResources

    async def _open_cameras(self, client: Any, cameras: list[str], *, test_connection: bool) -> Any:
        if isinstance(client, CameraManagerService):
            return await client.open_cameras_batch(
                CameraOpenBatchRequest(cameras=cameras, test_connection=test_connection)
            )
        return await client.open_cameras_batch(cameras=cameras, test_connection=test_connection)

    async def _capture_batch(self, client: Any, cameras: list[str], *, output_format: str) -> Any:
        if isinstance(client, CameraManagerService):
            return await client.capture_images_batch(CaptureBatchRequest(cameras=cameras, output_format=output_format))
        return await client.capture_images_batch(cameras=cameras, output_format=output_format)

    async def _close_all(self, client: Any) -> None:
        close_all = getattr(client, "close_all_cameras", None)
        if close_all is None:
            return
        result = close_all()
        if hasattr(result, "__await__"):
            await result

    async def _run_capture_loop_async(
        self,
        config: BenchSuiteConfig,
        reporter: BenchReporter,
        *,
        capture_once: bool,
    ) -> BenchResult:
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        monotonic_start = time.perf_counter()
        cameras = camera_names_from_config(config)
        output_format = str(config.parameters.get("output_format", "png"))
        include_mocks = bool(config.parameters.get("include_mocks", True))
        test_connection = bool(config.parameters.get("test_connection", False))
        service_url = config.resources.get("service_url")
        per_camera_successes: Counter[str] = Counter()
        per_camera_failures: Counter[str] = Counter()
        owned_service: CameraManagerService | None = None

        if service_url:
            client = CameraManagerService.connect(str(service_url))
        else:
            owned_service = CameraManagerService(include_mocks=include_mocks)
            client = owned_service

        try:
            await self._open_cameras(client, cameras, test_connection=test_connection)
            deadline = reporter.deadline(config.duration_seconds)
            while not reporter.is_cancelled():
                if not capture_once and time.perf_counter() >= deadline:
                    break
                op_start = time.perf_counter()
                try:
                    response = await self._capture_batch(client, cameras, output_format=output_format)
                except Exception as exc:  # noqa: BLE001 - benchmark records failures and continues.
                    for camera in cameras:
                        per_camera_failures[camera] += 1
                    reporter.record_operation(
                        success=False,
                        latency_seconds=time.perf_counter() - op_start,
                        error=exc,
                        cameras=cameras,
                    )
                    if capture_once:
                        break
                    continue

                data = response.get("data", response) if isinstance(response, dict) else getattr(response, "data", {})
                failed_count = int(
                    response.get("failed_count", 0)
                    if isinstance(response, dict)
                    else getattr(response, "failed_count", 0)
                )
                success = failed_count == 0
                bytes_processed = 0
                if isinstance(data, dict):
                    for camera, result in data.items():
                        result_success = (
                            bool(result.get("success", True))
                            if isinstance(result, dict)
                            else bool(getattr(result, "success", True))
                        )
                        if result_success:
                            per_camera_successes[str(camera)] += 1
                        else:
                            per_camera_failures[str(camera)] += 1
                        bytes_processed += service_capture_bytes(result)
                reporter.record_operation(
                    success=success,
                    latency_seconds=time.perf_counter() - op_start,
                    bytes_processed=bytes_processed,
                    cameras=cameras,
                )
                if capture_once:
                    break
        finally:
            await self._close_all(client)
            if owned_service is not None:
                await owned_service.shutdown_cleanup()

        return make_result(
            config=config,
            reporter=reporter,
            started=started,
            monotonic_start=monotonic_start,
            cameras=cameras,
            mode="camera_manager_service",
            extra_metrics={
                "per_camera_successes": dict(per_camera_successes),
                "per_camera_failures": dict(per_camera_failures),
                "output_format": output_format,
                "service_url": str(service_url) if service_url else None,
            },
        )

    def _run_capture_loop(
        self,
        config: BenchSuiteConfig,
        reporter: BenchReporter,
        *,
        capture_once: bool,
    ) -> BenchResult:
        return asyncio.run(self._run_capture_loop_async(config, reporter, capture_once=capture_once))


class HardwareCameraServiceCaptureSmokeSuite(_CameraServiceCaptureMixin):
    suite_id = "hardware.smoke.camera_service_capture"
    title = "Hardware smoke — CameraManagerService capture"
    description = (
        "Opens configured cameras through CameraManagerService, captures one image from each, and closes them."
    )
    safety = "Defaults to mock cameras and in-process service; physical cameras are touched only when explicitly named."
    task_schema = TaskSchema(name=suite_id, input_schema=HardwareCameraInput, output_schema=BenchResultSchema)
    profiles = MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 1.0,
                "cameras": ["MockBasler:mock_basler_1"],
                "include_mocks": True,
                "output_format": "png",
                "test_connection": False,
            },
            "stress": {
                "duration_seconds": 1.0,
                "cameras": ["MockBasler:mock_basler_1"],
                "include_mocks": True,
                "output_format": "png",
                "test_connection": False,
            },
        }
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        return self._run_capture_loop(config, reporter, capture_once=True)


class HardwareCameraServiceCaptureStressSuite(_CameraServiceCaptureMixin):
    suite_id = "hardware.stress.camera_service_capture_ceiling"
    title = "Hardware stress — CameraManagerService capture ceiling"
    description = "Measures repeated CameraManagerService capture throughput and latency for configured cameras."
    safety = "Defaults to mock cameras and in-process service; physical cameras are touched only when explicitly named."
    task_schema = TaskSchema(name=suite_id, input_schema=HardwareCameraInput, output_schema=BenchResultSchema)
    profiles = MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 1.0,
                "cameras": ["MockBasler:mock_basler_1"],
                "include_mocks": True,
                "output_format": "png",
                "test_connection": False,
            },
            "stress": {
                "duration_seconds": 10.0,
                "cameras": ["MockBasler:mock_basler_1"],
                "include_mocks": True,
                "output_format": "png",
                "test_connection": False,
            },
        }
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        return self._run_capture_loop(config, reporter, capture_once=False)
