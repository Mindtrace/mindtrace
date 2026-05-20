"""Hardware benchmark suite implementations."""

from mindtrace.hardware.testing.suites.camera_manager import (
    HardwareCameraManagerCaptureStressSuite,
    HardwareCameraManagerCaptureSmokeSuite,
)
from mindtrace.hardware.testing.suites.camera_service import (
    HardwareCameraServiceCaptureStressSuite,
    HardwareCameraServiceCaptureSmokeSuite,
)

__all__ = [
    "HardwareCameraManagerCaptureSmokeSuite",
    "HardwareCameraManagerCaptureStressSuite",
    "HardwareCameraServiceCaptureSmokeSuite",
    "HardwareCameraServiceCaptureStressSuite",
]
