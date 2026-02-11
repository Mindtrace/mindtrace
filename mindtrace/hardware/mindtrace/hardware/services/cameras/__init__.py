"""CameraManagerService - Service-based camera management API."""

from mindtrace.hardware.services.cameras.connection_manager import CameraManagerConnectionManager
from mindtrace.hardware.services.cameras.service import CameraManagerService

# Register the custom connection manager
CameraManagerService.register_connection_manager(CameraManagerConnectionManager)

__all__ = [
    "CameraManagerService",
    "CameraManagerConnectionManager",
]
