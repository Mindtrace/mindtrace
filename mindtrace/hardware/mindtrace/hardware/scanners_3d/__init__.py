"""3D Scanner module for structured light and other 3D scanning technologies.

This module provides support for 3D scanners including:
- Photoneo PhoXi structured light scanners
- Future: Time-of-Flight (ToF) cameras
- Future: LiDAR sensors

Usage:
    >>> from mindtrace.hardware.scanners_3d import Scanner3D, AsyncScanner3D
    >>>
    >>> # Synchronous usage
    >>> with Scanner3D() as scanner:
    ...     result = scanner.capture()
    ...     point_cloud = scanner.capture_point_cloud()
    ...     point_cloud.save_ply("output.ply")
    >>>
    >>> # Async usage
    >>> async with await AsyncScanner3D.open() as scanner:
    ...     result = await scanner.capture()
    ...     point_cloud = await scanner.capture_point_cloud()
"""

from mindtrace.hardware.scanners_3d.backends import PhotoneoBackend
from mindtrace.hardware.scanners_3d.core import (
    AsyncScanner3D,
    CoordinateMap,
    PointCloudData,
    ScanComponent,
    Scanner3D,
    ScanResult,
)

__all__ = [
    # High-level interfaces
    "Scanner3D",
    "AsyncScanner3D",
    # Data models
    "ScanResult",
    "ScanComponent",
    "CoordinateMap",
    "PointCloudData",
    # Backends
    "PhotoneoBackend",
]
