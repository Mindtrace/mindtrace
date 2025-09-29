"""CameraManagerService - Service-based camera management API."""

from mindtrace.hardware.api.cameras.connection_manager import CameraManagerConnectionManager
from mindtrace.hardware.api.cameras.service import CameraManagerService

# Register the custom connection manager
CameraManagerService.register_connection_manager(CameraManagerConnectionManager)

__all__ = [
    "CameraManagerService",
    "CameraManagerConnectionManager",
]
