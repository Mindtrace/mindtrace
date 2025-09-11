"""CameraManagerService - Service-based camera management API."""

from .connection_manager import CameraManagerConnectionManager
from .service import CameraManagerService

# Register the custom connection manager
CameraManagerService.register_connection_manager(CameraManagerConnectionManager)

__all__ = [
    "CameraManagerService",
    "CameraManagerConnectionManager",
]