"""
Async configuration routes for Camera API.

This module provides endpoints for camera settings that require async operations:
- Exposure control
- Trigger mode
- White balance
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from mindtrace.hardware.api.dependencies import get_camera_manager, validate_camera_exists
from mindtrace.hardware.cameras.camera_manager import CameraManager
from mindtrace.hardware.core.exceptions import CameraError
from mindtrace.hardware.models.requests import (
    BatchCameraConfigRequest,
    ExposureRequest,
    TriggerModeRequest,
    WhiteBalanceRequest,
)
from mindtrace.hardware.models.responses import (
    BatchOperationResponse,
    BoolResponse,
    FloatResponse,
    RangeResponse,
    StringResponse,
    WhiteBalanceListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# Exposure Control Endpoints
@router.get("/exposure", response_model=FloatResponse)
async def get_exposure(
    camera: str = Query(..., description="Camera name"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> FloatResponse:
    """
    Get current camera exposure time.

    Args:
        camera: Camera name in format 'Backend:device_name'

    Returns:
        FloatResponse: Current exposure time in microseconds
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)
        exposure = await camera_proxy.get_exposure()

        logger.info(f"Retrieved exposure for '{validated_camera}': {exposure} μs")

        return FloatResponse(success=True, data=exposure, message=f"Current exposure: {exposure} μs")

    except CameraError as e:
        logger.error(f"Failed to get exposure for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Failed to get exposure: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting exposure for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.put("/exposure", response_model=BoolResponse)
async def set_exposure(request: ExposureRequest, manager: CameraManager = Depends(get_camera_manager)) -> BoolResponse:
    """
    Set camera exposure time.

    Args:
        request: Exposure setting request

    Returns:
        BoolResponse: Success status of exposure setting
    """
    try:
        # Validate camera exists (done by dependency)
        if ":" not in request.camera:
            raise HTTPException(status_code=400, detail="Invalid camera name format. Expected 'Backend:device_name'")

        # Check if camera is initialized
        active_cameras = manager.get_active_cameras()
        if request.camera not in active_cameras:
            raise HTTPException(status_code=404, detail=f"Camera '{request.camera}' is not initialized")

        camera_proxy = manager.get_camera(request.camera)
        success = await camera_proxy.set_exposure(request.exposure)

        if success:
            logger.info(f"Set exposure for '{request.camera}' to {request.exposure} μs")
            return BoolResponse(success=True, message=f"Exposure set to {request.exposure} μs")
        else:
            logger.warning(f"Failed to set exposure for '{request.camera}' to {request.exposure} μs")
            raise HTTPException(status_code=422, detail=f"Failed to set exposure to {request.exposure} μs")

    except HTTPException:
        raise
    except CameraError as e:
        logger.error(f"Camera error setting exposure for '{request.camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Camera error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error setting exposure for '{request.camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("/exposure/range", response_model=RangeResponse)
async def get_exposure_range(
    camera: str = Query(..., description="Camera name"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> RangeResponse:
    """
    Get camera exposure range.

    Args:
        camera: Camera name in format 'Backend:device_name'

    Returns:
        RangeResponse: Tuple of (minimum_exposure, maximum_exposure) in microseconds
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)
        exposure_range = await camera_proxy.get_exposure_range()

        logger.info(f"Retrieved exposure range for '{validated_camera}': {exposure_range}")

        return RangeResponse(
            success=True, data=exposure_range, message=f"Exposure range: {exposure_range[0]} - {exposure_range[1]} μs"
        )

    except CameraError as e:
        logger.error(f"Failed to get exposure range for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Failed to get exposure range: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting exposure range for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


# Trigger Mode Control Endpoints
@router.get("/trigger-mode", response_model=StringResponse)
async def get_trigger_mode(
    camera: str = Query(..., description="Camera name"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> StringResponse:
    """
    Get current camera trigger mode.

    Args:
        camera: Camera name in format 'Backend:device_name'

    Returns:
        StringResponse: Current trigger mode ('continuous' or 'trigger')
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)
        trigger_mode = await camera_proxy.get_trigger_mode()

        logger.info(f"Retrieved trigger mode for '{validated_camera}': {trigger_mode}")

        return StringResponse(success=True, data=trigger_mode, message=f"Current trigger mode: {trigger_mode}")

    except CameraError as e:
        logger.error(f"Failed to get trigger mode for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Failed to get trigger mode: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting trigger mode for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.put("/trigger-mode", response_model=BoolResponse)
async def set_trigger_mode(
    request: TriggerModeRequest, manager: CameraManager = Depends(get_camera_manager)
) -> BoolResponse:
    """
    Set camera trigger mode.

    Args:
        request: Trigger mode setting request

    Returns:
        BoolResponse: Success status of trigger mode setting
    """
    try:
        # Validate camera exists and trigger mode value
        if ":" not in request.camera:
            raise HTTPException(status_code=400, detail="Invalid camera name format. Expected 'Backend:device_name'")

        if request.mode not in ["continuous", "trigger"]:
            raise HTTPException(status_code=400, detail="Invalid trigger mode. Must be 'continuous' or 'trigger'")

        # Check if camera is initialized
        active_cameras = manager.get_active_cameras()
        if request.camera not in active_cameras:
            raise HTTPException(status_code=404, detail=f"Camera '{request.camera}' is not initialized")

        camera_proxy = manager.get_camera(request.camera)
        success = await camera_proxy.set_trigger_mode(request.mode)

        if success:
            logger.info(f"Set trigger mode for '{request.camera}' to '{request.mode}'")
            return BoolResponse(success=True, message=f"Trigger mode set to '{request.mode}'")
        else:
            logger.warning(f"Failed to set trigger mode for '{request.camera}' to '{request.mode}'")
            raise HTTPException(status_code=422, detail=f"Failed to set trigger mode to '{request.mode}'")

    except HTTPException:
        raise
    except CameraError as e:
        logger.error(f"Camera error setting trigger mode for '{request.camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Camera error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error setting trigger mode for '{request.camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


# White Balance Control Endpoints
@router.get("/white-balance", response_model=StringResponse)
async def get_white_balance(
    camera: str = Query(..., description="Camera name"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> StringResponse:
    """
    Get current white balance mode.

    Args:
        camera: Camera name in format 'Backend:device_name'

    Returns:
        StringResponse: Current white balance mode
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)
        white_balance = await camera_proxy.get_white_balance()

        logger.info(f"Retrieved white balance for '{validated_camera}': {white_balance}")

        return StringResponse(success=True, data=white_balance, message=f"Current white balance: {white_balance}")

    except CameraError as e:
        logger.error(f"Failed to get white balance for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Failed to get white balance: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting white balance for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.put("/white-balance", response_model=BoolResponse)
async def set_white_balance(
    request: WhiteBalanceRequest, manager: CameraManager = Depends(get_camera_manager)
) -> BoolResponse:
    """
    Set white balance mode.

    Args:
        request: White balance setting request

    Returns:
        BoolResponse: Success status of white balance setting
    """
    try:
        # Validate camera exists
        if ":" not in request.camera:
            raise HTTPException(status_code=400, detail="Invalid camera name format. Expected 'Backend:device_name'")

        # Check if camera is initialized
        active_cameras = manager.get_active_cameras()
        if request.camera not in active_cameras:
            raise HTTPException(status_code=404, detail=f"Camera '{request.camera}' is not initialized")

        camera_proxy = manager.get_camera(request.camera)
        success = await camera_proxy.set_white_balance(request.mode)

        if success:
            logger.info(f"Set white balance for '{request.camera}' to '{request.mode}'")
            return BoolResponse(success=True, message=f"White balance set to '{request.mode}'")
        else:
            logger.warning(f"Failed to set white balance for '{request.camera}' to '{request.mode}'")
            raise HTTPException(status_code=422, detail=f"Failed to set white balance to '{request.mode}'")

    except HTTPException:
        raise
    except CameraError as e:
        logger.error(f"Camera error setting white balance for '{request.camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Camera error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error setting white balance for '{request.camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("/white-balance/modes", response_model=WhiteBalanceListResponse)
async def get_white_balance_modes(
    camera: str = Query(..., description="Camera name"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> WhiteBalanceListResponse:
    """
    Get available white balance modes.

    Args:
        camera: Camera name in format 'Backend:device_name'

    Returns:
        WhiteBalanceListResponse: List of supported white balance modes
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)
        wb_modes = camera_proxy.get_available_white_balance_modes()

        logger.info(f"Retrieved white balance modes for '{validated_camera}': {wb_modes}")

        return WhiteBalanceListResponse(
            success=True, data=wb_modes, message=f"Found {len(wb_modes)} available white balance modes"
        )

    except CameraError as e:
        logger.error(f"Failed to get white balance modes for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Failed to get white balance modes: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting white balance modes for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.post("/batch", response_model=BatchOperationResponse)
async def configure_batch_async(
    request: BatchCameraConfigRequest, manager: CameraManager = Depends(get_camera_manager)
) -> BatchOperationResponse:
    """
    Configure multiple cameras with async settings (exposure, trigger mode, white balance).

    This endpoint allows batch configuration of async camera settings across multiple cameras.
    Only supports async configuration parameters: exposure, trigger_mode, white_balance.

    **Supported Parameters:**
    - exposure: Exposure time in microseconds
    - trigger_mode: Trigger mode ('continuous' or 'trigger')
    - white_balance: White balance mode ('auto', 'once', 'off')

    Args:
        request: Batch configuration request with camera names and settings
        manager: Camera manager instance

    Returns:
        BatchOperationResponse: Results of batch configuration operation

    Raises:
        422: If configuration fails for any camera
        500: If unexpected error occurs
    """
    try:
        logger.info(f"Starting batch async configuration for {len(request.configurations)} cameras")

        # Validate that all cameras exist and are initialized
        for camera_name in request.configurations.keys():
            if ":" not in camera_name:
                raise ValueError(f"Invalid camera name format '{camera_name}'. Expected 'Backend:device_name'")

        # Filter configurations to only include async parameters
        async_configs = {}
        for camera_name, settings in request.configurations.items():
            async_settings = {}
            for param, value in settings.items():
                if param in ["exposure", "trigger_mode", "white_balance"]:
                    async_settings[param] = value
                else:
                    logger.warning(f"Ignoring non-async parameter '{param}' for camera '{camera_name}'")

            if async_settings:
                async_configs[camera_name] = async_settings

        if not async_configs:
            return BatchOperationResponse(
                success=True,
                results={},
                successful_count=0,
                failed_count=0,
                message="No async configuration parameters provided",
            )

        # Perform batch configuration
        results = await manager.batch_configure(async_configs)

        successful_count = sum(1 for success in results.values() if success)
        failed_count = len(results) - successful_count

        logger.info(f"Batch async configuration completed: {successful_count} successful, {failed_count} failed")

        return BatchOperationResponse(
            success=failed_count == 0,
            results=results,
            successful_count=successful_count,
            failed_count=failed_count,
            message=f"Batch async configuration completed: {successful_count} successful, {failed_count} failed",
        )

    except ValueError:
        # Re-raise ValueError to let app.py handlers convert to 400
        raise
    except Exception as e:
        logger.error(f"Batch async configuration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch async configuration error: {str(e)}")
