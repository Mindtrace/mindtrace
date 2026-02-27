"""Hardware API modules - lazy imports for independent service operation."""

__all__ = [
    "CameraManagerService",
    "CameraManagerConnectionManager",
    "PLCManagerService",
    "PLCManagerConnectionManager",
    "SensorManagerService",
    "SensorConnectionManager",
    "StereoCameraService",
    "StereoCameraConnectionManager",
    "Scanner3DService",
    "Scanner3DConnectionManager",
]


def __getattr__(name: str):
    """Lazy import to avoid loading all services when only one is needed."""
    if name in ("CameraManagerService", "CameraManagerConnectionManager"):
        from mindtrace.hardware.services.cameras import CameraManagerConnectionManager, CameraManagerService

        return CameraManagerService if name == "CameraManagerService" else CameraManagerConnectionManager

    if name in ("PLCManagerService", "PLCManagerConnectionManager"):
        from mindtrace.hardware.services.plcs import PLCManagerConnectionManager, PLCManagerService

        return PLCManagerService if name == "PLCManagerService" else PLCManagerConnectionManager

    if name in ("SensorManagerService", "SensorConnectionManager"):
        from mindtrace.hardware.services.sensors import SensorConnectionManager, SensorManagerService

        return SensorManagerService if name == "SensorManagerService" else SensorConnectionManager

    if name in ("StereoCameraService", "StereoCameraConnectionManager"):
        from mindtrace.hardware.services.stereo_cameras import StereoCameraConnectionManager, StereoCameraService

        return StereoCameraService if name == "StereoCameraService" else StereoCameraConnectionManager

    if name in ("Scanner3DService", "Scanner3DConnectionManager"):
        from mindtrace.hardware.services.scanners_3d import Scanner3DConnectionManager, Scanner3DService

        return Scanner3DService if name == "Scanner3DService" else Scanner3DConnectionManager

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
