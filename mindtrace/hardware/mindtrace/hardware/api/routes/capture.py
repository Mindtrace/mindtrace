"""
Image capture routes for Camera API.

This module provides endpoints for image capture operations:
- Single image capture
- Batch image capture  
- HDR image capture
"""

import logging
import base64
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from mindtrace.hardware.mindtrace.hardware.cameras.camera_manager import CameraManager
from mindtrace.hardware.mindtrace.hardware.api.dependencies import (
    get_camera_manager,
    validate_camera_exists
)
from mindtrace.hardware.mindtrace.hardware.models.requests import (
    CaptureRequest,
    BatchCaptureRequest,
    HDRCaptureRequest,
    BatchHDRCaptureRequest
)
from mindtrace.hardware.mindtrace.hardware.models.responses import (
    CaptureResponse,
    HDRCaptureResponse,
    BatchOperationResponse
)
from mindtrace.hardware.mindtrace.hardware.core.exceptions import CameraError


logger = logging.getLogger(__name__)

router = APIRouter()


def _encode_image_to_base64(image_array) -> Optional[str]:
    """
    Convert image array to base64 string.
    
    Args:
        image_array: Numpy array or image data
        
    Returns:
        Optional[str]: Base64 encoded image or None if conversion fails
    """
    try:
        import cv2
        import numpy as np
        
        if image_array is None:
            return None
        
        # Ensure image is in the right format
        if isinstance(image_array, np.ndarray):
            # Convert to BGR if needed and encode as JPEG
            if len(image_array.shape) == 3 and image_array.shape[2] == 3:
                # Assume RGB, convert to BGR for OpenCV
                image_bgr = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)
            else:
                image_bgr = image_array
            
            # Encode as JPEG
            success, buffer = cv2.imencode('.jpg', image_bgr)
            if success:
                # Convert to base64
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
                return jpg_as_text
        
        return None
        
    except Exception as e:
        logger.warning(f"Failed to encode image to base64: {e}")
        return None


@router.post("/", response_model=CaptureResponse)
async def capture_image(
    request: CaptureRequest,
    manager: CameraManager = Depends(get_camera_manager)
) -> CaptureResponse:
    """
    Capture a single image from the specified camera.
    
    Args:
        request: Capture request with camera name and optional save path
        
    Returns:
        CaptureResponse: Capture result with optional image data
        
    Raises:
        HTTPException: If capture fails or camera is not available
    """
    try:
        # Validate camera exists
        if ":" not in request.camera:
            raise HTTPException(
                status_code=400,
                detail="Invalid camera name format. Expected 'Backend:device_name'"
            )
        
        # Check if camera is initialized
        active_cameras = manager.get_active_cameras()
        if request.camera not in active_cameras:
            raise HTTPException(
                status_code=404,
                detail=f"Camera '{request.camera}' is not initialized. Use POST /api/v1/cameras/initialize first."
            )
        
        # Get camera proxy and capture image
        camera_proxy = manager.get_camera(request.camera)
        
        # Capture image - this returns success status and image data
        capture_result = await camera_proxy.capture(save_path=request.save_path)
        
        # Handle different return formats from capture method
        if isinstance(capture_result, tuple):
            success, image_data = capture_result
        else:
            # Some implementations might return just the image
            success = True
            image_data = capture_result
        
        if not success:
            raise HTTPException(
                status_code=422,
                detail=f"Failed to capture image from camera '{request.camera}'"
            )
        
        # Encode image to base64 for transmission
        image_base64 = _encode_image_to_base64(image_data)
        
        logger.info(
            f"Successfully captured image from '{request.camera}'"
            + (f" and saved to '{request.save_path}'" if request.save_path else "")
        )
        
        return CaptureResponse(
            success=True,
            message=f"Image captured successfully from '{request.camera}'"
                   + (f" and saved to '{request.save_path}'" if request.save_path else ""),
            image_data=image_base64,
            save_path=request.save_path,
            media_type="image/jpeg"
        )
    
    except HTTPException:
        raise
    except CameraError as e:
        logger.error(f"Camera error during capture from '{request.camera}': {e}")
        raise HTTPException(
            status_code=422,
            detail=f"Camera capture error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during capture from '{request.camera}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected capture error: {str(e)}"
        )


@router.post("/batch", response_model=BatchOperationResponse)
async def capture_batch(
    request: BatchCaptureRequest,
    manager: CameraManager = Depends(get_camera_manager)
) -> BatchOperationResponse:
    """
    Capture images from multiple cameras simultaneously.
    
    Uses network bandwidth management to prevent saturation when capturing
    from multiple cameras, especially important for GigE cameras.
    
    Args:
        request: Batch capture request with list of camera names
        
    Returns:
        BatchOperationResponse: Results of batch capture operation
    """
    try:
        # Validate camera names
        for camera in request.cameras:
            if ":" not in camera:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid camera name format '{camera}'. Expected 'Backend:device_name'"
                )
        
        # Check if all cameras are initialized
        active_cameras = manager.get_active_cameras()
        uninitialized_cameras = [cam for cam in request.cameras if cam not in active_cameras]
        
        if uninitialized_cameras:
            raise HTTPException(
                status_code=404,
                detail=f"Cameras not initialized: {', '.join(uninitialized_cameras)}"
            )
        
        # Perform batch capture with bandwidth management
        capture_results = await manager.batch_capture(request.cameras)
        
        # Process results
        results = {}
        successful_count = 0
        failed_count = 0
        
        for camera_name, image_data in capture_results.items():
            if image_data is not None:
                results[camera_name] = True
                successful_count += 1
            else:
                results[camera_name] = False
                failed_count += 1
        
        logger.info(
            f"Batch capture completed: {successful_count} successful, {failed_count} failed"
        )
        
        return BatchOperationResponse(
            success=failed_count == 0,
            results=results,
            successful_count=successful_count,
            failed_count=failed_count,
            message=f"Batch capture completed: {successful_count} successful, {failed_count} failed"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch capture failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Batch capture error: {str(e)}"
        )


@router.post("/hdr", response_model=HDRCaptureResponse)
async def capture_hdr(
    request: HDRCaptureRequest,
    manager: CameraManager = Depends(get_camera_manager)
) -> HDRCaptureResponse:
    """
    Capture HDR (High Dynamic Range) images with multiple exposure levels.
    
    This endpoint captures multiple images at different exposure levels to create
    HDR imagery. It temporarily modifies the camera's exposure settings and
    restores the original exposure when complete.
    
    Args:
        request: HDR capture request with exposure settings
        
    Returns:
        HDRCaptureResponse: HDR capture results with images and exposure levels
    """
    try:
        # Validate camera exists
        if ":" not in request.camera:
            raise HTTPException(
                status_code=400,
                detail="Invalid camera name format. Expected 'Backend:device_name'"
            )
        
        # Check if camera is initialized
        active_cameras = manager.get_active_cameras()
        if request.camera not in active_cameras:
            raise HTTPException(
                status_code=404,
                detail=f"Camera '{request.camera}' is not initialized"
            )
        
        # Get camera proxy and perform HDR capture
        camera_proxy = manager.get_camera(request.camera)
        
        hdr_result = await camera_proxy.capture_hdr(
            save_path_pattern=request.save_path_pattern,
            exposure_levels=request.exposure_levels,
            exposure_multiplier=request.exposure_multiplier,
            return_images=request.return_images
        )
        
        # Process HDR results
        if request.return_images and isinstance(hdr_result, list):
            # Encode images to base64
            encoded_images = []
            for image in hdr_result:
                encoded_image = _encode_image_to_base64(image)
                if encoded_image:
                    encoded_images.append(encoded_image)
            
            successful_captures = len(encoded_images)
            
            logger.info(
                f"HDR capture completed for '{request.camera}': {successful_captures} images"
            )
            
            return HDRCaptureResponse(
                success=successful_captures > 0,
                message=f"HDR capture completed: {successful_captures} images captured",
                images=encoded_images,
                successful_captures=successful_captures
            )
        
        elif isinstance(hdr_result, bool):
            # Simple success/failure result
            successful_captures = request.exposure_levels if hdr_result else 0
            
            logger.info(
                f"HDR capture {'succeeded' if hdr_result else 'failed'} for '{request.camera}'"
            )
            
            return HDRCaptureResponse(
                success=hdr_result,
                message=f"HDR capture {'completed successfully' if hdr_result else 'failed'}",
                successful_captures=successful_captures
            )
        
        else:
            # Unexpected result format
            raise HTTPException(
                status_code=500,
                detail="Unexpected HDR capture result format"
            )
    
    except HTTPException:
        raise
    except CameraError as e:
        logger.error(f"Camera error during HDR capture from '{request.camera}': {e}")
        raise HTTPException(
            status_code=422,
            detail=f"HDR capture error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during HDR capture from '{request.camera}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected HDR capture error: {str(e)}"
        )


@router.post("/hdr/batch", response_model=Dict[str, HDRCaptureResponse])
async def capture_hdr_batch(
    request: BatchHDRCaptureRequest,
    manager: CameraManager = Depends(get_camera_manager)
) -> Dict[str, HDRCaptureResponse]:
    """
    Capture HDR images from multiple cameras simultaneously.
    
    Args:
        request: Batch HDR capture request
        
    Returns:
        Dict[str, HDRCaptureResponse]: Mapping of camera names to HDR capture results
    """
    try:
        # Validate camera names
        for camera in request.cameras:
            if ":" not in camera:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid camera name format '{camera}'. Expected 'Backend:device_name'"
                )
        
        # Check if all cameras are initialized
        active_cameras = manager.get_active_cameras()
        uninitialized_cameras = [cam for cam in request.cameras if cam not in active_cameras]
        
        if uninitialized_cameras:
            raise HTTPException(
                status_code=404,
                detail=f"Cameras not initialized: {', '.join(uninitialized_cameras)}"
            )
        
        # Perform batch HDR capture
        hdr_results = await manager.batch_capture_hdr(
            request.cameras,
            save_path_pattern=request.save_path_pattern,
            exposure_levels=request.exposure_levels,
            exposure_multiplier=request.exposure_multiplier,
            return_images=request.return_images
        )
        
        # Process results into response format
        response_results = {}
        
        for camera_name, hdr_result in hdr_results.items():
            if request.return_images and isinstance(hdr_result, list):
                # Encode images to base64
                encoded_images = []
                for image in hdr_result:
                    encoded_image = _encode_image_to_base64(image)
                    if encoded_image:
                        encoded_images.append(encoded_image)
                
                successful_captures = len(encoded_images)
                
                response_results[camera_name] = HDRCaptureResponse(
                    success=successful_captures > 0,
                    message=f"HDR capture completed: {successful_captures} images",
                    images=encoded_images,
                    successful_captures=successful_captures
                )
            
            elif isinstance(hdr_result, bool):
                successful_captures = request.exposure_levels if hdr_result else 0
                
                response_results[camera_name] = HDRCaptureResponse(
                    success=hdr_result,
                    message=f"HDR capture {'completed' if hdr_result else 'failed'}",
                    successful_captures=successful_captures
                )
            
            else:
                # Handle failures
                response_results[camera_name] = HDRCaptureResponse(
                    success=False,
                    message="HDR capture failed",
                    successful_captures=0
                )
        
        successful_cameras = sum(1 for result in response_results.values() if result.success)
        failed_cameras = len(response_results) - successful_cameras
        
        logger.info(
            f"Batch HDR capture completed: {successful_cameras} successful, {failed_cameras} failed"
        )
        
        return response_results
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch HDR capture failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Batch HDR capture error: {str(e)}"
        ) 