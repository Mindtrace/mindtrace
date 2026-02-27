"""Core 3D scanner interfaces and models."""

from mindtrace.hardware.scanners_3d.core.async_scanner_3d import AsyncScanner3D
from mindtrace.hardware.scanners_3d.core.models import (
    # Configuration enums
    CameraSpace,
    CodingQuality,
    CodingStrategy,
    # Data models
    CoordinateMap,
    HardwareTriggerSignal,
    OperationMode,
    OutputTopology,
    PointCloudData,
    ScanComponent,
    # Configuration models
    ScannerCapabilities,
    ScannerConfiguration,
    ScanResult,
    TextureSource,
    TriggerMode,
)
from mindtrace.hardware.scanners_3d.core.scanner_3d import Scanner3D

__all__ = [
    # Core classes
    "AsyncScanner3D",
    "Scanner3D",
    # Data models
    "ScanResult",
    "ScanComponent",
    "CoordinateMap",
    "PointCloudData",
    # Configuration
    "ScannerConfiguration",
    "ScannerCapabilities",
    # Enums
    "OperationMode",
    "CodingStrategy",
    "CodingQuality",
    "TextureSource",
    "OutputTopology",
    "CameraSpace",
    "TriggerMode",
    "HardwareTriggerSignal",
]
