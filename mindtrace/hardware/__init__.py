"""
Hardware module with lazy imports to avoid cross-contamination.

This module provides lazy imports for CameraManager and PLCManager to prevent
SWIG warnings from pycomm3 appearing in camera tests.
"""

def __getattr__(name):
    """Lazy import implementation to avoid loading all backends at once."""
    if name == "CameraManager":
        from .cameras.camera_manager import CameraManager
        return CameraManager
    elif name == "PLCManager":
        from .plcs.plc_manager import PLCManager
        return PLCManager
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = ["CameraManager", "PLCManager"]