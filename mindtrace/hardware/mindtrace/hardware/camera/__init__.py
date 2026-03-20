"""Camera sub-package for mindtrace-hardware.

Provides a unified, synchronous interface for camera backends including
GigE Vision (via harvesters / pypylon) and an in-memory mock for testing.
"""

from __future__ import annotations

from mindtrace.hardware.camera.base import AbstractCamera, CameraFrame, CameraStatus
from mindtrace.hardware.camera.gige import GigECamera
from mindtrace.hardware.camera.mock import MockCamera

__all__ = [
    "AbstractCamera",
    "CameraFrame",
    "CameraStatus",
    "GigECamera",
    "MockCamera",
]
