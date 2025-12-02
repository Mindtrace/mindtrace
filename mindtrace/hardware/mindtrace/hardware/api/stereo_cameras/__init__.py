"""StereoCameraService - Service-based stereo camera management API."""

from mindtrace.hardware.api.stereo_cameras.connection_manager import StereoCameraConnectionManager
from mindtrace.hardware.api.stereo_cameras.service import StereoCameraService

# Register the custom connection manager
StereoCameraService.register_connection_manager(StereoCameraConnectionManager)

__all__ = [
    "StereoCameraService",
    "StereoCameraConnectionManager",
]
