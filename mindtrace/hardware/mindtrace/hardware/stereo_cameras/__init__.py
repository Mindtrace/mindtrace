"""Stereo camera support for MindTrace hardware system.

This module provides backends and utilities for stereo camera systems
that output multi-component data (intensity, disparity, depth, point clouds).

Available components:
    - backends: Stereo camera backend implementations
    - core: Core stereo camera management classes
    - setup: Installation scripts for stereo camera SDKs

Quick Start:
    >>> from mindtrace.hardware.stereo_cameras import StereoCamera
    >>>
    >>> # Open first available stereo camera
    >>> camera = StereoCamera()
    >>>
    >>> # Capture multi-component data
    >>> result = camera.capture()
    >>> print(f"Intensity: {result.intensity.shape}")
    >>> print(f"Disparity: {result.disparity.shape}")
    >>>
    >>> # Generate point cloud
    >>> point_cloud = camera.capture_point_cloud()
    >>> point_cloud.save_ply("output.ply")
    >>>
    >>> camera.close()
"""

from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend
from mindtrace.hardware.stereo_cameras.core import (
    AsyncStereoCamera,
    PointCloudData,
    StereoCalibrationData,
    StereoCamera,
    StereoGrabResult,
)

__all__ = [
    # Core interfaces
    "StereoCamera",
    "AsyncStereoCamera",
    # Data models
    "StereoGrabResult",
    "StereoCalibrationData",
    "PointCloudData",
    # Backends
    "BaslerStereoAceBackend",
]
