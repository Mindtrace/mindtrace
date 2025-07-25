"""
Camera backends for different manufacturers and types.

This module provides camera backend implementations for the Mindtrace hardware system.
Each backend implements the BaseCamera interface for consistent camera operations.

Available Backends:
    - BaseCamera: Abstract base class defining the camera interface
    - DahengCamera: Industrial cameras from Daheng Imaging (when available)
    - BaslerCamera: Industrial cameras from Basler (when available)
    - OpenCVCamera: USB cameras and webcams via OpenCV (when available)

Usage:
from mindtrace.hardware.cameras.backends import BaseCamera
from mindtrace.hardware.cameras.backends.daheng import DahengCamera
from mindtrace.hardware.cameras.backends.basler import BaslerCamera
from mindtrace.hardware.cameras.backends.opencv import OpenCVCamera

Configuration:
    Camera backends integrate with the Mindtrace configuration system
    to provide consistent default values and settings across all camera types.
"""

from .base import BaseCamera

__all__ = ["BaseCamera"]
