"""
Sync configuration routes for Camera API.

This module provides endpoints for camera settings that are synchronous operations:
- Gain control
- ROI (Region of Interest)
- Pixel format
- Image enhancement
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from mindtrace.hardware.api.dependencies import get_camera_manager, validate_camera_exists
from mindtrace.hardware.cameras.camera_manager import CameraManager
from mindtrace.hardware.core.exceptions import CameraError
from mindtrace.hardware.models.requests import (
    BatchCameraConfigRequest,
    GainRequest,
    ImageEnhancementRequest,
    PixelFormatRequest,
    ROIRequest,
)
from mindtrace.hardware.models.responses import (
    BatchOperationResponse,
    BoolResponse,
    DictResponse,
    FloatResponse,
    PixelFormatListResponse,
    RangeResponse,
    StringResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# Gain Control Endpoints
@router.get("/gain", response_model=FloatResponse)
async def get_gain(
    camera: str = Query(..., description="Camera name"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> FloatResponse:
    """
    Get current camera gain value.

    Args:
        camera: Camera name in format 'Backend:device_name'

    Returns:
        FloatResponse: Current gain value
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)
        gain = camera_proxy.get_gain()

        logger.info(f"Retrieved gain for '{validated_camera}': {gain}")

        return FloatResponse(success=True, data=gain, message=f"Current gain: {gain}")

    except CameraError as e:
        logger.error(f"Failed to get gain for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Failed to get gain: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting gain for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.put("/gain", response_model=BoolResponse)
async def set_gain(request: GainRequest, manager: CameraManager = Depends(get_camera_manager)) -> BoolResponse:
    """
    Set camera gain value.

    Args:
        request: Gain setting request

    Returns:
        BoolResponse: Success status of gain setting
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
        success = camera_proxy.set_gain(request.gain)

        if success:
            logger.info(f"Set gain for '{request.camera}' to {request.gain}")
            return BoolResponse(success=True, message=f"Gain set to {request.gain}")
        else:
            logger.warning(f"Failed to set gain for '{request.camera}' to {request.gain}")
            raise HTTPException(status_code=422, detail=f"Failed to set gain to {request.gain}")

    except HTTPException:
        raise
    except CameraError as e:
        logger.error(f"Camera error setting gain for '{request.camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Camera error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error setting gain for '{request.camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("/gain/range", response_model=RangeResponse)
async def get_gain_range(
    camera: str = Query(..., description="Camera name"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> RangeResponse:
    """
    Get camera gain range.

    Args:
        camera: Camera name in format 'Backend:device_name'

    Returns:
        RangeResponse: Tuple of (minimum_gain, maximum_gain)
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)
        gain_range = camera_proxy.get_gain_range()

        logger.info(f"Retrieved gain range for '{validated_camera}': {gain_range}")

        return RangeResponse(success=True, data=gain_range, message=f"Gain range: {gain_range[0]} - {gain_range[1]}")

    except CameraError as e:
        logger.error(f"Failed to get gain range for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Failed to get gain range: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting gain range for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


# ROI Control Endpoints
@router.get("/roi", response_model=DictResponse)
async def get_roi(
    camera: str = Query(..., description="Camera name"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> DictResponse:
    """
    Get current Region of Interest (ROI) settings.

    Args:
        camera: Camera name in format 'Backend:device_name'

    Returns:
        DictResponse: Dictionary with keys: 'x', 'y', 'width', 'height'
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)
        roi = camera_proxy.get_roi()

        logger.info(f"Retrieved ROI for '{validated_camera}': {roi}")

        return DictResponse(success=True, data=roi, message=f"Current ROI: {roi}")

    except CameraError as e:
        logger.error(f"Failed to get ROI for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Failed to get ROI: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting ROI for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.put("/roi", response_model=BoolResponse)
async def set_roi(request: ROIRequest, manager: CameraManager = Depends(get_camera_manager)) -> BoolResponse:
    """
    Set camera Region of Interest (ROI).

    Args:
        request: ROI setting request with x, y, width, height

    Returns:
        BoolResponse: Success status of ROI setting
    """
    try:
        # Validate camera exists
        if ":" not in request.camera:
            raise HTTPException(status_code=400, detail="Invalid camera name format. Expected 'Backend:device_name'")

        # Validate ROI parameters
        if request.width <= 0 or request.height <= 0:
            raise HTTPException(status_code=400, detail="ROI width and height must be positive")

        if request.x < 0 or request.y < 0:
            raise HTTPException(status_code=400, detail="ROI x and y coordinates must be non-negative")

        # Check if camera is initialized
        active_cameras = manager.get_active_cameras()
        if request.camera not in active_cameras:
            raise HTTPException(status_code=404, detail=f"Camera '{request.camera}' is not initialized")

        camera_proxy = manager.get_camera(request.camera)
        success = camera_proxy.set_roi(request.x, request.y, request.width, request.height)

        if success:
            logger.info(
                f"Set ROI for '{request.camera}' to ({request.x}, {request.y}, {request.width}, {request.height})"
            )
            return BoolResponse(
                success=True, message=f"ROI set to ({request.x}, {request.y}, {request.width}, {request.height})"
            )
        else:
            logger.warning(f"Failed to set ROI for '{request.camera}'")
            raise HTTPException(status_code=422, detail="Failed to set ROI")

    except HTTPException:
        raise
    except CameraError as e:
        logger.error(f"Camera error setting ROI for '{request.camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Camera error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error setting ROI for '{request.camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.delete("/roi", response_model=BoolResponse)
async def reset_roi(
    camera: str = Query(..., description="Camera name"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> BoolResponse:
    """
    Reset ROI to full sensor size.

    Args:
        camera: Camera name in format 'Backend:device_name'

    Returns:
        BoolResponse: Success status of ROI reset
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)
        success = camera_proxy.reset_roi()

        if success:
            logger.info(f"Reset ROI for '{validated_camera}' to full sensor")
            return BoolResponse(success=True, message="ROI reset to full sensor size")
        else:
            logger.warning(f"Failed to reset ROI for '{validated_camera}'")
            raise HTTPException(status_code=422, detail="Failed to reset ROI")

    except CameraError as e:
        logger.error(f"Failed to reset ROI for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Failed to reset ROI: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error resetting ROI for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


# Pixel Format Control Endpoints
@router.get("/pixel-format", response_model=StringResponse)
async def get_pixel_format(
    camera: str = Query(..., description="Camera name"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> StringResponse:
    """
    Get current pixel format.

    Args:
        camera: Camera name in format 'Backend:device_name'

    Returns:
        StringResponse: Current pixel format string
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)
        pixel_format = camera_proxy.get_pixel_format()

        logger.info(f"Retrieved pixel format for '{validated_camera}': {pixel_format}")

        return StringResponse(success=True, data=pixel_format, message=f"Current pixel format: {pixel_format}")

    except CameraError as e:
        logger.error(f"Failed to get pixel format for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Failed to get pixel format: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting pixel format for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.put("/pixel-format", response_model=BoolResponse)
async def set_pixel_format(
    request: PixelFormatRequest, manager: CameraManager = Depends(get_camera_manager)
) -> BoolResponse:
    """
    Set camera pixel format.

    Args:
        request: Pixel format setting request

    Returns:
        BoolResponse: Success status of pixel format setting
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
        success = camera_proxy.set_pixel_format(request.format)

        if success:
            logger.info(f"Set pixel format for '{request.camera}' to '{request.format}'")
            return BoolResponse(success=True, message=f"Pixel format set to '{request.format}'")
        else:
            logger.warning(f"Failed to set pixel format for '{request.camera}' to '{request.format}'")
            raise HTTPException(status_code=422, detail=f"Failed to set pixel format to '{request.format}'")

    except HTTPException:
        raise
    except CameraError as e:
        logger.error(f"Camera error setting pixel format for '{request.camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Camera error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error setting pixel format for '{request.camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("/pixel-format/options", response_model=PixelFormatListResponse)
async def get_pixel_format_options(
    camera: str = Query(..., description="Camera name"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> PixelFormatListResponse:
    """
    Get available pixel formats.

    Args:
        camera: Camera name in format 'Backend:device_name'

    Returns:
        PixelFormatListResponse: List of supported pixel format strings
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)
        pixel_formats = camera_proxy.get_available_pixel_formats()

        logger.info(f"Retrieved pixel formats for '{validated_camera}': {pixel_formats}")

        return PixelFormatListResponse(
            success=True, data=pixel_formats, message=f"Found {len(pixel_formats)} available pixel formats"
        )

    except CameraError as e:
        logger.error(f"Failed to get pixel formats for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Failed to get pixel formats: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting pixel formats for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


# Image Enhancement Control Endpoints
@router.get("/image-enhancement", response_model=BoolResponse)
async def get_image_enhancement(
    camera: str = Query(..., description="Camera name"),
    manager: CameraManager = Depends(get_camera_manager),
    validated_camera: str = Depends(validate_camera_exists),
) -> BoolResponse:
    """
    Get current image enhancement status.

    Args:
        camera: Camera name in format 'Backend:device_name'

    Returns:
        BoolResponse: Current image enhancement status (enabled/disabled)
    """
    try:
        camera_proxy = manager.get_camera(validated_camera)
        enhancement_enabled = camera_proxy.get_image_enhancement()

        logger.info(f"Retrieved image enhancement for '{validated_camera}': {enhancement_enabled}")

        return BoolResponse(
            success=enhancement_enabled,
            message=f"Image enhancement is {'enabled' if enhancement_enabled else 'disabled'}",
        )

    except CameraError as e:
        logger.error(f"Failed to get image enhancement for '{validated_camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Failed to get image enhancement: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting image enhancement for '{validated_camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.put("/image-enhancement", response_model=BoolResponse)
async def set_image_enhancement(
    request: ImageEnhancementRequest, manager: CameraManager = Depends(get_camera_manager)
) -> BoolResponse:
    """
    Enable or disable image quality enhancement.

    Image enhancement may include gamma correction, contrast adjustment,
    and color correction depending on the camera backend.

    Args:
        request: Image enhancement setting request

    Returns:
        BoolResponse: Success status of image enhancement setting
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
        success = camera_proxy.set_image_enhancement(request.enabled)

        if success:
            status = "enabled" if request.enabled else "disabled"
            logger.info(f"Set image enhancement for '{request.camera}' to {status}")
            return BoolResponse(success=True, message=f"Image enhancement {status}")
        else:
            logger.warning(f"Failed to set image enhancement for '{request.camera}'")
            raise HTTPException(status_code=422, detail="Failed to set image enhancement")

    except HTTPException:
        raise
    except CameraError as e:
        logger.error(f"Camera error setting image enhancement for '{request.camera}': {e}")
        raise HTTPException(status_code=422, detail=f"Camera error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error setting image enhancement for '{request.camera}': {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.post("/batch", response_model=BatchOperationResponse)
async def configure_batch_sync(
    request: BatchCameraConfigRequest, manager: CameraManager = Depends(get_camera_manager)
) -> BatchOperationResponse:
    """
    Configure multiple cameras with sync settings (gain, ROI, pixel format, image enhancement).

    This endpoint allows batch configuration of sync camera settings across multiple cameras.
    Only supports sync configuration parameters: gain, roi, pixel_format, image_enhancement.

    **Supported Parameters:**
    - gain: Gain value (numeric)
    - roi: ROI as tuple (x, y, width, height)
    - pixel_format: Pixel format string (e.g., 'BGR8', 'Mono8', 'RGB8')
    - image_enhancement: Boolean for image enhancement

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
        logger.info(f"Starting batch sync configuration for {len(request.configurations)} cameras")

        # Validate that all cameras exist and are initialized
        for camera_name in request.configurations.keys():
            if ":" not in camera_name:
                raise ValueError(f"Invalid camera name format '{camera_name}'. Expected 'Backend:device_name'")

        # Filter configurations to only include sync parameters
        sync_configs = {}
        for camera_name, settings in request.configurations.items():
            sync_settings = {}
            for param, value in settings.items():
                if param in ["gain", "roi", "pixel_format", "image_enhancement"]:
                    sync_settings[param] = value
                else:
                    logger.warning(f"Ignoring non-sync parameter '{param}' for camera '{camera_name}'")

            if sync_settings:
                sync_configs[camera_name] = sync_settings

        if not sync_configs:
            return BatchOperationResponse(
                success=True,
                results={},
                successful_count=0,
                failed_count=0,
                message="No sync configuration parameters provided",
            )

        # Perform batch configuration
        results = await manager.batch_configure(sync_configs)

        successful_count = sum(1 for success in results.values() if success)
        failed_count = len(results) - successful_count

        logger.info(f"Batch sync configuration completed: {successful_count} successful, {failed_count} failed")

        return BatchOperationResponse(
            success=failed_count == 0,
            results=results,
            successful_count=successful_count,
            failed_count=failed_count,
            message=f"Batch sync configuration completed: {successful_count} successful, {failed_count} failed",
        )

    except ValueError:
        # Re-raise ValueError to let app.py handlers convert to 400
        raise
    except Exception as e:
        logger.error(f"Batch sync configuration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch sync configuration error: {str(e)}")
