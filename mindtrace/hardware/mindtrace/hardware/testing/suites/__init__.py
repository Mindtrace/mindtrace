"""Hardware benchmark suite implementations."""

from mindtrace.hardware.testing.suites.camera_manager import (
    HardwareCameraManagerCaptureSmokeSuite,
    HardwareCameraManagerCaptureStressSuite,
)
from mindtrace.hardware.testing.suites.camera_service import (
    HardwareCameraServiceCaptureSmokeSuite,
    HardwareCameraServiceCaptureStressSuite,
)

__all__ = [
    "HardwareCameraManagerCaptureSmokeSuite",
    "HardwareCameraManagerCaptureStressSuite",
    "HardwareCameraServiceCaptureSmokeSuite",
    "HardwareCameraServiceCaptureStressSuite",
]
