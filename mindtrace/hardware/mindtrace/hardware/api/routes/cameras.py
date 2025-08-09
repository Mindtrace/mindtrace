"""Camera discovery and lifecycle routes for Camera API.

This module provides endpoints for discovering cameras, managing their
lifecycle (initialize/close), and checking their status.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from mindtrace.hardware.api.dependencies import (
    get_camera_manager,
    validate_backend_name,
    validate_camera_exists,
)
from mindtrace.hardware.cameras.core.camera_manager import CameraManager
from mindtrace.hardware.core.exceptions import CameraError
from mindtrace.hardware.models.requests import BatchCameraInitializeRequest, CameraInitializeRequest
from mindtrace.hardware.models.responses import (
    BatchOperationResponse,
    BoolResponse,
    ListResponse,
    StatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/discover", response_model=ListResponse)
async def discover_cameras(
    backend: Optional[str] = Query(None, description="Backend name to filter by"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_backend: Optional[str] = Depends(validate_backend_name),
) -> ListResponse:
    """Discover available cameras from all or specific backends.

    Args:
        backend: Optional backend name to filter cameras by

    Returns:
        ListResponse: List of discovered camera names in format 'Backend:device_name'

    Examples:
        - GET /api/v1/cameras/discover - All cameras from all backends
        - GET /api/v1/cameras/discover?backend=Basler - Only Basler cameras
        - GET /api/v1/cameras/discover?backend=OpenCV - Only OpenCV cameras
    """
    try:
        # Use validated backend if provided
        cameras = manager.discover_cameras(backends=validated_backend)

        logger.info(
            f"Discovered {len(cameras)} cameras"
            + (f" from backend '{validated_backend}'" if validated_backend else " from all backends")
        )

        return ListResponse(
            success=True,
            data=cameras,
            message=f"Found {len(cameras)} cameras"
            + (f" from backend '{validated_backend}'" if validated_backend else " from all backends"),
        )

    except ValueError:
        # Re-raise ValueError to let app.py handlers convert to 400
        raise
    except HTTPException:
        # Re-raise HTTPExceptions (like validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Camera discovery failed: {e}")
        raise HTTPException(status_code=500, detail=f"Camera discovery failed: {str(e)}")


@router.get("/active", response_model=ListResponse)
async def list_active_cameras(manager: CameraManager = Depends(get_camera_manager)) -> ListResponse:
    """List currently active (initialized) cameras.

    Returns:
        ListResponse: List of active camera names
    """
    try:
        active_cameras = manager.get_active_cameras()

        logger.info(f"Retrieved {len(active_cameras)} active cameras")

        return ListResponse(success=True, data=active_cameras, message=f"Found {len(active_cameras)} active cameras")

    except Exception as e:
        logger.error(f"Failed to list active cameras: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list active cameras: {str(e)}")


@router.post("/initialize", response_model=BoolResponse)
async def initialize_camera(
    request: CameraInitializeRequest, manager: CameraManager = Depends(get_camera_manager)
) -> BoolResponse:
    """Initialize a single camera.

    Args:
        request: Camera initialization request with camera name and options

    Returns:
        BoolResponse: Success status of initialization

    Raises:
        HTTPException: If camera initialization fails
    """
    try:
        # Validate camera name format
        if ":" not in request.camera:
            raise ValueError("Invalid camera name format. Expected 'Backend:device_name'")

        # Check if camera is already initialized
        active_cameras = manager.get_active_cameras()
        if request.camera in active_cameras:
            return BoolResponse(success=True, message=f"Camera '{request.camera}' is already initialized")

        # Initialize the camera
        await manager.initialize_camera(request.camera, test_connection=request.test_connection)

        logger.info(f"Successfully initialized camera '{request.camera}'")

        return BoolResponse(success=True, message=f"Camera '{request.camera}' initialized successfully")

    except CameraError as e:
        logger.error(f"Camera initialization failed for '{request.camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Camera initialization failed: {str(e)}")
    except ValueError:
        # Re-raise ValueError to let app.py handlers convert to 400
        raise
    except HTTPException:
        # Re-raise HTTPExceptions (like validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error initializing camera '{request.camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error during initialization: {str(e)}")


@router.post("/initialize/batch", response_model=BatchOperationResponse)
async def initialize_cameras_batch(
    request: BatchCameraInitializeRequest, manager: CameraManager = Depends(get_camera_manager)
) -> BatchOperationResponse:
    """Initialize multiple cameras in batch.

    Args:
        request: Batch camera initialization request

    Returns:
        BatchOperationResponse: Results of batch initialization
    """
    try:
        # Validate camera names
        for camera in request.cameras:
            if ":" not in camera:
                raise ValueError(f"Invalid camera name format '{camera}'. Expected 'Backend:device_name'")

        # Perform batch initialization
        failed_cameras = await manager.initialize_cameras(request.cameras, test_connections=request.test_connections)

        # Calculate results
        successful_count = len(request.cameras) - len(failed_cameras)
        failed_count = len(failed_cameras)

        # Create result mapping
        results = {}
        for camera in request.cameras:
            results[camera] = camera not in failed_cameras

        logger.info(f"Batch initialization completed: {successful_count} successful, {failed_count} failed")

        return BatchOperationResponse(
            success=failed_count == 0,
            results=results,
            successful_count=successful_count,
            failed_count=failed_count,
            message=f"Batch initialization completed: {successful_count} successful, {failed_count} failed",
        )

    except ValueError:
        # Re-raise ValueError to let app.py handlers convert to 400
        raise
    except HTTPException:
        # Re-raise HTTPExceptions (like validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Batch camera initialization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch initialization failed: {str(e)}")


@router.delete("/", response_model=BoolResponse)
async def close_camera(
    camera: str = Query(..., description="Camera name to close"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> BoolResponse:
    """Close a specific camera.

    Args:
        camera: Camera name to close

    Returns:
        BoolResponse: Success status of closure
    """
    try:
        await manager.close_camera(validated_camera)

        logger.info(f"Successfully closed camera '{validated_camera}'")

        return BoolResponse(success=True, message=f"Camera '{validated_camera}' closed successfully")

    except HTTPException:
        # Re-raise HTTPExceptions (like validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Failed to close camera '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to close camera: {str(e)}")


@router.delete("/all", response_model=BoolResponse)
async def close_all_cameras(manager: CameraManager = Depends(get_camera_manager)) -> BoolResponse:
    """Close all active cameras.

    Returns:
        BoolResponse: Success status of closure
    """
    try:
        active_cameras = manager.get_active_cameras()
        camera_count = len(active_cameras)

        await manager.close_all_cameras()

        logger.info(f"Successfully closed {camera_count} cameras")

        return BoolResponse(success=True, message=f"Successfully closed {camera_count} cameras")

    except Exception as e:
        logger.error(f"Failed to close all cameras: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to close all cameras: {str(e)}")


@router.get("/status", response_model=StatusResponse)
async def check_camera_connection(
    camera: str = Query(..., description="Camera name to check"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> StatusResponse:
    """Check camera connection status.

    Args:
        camera: Camera name to check

    Returns:
        StatusResponse: Camera connection status
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)
        is_connected = await camera_proxy.check_connection()

        status_info = {
            "camera": validated_camera,
            "connected": is_connected,
            "initialized": camera_proxy.is_connected,
            "backend": camera_proxy.backend,
            "device_name": camera_proxy.device_name,
        }

        logger.info(f"Camera '{validated_camera}' connection status: {is_connected}")

        return StatusResponse(
            success=is_connected,
            data=status_info,
            message=f"Camera '{validated_camera}' is {'connected' if is_connected else 'disconnected'}",
        )

    except HTTPException:
        # Re-raise HTTPExceptions (like validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Failed to check camera status for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check camera status: {str(e)}")


@router.get("/info", response_model=StatusResponse)
async def get_camera_info(
    camera: str = Query(..., description="Camera name to get info for"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> StatusResponse:
    """Get detailed camera information.

    Args:
        camera: Camera name to get info for

    Returns:
        StatusResponse: Detailed camera information
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)

        # Get sensor info and other details
        sensor_info = await camera_proxy.get_sensor_info()

        # Add additional information
        info = {
            **sensor_info,
            "camera": validated_camera,
            "backend": camera_proxy.backend,
            "device_name": camera_proxy.device_name,
            "initialized": camera_proxy.is_connected,
        }

        # Try to get current settings (if camera is connected)
        if camera_proxy.is_connected:
            try:
                info["current_exposure"] = await camera_proxy.get_exposure()
                info["current_gain"] = camera_proxy.get_gain()
                info["current_roi"] = camera_proxy.get_roi()
                info["current_pixel_format"] = camera_proxy.get_pixel_format()
            except Exception as e:
                logger.warning(f"Could not retrieve current settings for '{validated_camera}': {e}")
                info["settings_error"] = str(e)

        logger.info(f"Retrieved information for camera '{validated_camera}'")

        return StatusResponse(success=True, data=info, message=f"Camera information retrieved for '{validated_camera}'")

    except HTTPException:
        # Re-raise HTTPExceptions (like validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Failed to get camera info for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get camera information: {str(e)}")
