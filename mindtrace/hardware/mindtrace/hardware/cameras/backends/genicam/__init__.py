"""GenICam Camera Backend Module"""

try:
    from harvesters.core import Harvester
    HARVESTERS_AVAILABLE = True
    
    # Optional PFNC imports - not critical for basic functionality
    try:
        from harvesters.util.pfnc import PFNC_VERSION_1_0, PFNC_VERSION_2_0, PFNC_VERSION_2_1
    except ImportError:
        pass  # PFNC constants not available in this version
        
except ImportError:  # pragma: no cover
    HARVESTERS_AVAILABLE = False
    Harvester = None

from .genicam_camera_backend import GenICamCameraBackend, GENICAM_AVAILABLE
from .mock_genicam_camera_backend import MockGenICamCameraBackend

__all__ = [
    "GenICamCameraBackend",
    "MockGenICamCameraBackend",
    "GENICAM_AVAILABLE",
    "HARVESTERS_AVAILABLE",
]