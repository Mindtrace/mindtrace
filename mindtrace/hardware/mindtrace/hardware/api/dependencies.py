"""
Camera Manager utilities for the Camera API Service.
"""

from mindtrace.hardware.cameras.camera_manager import CameraManager

# Global CameraManager instance for dependency injection
_camera_manager: CameraManager = None


def get_camera_manager() -> CameraManager:
    """Get the shared CameraManager instance using dependency injection pattern."""
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager(include_mocks=False)
    return _camera_manager


def reset_camera_manager():
    """Reset the CameraManager instance (useful for testing)."""
    global _camera_manager
    if _camera_manager:
        _camera_manager = None
