"""Dependencies for Camera API.

This module provides FastAPI dependency injection for the CameraManager
and other shared resources.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, HTTPException

from mindtrace.hardware.cameras.core.camera_manager import CameraManager

logger = logging.getLogger(__name__)


# Global CameraManager instance
_camera_manager: Optional[CameraManager] = None


class CameraManagerDependency:
    """Dependency class for CameraManager with proper lifecycle management."""

    def __init__(self):
        self._manager: Optional[CameraManager] = None
        self._initialized = False

    async def get_manager(self) -> CameraManager:
        """Get or create the CameraManager instance."""
        if self._manager is None:
            try:
                logger.info("Initializing CameraManager...")
                self._manager = CameraManager(include_mocks=False)
                # CameraManager doesn't need async initialization, but we mark it as initialized
                self._initialized = True
                logger.info("CameraManager initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize CameraManager: {e}")
                raise HTTPException(status_code=503, detail=f"Camera system unavailable: {str(e)}")

        return self._manager

    async def close(self):
        """Close the CameraManager and cleanup resources."""
        if self._manager is not None:
            try:
                logger.info("Closing CameraManager...")
                await self._manager.close()
                await self._manager.__aexit__(None, None, None)
                self._manager = None
                self._initialized = False
                logger.info("CameraManager closed successfully")
            except Exception as e:
                logger.error(f"Error closing CameraManager: {e}")


# Global dependency instance
camera_manager_dependency = CameraManagerDependency()


async def get_camera_manager() -> CameraManager:
    """FastAPI dependency to get the CameraManager instance.

    Returns:
        CameraManager: The camera manager instance

    Raises:
        HTTPException: If CameraManager cannot be initialized
    """
    return await camera_manager_dependency.get_manager()


async def get_camera_manager_with_validation() -> CameraManager:
    """FastAPI dependency to get the CameraManager with additional validation.

    Returns:
        CameraManager: The camera manager instance

    Raises:
        HTTPException: If CameraManager is not available or has issues
    """
    manager = await get_camera_manager()

    # Validate that the manager is working
    try:
        # Test basic functionality by getting available backends
        backends = manager._discovered_backends
        if not backends:
            logger.warning("No camera backends discovered")
            raise HTTPException(status_code=503, detail="No camera backends available")

        return manager
    except Exception as e:
        logger.error(f"CameraManager validation failed: {e}")
        raise HTTPException(status_code=503, detail=f"Camera system validation failed: {str(e)}")


@asynccontextmanager
async def lifespan_manager():
    """Context manager for application lifespan management.

    This can be used with FastAPI's lifespan events to properly
    initialize and cleanup the CameraManager.
    """
    try:
        # Initialize CameraManager
        await camera_manager_dependency.get_manager()
        yield
    finally:
        # Cleanup CameraManager
        await camera_manager_dependency.close()


# Dependency for specific camera validation
async def validate_camera_name(camera: str) -> str:
    """Dependency to validate camera name format.

    Args:
        camera: Camera name in format 'Backend:device_name'

    Returns:
        str: Validated camera name

    Raises:
        ValueError: If camera name format is invalid
    """
    if not camera or ":" not in camera:
        raise ValueError("Invalid camera name format. Expected 'Backend:device_name'")

    backend, device_name = camera.split(":", 1)

    if not backend or not device_name:
        raise ValueError("Invalid camera name format. Backend and device name cannot be empty")

    return camera


# Dependency for camera existence validation
async def validate_camera_exists(
    camera: str = Depends(validate_camera_name), manager: CameraManager = Depends(get_camera_manager)
) -> str:
    """Dependency to validate that a camera exists and is initialized.

    Args:
        camera: Camera name in format 'Backend:device_name'
        manager: CameraManager instance

    Returns:
        str: Validated camera name

    Raises:
        CameraNotFoundError: If camera doesn't exist or isn't initialized
        CameraError: If camera system error occurs
    """
    # Check if camera is initialized
    active_cameras = manager.active_cameras
    if camera not in active_cameras:
        # Import here to avoid circular imports
        from mindtrace.hardware.core.exceptions import CameraNotFoundError

        raise CameraNotFoundError(f"Camera '{camera}' is not initialized. Use POST /api/v1/cameras/initialize first.")

    return camera


# Dependency for backend validation
async def validate_backend_name(backend: Optional[str] = None) -> Optional[str]:
    """Dependency to validate backend name if provided.

    Args:
        backend: Optional backend name

    Returns:
        Optional[str]: Validated backend name or None

    Raises:
        ValueError: If backend name is invalid
    """
    if backend is None:
        return None

    # List of valid backends (could be dynamically determined)
    valid_backends = ["Basler", "OpenCV", "MockBasler"]

    if backend not in valid_backends:
        raise ValueError(f"Invalid backend '{backend}'. Valid backends: {', '.join(valid_backends)}")

    return backend


# Utility function for cleanup on shutdown
async def cleanup_camera_manager():
    """Cleanup function to be called on application shutdown."""
    await camera_manager_dependency.close()
