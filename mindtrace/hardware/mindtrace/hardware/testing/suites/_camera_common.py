"""Shared helpers for camera benchmark suites."""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, Field

from mindtrace.core import BenchReporter, BenchResult, BenchSuiteConfig, utc_now_iso

DEFAULT_MOCK_CAMERAS = ("MockBasler:mock_basler_1",)


class HardwareCameraInput(BaseModel):
    cameras: list[str] = Field(
        default_factory=lambda: list(DEFAULT_MOCK_CAMERAS),
        description="Camera names to open and capture from. Mock camera names are valid defaults.",
    )
    include_mocks: bool = Field(True, description="Whether discovery/open should include mock cameras.")
    output_format: Literal["numpy", "pil", "png", "jpeg", "jpg"] = Field(
        "numpy",
        description="Capture output format. Service suites may use an encoded wire format such as png.",
    )
    max_concurrent_captures: int | None = Field(
        None,
        ge=1,
        description="Optional CameraManager concurrency limit for batch capture.",
    )
    test_connection: bool = Field(False, description="Whether to test camera connections during open.")


class HardwareCameraServiceResources(BaseModel):
    service_url: str | None = Field(
        None,
        description=(
            "Optional CameraManagerService base URL. If omitted, the suite instantiates CameraManagerService in-process."
        ),
    )


def camera_names_from_config(config: BenchSuiteConfig) -> list[str]:
    raw = config.parameters.get("cameras") or DEFAULT_MOCK_CAMERAS
    if isinstance(raw, str):
        names = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        names = [str(item).strip() for item in raw if str(item).strip()]
    if not names:
        raise ValueError("At least one camera name is required")
    return names


def status_from_reporter(reporter: BenchReporter) -> str:
    return "passed" if reporter.operations > 0 and reporter.failures == 0 else "failed"


def image_bytes_processed(image: Any) -> int:
    if image is None:
        return 0
    nbytes = getattr(image, "nbytes", None)
    if isinstance(nbytes, int):
        return nbytes
    size = getattr(image, "size", None)
    if isinstance(size, tuple) and size:
        bands = len(getattr(image, "getbands", lambda: ())()) or 1
        total = 1
        for dim in size:
            total *= int(dim)
        return total * bands
    if isinstance(size, int):
        return size
    if isinstance(image, (bytes, bytearray, memoryview)):
        return len(image)
    return 0


def service_capture_bytes(result: Any) -> int:
    if result is None:
        return 0
    if isinstance(result, dict):
        file_size = result.get("file_size_bytes")
        if isinstance(file_size, int):
            return file_size
        image_data = result.get("image_data")
        if isinstance(image_data, str):
            return len(image_data)
        image_size = result.get("image_size")
    else:
        file_size = getattr(result, "file_size_bytes", None)
        if isinstance(file_size, int):
            return file_size
        image_data = getattr(result, "image_data", None)
        if isinstance(image_data, str):
            return len(image_data)
        image_size = getattr(result, "image_size", None)
    if isinstance(image_size, Iterable) and not isinstance(image_size, (str, bytes, bytearray)):
        dims = [int(dim) for dim in image_size]
        if len(dims) >= 2:
            return dims[0] * dims[1]
    return 0


def make_result(
    *,
    config: BenchSuiteConfig,
    reporter: BenchReporter,
    started: str,
    monotonic_start: float,
    cameras: list[str],
    mode: str,
    extra_metrics: dict[str, Any] | None = None,
) -> BenchResult:
    elapsed = time.perf_counter() - monotonic_start
    return BenchResult(
        suite_id=config.suite_id,
        status=status_from_reporter(reporter),
        started_at=started,
        ended_at=utc_now_iso(),
        duration_seconds=elapsed,
        operations=reporter.operations,
        successes=reporter.successes,
        failures=reporter.failures,
        bytes_processed=reporter.bytes_processed,
        latency_seconds=reporter.latency_seconds,
        error_counts=reporter.error_counts,
        metrics={
            **reporter.metrics,
            "mode": mode,
            "camera_count": len(cameras),
            "cameras": cameras,
            **(extra_metrics or {}),
        },
    )
