"""Embedded benchmark suites for ``mindtrace-hardware``.

Use ``register_benchmark_suites`` directly or discover it through the
``mindtrace.benchmark_suites`` entry point group.
"""

from __future__ import annotations

from mindtrace.core import TestRunner


def register_benchmark_suites(*, runner: TestRunner | None = None, replace: bool = True) -> None:
    """Register hardware benchmark suites on ``runner`` or the default runner."""

    target = runner or TestRunner.default()

    from mindtrace.hardware.testing.suites.camera_manager import (
        HardwareCameraManagerCaptureStressSuite,
        HardwareCameraManagerCaptureSmokeSuite,
    )
    from mindtrace.hardware.testing.suites.camera_service import (
        HardwareCameraServiceCaptureStressSuite,
        HardwareCameraServiceCaptureSmokeSuite,
    )

    for cls in (
        HardwareCameraManagerCaptureSmokeSuite,
        HardwareCameraManagerCaptureStressSuite,
        HardwareCameraServiceCaptureSmokeSuite,
        HardwareCameraServiceCaptureStressSuite,
    ):
        if replace or cls.suite_id not in target.registered_suites():
            target.register_test_suite(cls, replace=replace)
