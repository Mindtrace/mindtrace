"""Camera backends for different manufacturers and types.

This module provides camera backend implementations for the Mindtrace hardware system.
Each backend implements the CameraBackend interface for consistent camera operations.

Available Backends:
    - CameraBackend: Abstract base class defining the camera interface
    - BaslerCameraBackend: Industrial cameras from Basler (when available)
    - OpenCVCameraBackend: USB cameras and webcams via OpenCV (when available)

Usage:
from mindtrace.hardware.cameras.backends import CameraBackend
from mindtrace.hardware.cameras.backends.basler import BaslerCameraBackend
from mindtrace.hardware.cameras.backends.opencv import OpenCVCameraBackend

Configuration:
    Camera backends integrate with the Mindtrace configuration system
    to provide consistent default values and settings across all camera types.
"""

from mindtrace.hardware.cameras.backends.camera_backend import CameraBackend

__all__ = ["CameraBackend"]
