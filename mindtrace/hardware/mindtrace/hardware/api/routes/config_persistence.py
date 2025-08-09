"""
Configuration Persistence API Routes

Handles camera configuration export and import operations.
Provides endpoints for saving and loading camera configurations to/from files.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from mindtrace.hardware.api.dependencies import get_camera_manager, validate_camera_exists
from mindtrace.hardware.cameras.core.camera_manager import CameraManager
from mindtrace.hardware.core.exceptions import CameraError
from mindtrace.hardware.models.requests import ConfigFileRequest
from mindtrace.hardware.models.responses import (
    BatchOperationResponse,
    BoolResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/export", response_model=BoolResponse)
async def export_config(
    request: ConfigFileRequest,
    validated_camera: str = Depends(validate_camera_exists),
    manager: CameraManager = Depends(get_camera_manager),
) -> BoolResponse:
    """
    Export camera configuration to a file.

    Saves the current camera configuration (exposure, gain, ROI, etc.) to a specified file.
    The configuration file uses JSON format and includes all current camera settings.

    Args:
        request: Export configuration request with camera name and file path
        validated_camera: Validated camera name (from dependency)
        manager: Camera manager instance

    Returns:
        BoolResponse: Success status and message

    Raises:
        404: If camera is not found or not initialized
        422: If export operation fails
        500: If unexpected error occurs
    """
    try:
        logger.info(f"Exporting configuration for camera '{validated_camera}' to '{request.config_path}'")

        # Get camera and export configuration
        camera = manager.get_camera(validated_camera)
        success = await camera.save_config(request.config_path)

        if success:
            logger.info(f"Configuration exported successfully for camera '{validated_camera}'")
            return BoolResponse(
                success=True, data=True, message=f"Configuration exported successfully to '{request.config_path}'"
            )
        else:
            logger.error(f"Failed to export configuration for camera '{validated_camera}'")
            raise HTTPException(
                status_code=422, detail=f"Failed to export configuration for camera '{validated_camera}'"
            )

    except CameraError as e:
        logger.error(f"Camera error during export for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Camera error during export: {str(e)}")
    except ValueError:
        # Re-raise ValueError to let app.py handlers convert to 400
        raise
    except HTTPException:
        # Re-raise HTTPExceptions (like validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error exporting config for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error during export: {str(e)}")


@router.post("/import", response_model=BoolResponse)
async def import_config(
    request: ConfigFileRequest,
    validated_camera: str = Depends(validate_camera_exists),
    manager: CameraManager = Depends(get_camera_manager),
) -> BoolResponse:
    """
    Import camera configuration from a file.

    Loads camera configuration from a specified file and applies it to the camera.
    The configuration file should be in JSON format with camera settings.

    Args:
        request: Import configuration request with camera name and file path
        validated_camera: Validated camera name (from dependency)
        manager: Camera manager instance

    Returns:
        BoolResponse: Success status and message

    Raises:
        404: If camera is not found or not initialized
        422: If import operation fails
        500: If unexpected error occurs
    """
    try:
        logger.info(f"Importing configuration for camera '{validated_camera}' from '{request.config_path}'")

        # Get camera and import configuration
        camera = manager.get_camera(validated_camera)
        success = await camera.load_config(request.config_path)

        if success:
            logger.info(f"Configuration imported successfully for camera '{validated_camera}'")
            return BoolResponse(
                success=True, data=True, message=f"Configuration imported successfully from '{request.config_path}'"
            )
        else:
            logger.error(f"Failed to import configuration for camera '{validated_camera}'")
            raise HTTPException(
                status_code=422, detail=f"Failed to import configuration for camera '{validated_camera}'"
            )

    except CameraError as e:
        logger.error(f"Camera error during import for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Camera error during import: {str(e)}")
    except ValueError:
        # Re-raise ValueError to let app.py handlers convert to 400
        raise
    except HTTPException:
        # Re-raise HTTPExceptions (like validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error importing config for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error during import: {str(e)}")


@router.get("/export/batch", response_model=BatchOperationResponse)
async def export_batch_config(
    cameras: str,  # Comma-separated list of camera names
    config_path_pattern: str,  # Path pattern with {camera} placeholder
    manager: CameraManager = Depends(get_camera_manager),
) -> BatchOperationResponse:
    """
    Export configurations from multiple cameras to files.

    Exports configurations from multiple cameras using a path pattern.
    The path pattern should include {camera} placeholder for camera names.

    Args:
        cameras: Comma-separated list of camera names
        config_path_pattern: Path pattern with {camera} placeholder (e.g., "config_{camera}.json")
        manager: Camera manager instance

    Returns:
        BatchOperationResponse: Results of batch export operation

    Raises:
        422: If export fails for any camera
        500: If unexpected error occurs
    """
    try:
        camera_list = [cam.strip() for cam in cameras.split(",")]
        logger.info(f"Exporting configurations for {len(camera_list)} cameras")

        # Validate camera names
        for camera_name in camera_list:
            if ":" not in camera_name:
                raise ValueError(f"Invalid camera name format '{camera_name}'. Expected 'Backend:device_name'")

        # Perform batch export
        results = {}
        for camera_name in camera_list:
            try:
                # Generate path for this camera
                safe_camera_name = camera_name.replace(":", "_")
                config_path = config_path_pattern.replace("{camera}", safe_camera_name)

                camera = manager.get_camera(camera_name)
                success = await camera.save_config(config_path)
                results[camera_name] = success

            except Exception as e:
                logger.error(f"Export failed for camera '{camera_name}': {e}")
                results[camera_name] = False

        successful_count = sum(1 for success in results.values() if success)
        failed_count = len(results) - successful_count

        logger.info(f"Batch export completed: {successful_count} successful, {failed_count} failed")

        return BatchOperationResponse(
            success=failed_count == 0,
            results=results,
            successful_count=successful_count,
            failed_count=failed_count,
            message=f"Batch export completed: {successful_count} successful, {failed_count} failed",
        )

    except ValueError:
        # Re-raise ValueError to let app.py handlers convert to 400
        raise
    except Exception as e:
        logger.error(f"Batch export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch export error: {str(e)}")


@router.get("/import/batch", response_model=BatchOperationResponse)
async def import_batch_config(
    cameras: str,  # Comma-separated list of camera names
    config_path_pattern: str,  # Path pattern with {camera} placeholder
    manager: CameraManager = Depends(get_camera_manager),
) -> BatchOperationResponse:
    """
    Import configurations to multiple cameras from files.

    Imports configurations to multiple cameras using a path pattern.
    The path pattern should include {camera} placeholder for camera names.

    Args:
        cameras: Comma-separated list of camera names
        config_path_pattern: Path pattern with {camera} placeholder (e.g., "config_{camera}.json")
        manager: Camera manager instance

    Returns:
        BatchOperationResponse: Results of batch import operation

    Raises:
        422: If import fails for any camera
        500: If unexpected error occurs
    """
    try:
        camera_list = [cam.strip() for cam in cameras.split(",")]
        logger.info(f"Importing configurations for {len(camera_list)} cameras")

        # Validate camera names
        for camera_name in camera_list:
            if ":" not in camera_name:
                raise ValueError(f"Invalid camera name format '{camera_name}'. Expected 'Backend:device_name'")

        # Perform batch import
        results = {}
        for camera_name in camera_list:
            try:
                # Generate path for this camera
                safe_camera_name = camera_name.replace(":", "_")
                config_path = config_path_pattern.replace("{camera}", safe_camera_name)

                camera = manager.get_camera(camera_name)
                success = await camera.load_config(config_path)
                results[camera_name] = success

            except Exception as e:
                logger.error(f"Import failed for camera '{camera_name}': {e}")
                results[camera_name] = False

        successful_count = sum(1 for success in results.values() if success)
        failed_count = len(results) - successful_count

        logger.info(f"Batch import completed: {successful_count} successful, {failed_count} failed")

        return BatchOperationResponse(
            success=failed_count == 0,
            results=results,
            successful_count=successful_count,
            failed_count=failed_count,
            message=f"Batch import completed: {successful_count} successful, {failed_count} failed",
        )

    except ValueError:
        # Re-raise ValueError to let app.py handlers convert to 400
        raise
    except Exception as e:
        logger.error(f"Batch import failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch import error: {str(e)}")
