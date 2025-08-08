"""Camera module for mindtrace hardware.

Provides unified camera management across different camera manufacturers with graceful SDK handling and comprehensive 
error management.
"""

# ruff: noqa
# this is too weird for ruff to work out what's going on

from mindtrace.hardware.cameras.backends.camera_backend import CameraBackend
from mindtrace.hardware.cameras.camera_manager import CameraManager
from mindtrace.hardware.cameras.camera import Camera


# Lazy import availability flags to avoid loading SDKs unnecessarily
def __getattr__(name):
    """Lazy import implementation for availability flags."""
    if name == "BASLER_AVAILABLE":
        try:
            from .backends.basler import BASLER_AVAILABLE

            return BASLER_AVAILABLE
        except ImportError:
            return False
    elif name == "OPENCV_AVAILABLE":
        try:
            from .backends.opencv import OPENCV_AVAILABLE

            return OPENCV_AVAILABLE
        except ImportError:
            return False
    elif name == "SETUP_AVAILABLE":
        try:
            from .setup import (
                configure_firewall,
                install_pylon_sdk,
                setup_all_cameras,
                uninstall_pylon_sdk,
            )

            return True
        except ImportError:
            return False
    elif name in [
        "install_pylon_sdk",
        "uninstall_pylon_sdk",
        "setup_all_cameras",
        "configure_firewall",
    ]:
        try:
            from .setup import (
                configure_firewall,
                install_pylon_sdk,
                setup_all_cameras,
                uninstall_pylon_sdk,
            )

            return locals()[name]
        except ImportError:
            raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    # Core camera functionality
    "CameraManager",
    "CameraBackend",
    "Camera",
    # Availability flags
    "BASLER_AVAILABLE",
    "OPENCV_AVAILABLE",
    "SETUP_AVAILABLE",
    # Setup utilities (available if setup module can be imported)
    "install_pylon_sdk",
    "uninstall_pylon_sdk",
    "setup_all_cameras",
    "configure_firewall",
]
