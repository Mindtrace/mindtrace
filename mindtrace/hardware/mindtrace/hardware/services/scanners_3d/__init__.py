"""Scanner3DService - Service-based 3D scanner management API."""

from mindtrace.hardware.services.scanners_3d.connection_manager import Scanner3DConnectionManager
from mindtrace.hardware.services.scanners_3d.service import Scanner3DService

# Register the custom connection manager
Scanner3DService.register_connection_manager(Scanner3DConnectionManager)

__all__ = [
    "Scanner3DService",
    "Scanner3DConnectionManager",
]
