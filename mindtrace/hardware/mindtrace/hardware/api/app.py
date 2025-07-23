"""
Camera API Service using Mindtrace Service base class.

This module provides a comprehensive REST API for camera management and control,
including camera discovery, initialization, configuration, capture operations,
and network management. The service supports multiple camera backends (OpenCV,
Basler, Daheng, and mock backends) with unified async interfaces.
"""

import logging
import base64
from datetime import datetime, UTC
from typing import Dict, Any, List, Optional, Tuple

from fastapi import Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse
import cv2
import asyncio
from pydantic import BaseModel

from mindtrace.services.core.service import Service
from mindtrace.core import TaskSchema
from mindtrace.hardware.core.exceptions import (
    CameraError,
    CameraNotFoundError,
    CameraInitializationError,
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    SDKNotAvailableError,
    CameraTimeoutError,
)
from mindtrace.hardware.models.responses import ErrorResponse
from mindtrace.hardware.api.dependencies import get_camera_manager
from mindtrace.hardware.models.requests import *
from mindtrace.hardware.models.responses import *

logger = logging.getLogger(__name__)

EXCEPTION_MAPPING = {
    CameraNotFoundError: (404, "CAMERA_NOT_FOUND"),
    CameraInitializationError: (409, "CAMERA_INITIALIZATION_ERROR"),
    CameraCaptureError: (422, "CAMERA_CAPTURE_ERROR"),
    CameraConfigurationError: (422, "CAMERA_CONFIGURATION_ERROR"),
    CameraConnectionError: (503, "CAMERA_CONNECTION_ERROR"),
    SDKNotAvailableError: (503, "SDK_NOT_AVAILABLE"),
    CameraTimeoutError: (408, "CAMERA_TIMEOUT"),
    CameraError: (500, "CAMERA_ERROR"),
}

def camera_error_handler(request: Request, exc: CameraError):
    """Handle camera-specific exceptions and return appropriate HTTP responses."""
    status_code, error_code = EXCEPTION_MAPPING.get(type(exc), (500, "UNKNOWN_CAMERA_ERROR"))
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            success=False,
            message=str(exc),
            error_type=type(exc).__name__,
            error_code=error_code,
            timestamp=datetime.now(UTC)
        ).model_dump(mode="json")
    )

def value_error_handler(request: Request, exc: ValueError):
    """Handle ValueError exceptions and return appropriate HTTP responses."""
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            success=False,
            message=str(exc),
            error_type="ValueError",
            error_code="VALIDATION_ERROR",
            timestamp=datetime.now(UTC)
        ).model_dump(mode="json")
    )

def key_error_handler(request: Request, exc: KeyError):
    """Handle KeyError exceptions and return appropriate HTTP responses."""
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(
            success=False,
            message=f"Resource not found: {exc}",
            error_type="KeyError",
            error_code="RESOURCE_NOT_FOUND",
            timestamp=datetime.now(UTC)
        ).model_dump(mode="json")
    )

def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions and return appropriate HTTP responses."""
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            success=False,
            message="An unexpected error occurred",
            error_type=type(exc).__name__,
            error_code="INTERNAL_SERVER_ERROR",
            timestamp=datetime.now(UTC)
        ).model_dump(mode="json")
    )

async def log_requests(request: Request, call_next):
    """Middleware to log request processing time and status."""
    start_time = datetime.now(UTC)
    response = await call_next(request)
    process_time = (datetime.now(UTC) - start_time).total_seconds()
    logger.info(f"{request.method} {request.url} - {response.status_code} - {process_time:.4f}s")
    return response

def _encode_image_to_base64(image_array) -> Optional[str]:
    """Convert image array to base64 string.
    
    Args:
        image_array: numpy array representing the image
        
    Returns:
        Base64 encoded string of the image in JPEG format, or None if conversion fails
    """
    try:
        import cv2
        import numpy as np
        
        if image_array is None:
            return None
        
        if isinstance(image_array, np.ndarray):
            if len(image_array.shape) == 3 and image_array.shape[2] == 3:
                image_bgr = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)
            else:
                image_bgr = image_array
            
            success, buffer = cv2.imencode('.jpg', image_bgr)
            if success:
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
                return jpg_as_text
        
        return None
        
    except Exception as e:
        logger.warning(f"Failed to encode image to base64: {e}")
        return None

# Camera Management Endpoints
async def discover_cameras(backend: str = None) -> ListResponse:
    """Discover available cameras across all backends or a specific backend.
    
    Args:
        backend: Optional backend name to filter cameras
        
    Returns:
        ListResponse containing discovered camera names
    """
    manager = get_camera_manager()
    cameras = manager.discover_cameras(backends=backend if backend else None)
    return ListResponse(success=True, data=cameras, message=f"Found {len(cameras)} cameras")

async def list_active_cameras() -> ListResponse:
    """List all currently initialized cameras.
    
    Returns:
        ListResponse containing active camera names
    """
    manager = get_camera_manager()
    active_cameras = manager.get_active_cameras()
    return ListResponse(success=True, data=active_cameras, message=f"Found {len(active_cameras)} active cameras")

async def initialize_camera(camera: str, payload: CameraInitializeRequest = None) -> BoolResponse:
    """Initialize a single camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        payload: Optional initialization parameters
        
    Returns:
        BoolResponse indicating success/failure
        
    Raises:
        ValueError: If camera name format is invalid
    """
    manager = get_camera_manager()
    if ":" not in camera:
        raise ValueError("Invalid camera name format. Expected 'Backend:device_name'")
    active_cameras = manager.get_active_cameras()
    if camera in active_cameras:
        return BoolResponse(success=True, message=f"Camera '{camera}' already initialized")
    test_connection = payload.test_connection if payload else True
    await manager.initialize_camera(camera, test_connection=test_connection)
    return BoolResponse(success=True, message=f"Camera '{camera}' initialized")

async def initialize_cameras_batch(payload: BatchCameraInitializeRequest) -> BatchOperationResponse:
    """Initialize multiple cameras in batch.
    
    Args:
        payload: Batch initialization request containing camera names and parameters
        
    Returns:
        BatchOperationResponse with results for each camera
        
    Raises:
        ValueError: If any camera name format is invalid
    """
    manager = get_camera_manager()
    for camera in payload.cameras:
        if ":" not in camera:
            raise ValueError(f"Invalid camera name format '{camera}'. Expected 'Backend:device_name'")
    failed_cameras = await manager.initialize_cameras(payload.cameras, test_connections=payload.test_connections)
    successful_count = len(payload.cameras) - len(failed_cameras)
    results = {camera: camera not in failed_cameras for camera in payload.cameras}
    return BatchOperationResponse(
        success=len(failed_cameras) == 0,
        results=results,
        successful_count=successful_count,
        failed_count=len(failed_cameras),
        message=f"Batch initialization: {successful_count} successful, {len(failed_cameras)} failed"
    )

async def close_camera(camera: str) -> BoolResponse:
    """Close a single camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        BoolResponse indicating success/failure
        
    Raises:
        ValueError: If camera name format is invalid
    """
    manager = get_camera_manager()
    if ":" not in camera:
        raise ValueError("Invalid camera name format. Expected 'Backend:device_name'")
    active_cameras = manager.get_active_cameras()
    if camera not in active_cameras:
        return BoolResponse(success=True, message=f"Camera '{camera}' already closed")
    await manager.close_camera(camera)
    return BoolResponse(success=True, message=f"Camera '{camera}' closed")

async def close_all_cameras() -> BoolResponse:
    """Close all active cameras.
    
    Returns:
        BoolResponse indicating success/failure
    """
    manager = get_camera_manager()
    active_cameras = manager.get_active_cameras()
    camera_count = len(active_cameras)
    await manager.close_all_cameras()
    return BoolResponse(success=True, message=f"Successfully closed {camera_count} cameras")

async def check_camera_connection(camera: str) -> StatusResponse:
    """Check if a camera is connected and responsive.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        StatusResponse with connection status and camera information
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    is_connected = await camera_proxy.check_connection()
    status_info = {
        "camera": camera,
        "connected": is_connected,
        "initialized": camera_proxy.is_connected,
        "backend": camera_proxy.backend,
        "device_name": camera_proxy.device_name
    }
    return StatusResponse(
        success=is_connected,
        data=status_info,
        message=f"Camera '{camera}' is {'connected' if is_connected else 'disconnected'}"
    )

async def get_camera_info(camera: str) -> StatusResponse:
    """Get comprehensive information about a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        StatusResponse with detailed camera information including sensor info and current settings
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    sensor_info = await camera_proxy.get_sensor_info()
    info = {
        **sensor_info,
        "camera": camera,
        "backend": camera_proxy.backend,
        "device_name": camera_proxy.device_name,
        "initialized": camera_proxy.is_connected,
    }
    if camera_proxy.is_connected:
        try:
            info["current_exposure"] = await camera_proxy.get_exposure()
            info["current_gain"] = await camera_proxy.get_gain()
            info["current_roi"] = await camera_proxy.get_roi()
            info["current_pixel_format"] = await camera_proxy.get_pixel_format()
        except Exception as e:
            info["settings_error"] = str(e)
    return StatusResponse(
        success=True,
        data=info,
        message=f"Camera information retrieved for '{camera}'"
    )

# Backend Management Endpoints
async def list_backends() -> ListResponse:
    """List all available camera backends.
    
    Returns:
        ListResponse containing backend names
    """
    manager = get_camera_manager()
    backends = manager._discovered_backends
    return ListResponse(success=True, data=backends, message=f"Found {len(backends)} backends")

async def get_backend_info() -> DictResponse:
    """Get detailed information about all backends.
    
    Returns:
        DictResponse with backend information including availability and camera counts
    """
    manager = get_camera_manager()
    backends = manager._discovered_backends
    backend_info = {}
    for backend in backends:
        try:
            cameras = manager.discover_cameras(backends=backend)
            backend_info[backend] = {
                "name": backend,
                "available": True,
                "sdk_available": True,
                "cameras": cameras,
                "camera_count": len(cameras)
            }
        except Exception as e:
            backend_info[backend] = {
                "name": backend,
                "available": False,
                "sdk_available": False,
                "error": str(e),
                "cameras": [],
                "camera_count": 0
            }
    return DictResponse(success=True, data=backend_info, message=f"Backend info for {len(backend_info)} backends")

async def get_specific_backend_info(backend: str) -> DictResponse:
    """Get detailed information about a specific backend.
    
    Args:
        backend: Backend name
        
    Returns:
        DictResponse with backend information
        
    Raises:
        HTTPException: If backend is not found
    """
    manager = get_camera_manager()
    backend_name = backend
    backends = manager._discovered_backends
    if backend_name not in backends:
        raise HTTPException(status_code=404, detail=f"Backend '{backend_name}' not found")
    
    info = {
        "name": backend_name,
        "available": True,
        "sdk_available": True,
        "cameras": []
    }
    
    try:
        cameras = manager.discover_cameras(backends=backend_name)
        info["cameras"] = cameras
        info["camera_count"] = len(cameras)
        
        if backend_name.startswith("Mock"):
            info["type"] = "mock"
            info["description"] = f"Mock backend for testing ({backend_name})"
        else:
            info["type"] = "hardware"
            info["description"] = f"Hardware backend for {backend_name} cameras"
            
    except Exception as e:
        info["cameras"] = []
        info["camera_count"] = 0
        info["error"] = str(e)
    
    return DictResponse(
        success=True,
        data=info,
        message=f"Backend information retrieved for '{backend_name}'"
    )

async def check_backends_health() -> DictResponse:
    """Check the health status of all backends.
    
    Returns:
        DictResponse with health status for each backend
    """
    manager = get_camera_manager()
    backends = manager._discovered_backends
    health_status = {
        "total_backends": len(backends),
        "healthy_backends": 0,
        "unhealthy_backends": 0,
        "backend_status": {}
    }
    
    for backend in backends:
        try:
            cameras = manager.discover_cameras(backends=backend)
            health_status["backend_status"][backend] = {
                "healthy": True,
                "camera_count": len(cameras),
                "message": "Backend is functioning normally"
            }
            health_status["healthy_backends"] += 1
            
        except Exception as e:
            health_status["backend_status"][backend] = {
                "healthy": False,
                "camera_count": 0,
                "error": str(e),
                "message": f"Backend health check failed: {str(e)}"
            }
            health_status["unhealthy_backends"] += 1
    
    overall_healthy = health_status["unhealthy_backends"] == 0
    
    return DictResponse(
        success=overall_healthy,
        data=health_status,
        message=f"Backend health check completed. {health_status['healthy_backends']} healthy, "
               f"{health_status['unhealthy_backends']} unhealthy"
    )

# Capture Endpoints
async def capture_image(camera: str, payload: CaptureRequest = None) -> CaptureResponse:
    """Capture a single image from a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        payload: Optional capture parameters including save path
        
    Returns:
        CaptureResponse with base64 encoded image data
        
    Raises:
        ValueError: If camera name format is invalid
        CameraNotFoundError: If camera is not initialized
        CameraCaptureError: If capture fails
    """
    manager = get_camera_manager()
    if ":" not in camera:
        raise ValueError("Invalid camera name format. Expected 'Backend:device_name'")
    active_cameras = manager.get_active_cameras()
    if camera not in active_cameras:
        raise CameraNotFoundError(f"Camera '{camera}' not initialized")
    camera_proxy = manager.get_camera(camera)
    save_path = payload.save_path if payload else None
    capture_result = await camera_proxy.capture(save_path=save_path)
    success, image_data = capture_result if isinstance(capture_result, tuple) else (True, capture_result)
    if not success:
        raise CameraCaptureError(f"Failed to capture from '{camera}'")
    
    image_base64 = _encode_image_to_base64(image_data)
    
    return CaptureResponse(
        success=True,
        message=f"Image captured from '{camera}'"
               + (f" and saved to '{save_path}'" if save_path else ""),
        image_data=image_base64,
        save_path=save_path,
        media_type="image/jpeg"
    )

async def capture_batch(payload: BatchCaptureRequest) -> BatchOperationResponse:
    """Capture images from multiple cameras in batch.
    
    Args:
        payload: Batch capture request containing camera names
        
    Returns:
        BatchOperationResponse with results for each camera
        
    Raises:
        ValueError: If any camera name format is invalid
        CameraNotFoundError: If any camera is not initialized
    """
    manager = get_camera_manager()
    for camera in payload.cameras:
        if ":" not in camera:
            raise ValueError(f"Invalid camera name format '{camera}'. Expected 'Backend:device_name'")
    active_cameras = manager.get_active_cameras()
    uninitialized = [cam for cam in payload.cameras if cam not in active_cameras]
    if uninitialized:
        raise CameraNotFoundError(f"Cameras not initialized: {', '.join(uninitialized)}")
    capture_results = await manager.batch_capture(payload.cameras)
    results = {camera: data is not None for camera, data in capture_results.items()}
    successful_count = sum(results.values())
    return BatchOperationResponse(
        success=len(payload.cameras) - successful_count == 0,
        results=results,
        successful_count=successful_count,
        failed_count=len(payload.cameras) - successful_count,
        message=f"Batch capture: {successful_count} successful"
    )

async def capture_hdr(camera: str, payload: HDRCaptureRequest = None) -> HDRCaptureResponse:
    """Capture HDR (High Dynamic Range) images from a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        payload: Optional HDR capture parameters
        
    Returns:
        HDRCaptureResponse with multiple images at different exposure levels
        
    Raises:
        ValueError: If camera name format is invalid
        CameraNotFoundError: If camera is not initialized
    """
    manager = get_camera_manager()
    if ":" not in camera:
        raise ValueError("Invalid camera name format. Expected 'Backend:device_name'")
    active_cameras = manager.get_active_cameras()
    if camera not in active_cameras:
        raise CameraNotFoundError(f"Camera '{camera}' not initialized")
    
    # Use defaults if no payload provided
    save_path_pattern = payload.save_path_pattern if payload else None
    exposure_levels = payload.exposure_levels if payload else 3
    exposure_multiplier = payload.exposure_multiplier if payload else 2.0
    return_images = payload.return_images if payload else True
    
    camera_proxy = manager.get_camera(camera)
    hdr_result = await camera_proxy.capture_hdr(
        save_path_pattern=save_path_pattern,
        exposure_levels=exposure_levels,
        exposure_multiplier=exposure_multiplier,
        return_images=return_images
    )
    
    images_base64 = []
    exposure_levels_list = []
    
    if return_images and isinstance(hdr_result, dict) and hdr_result.get("images"):
        for img in hdr_result["images"]:
            img_b64 = _encode_image_to_base64(img)
            if img_b64:
                images_base64.append(img_b64)
        exposure_levels_list = hdr_result.get("exposure_levels", [])
    elif return_images and isinstance(hdr_result, list):
        for img in hdr_result:
            img_b64 = _encode_image_to_base64(img)
            if img_b64:
                images_base64.append(img_b64)
    
    successful_captures = len(images_base64) if return_images else exposure_levels
    
    return HDRCaptureResponse(
        success=True,
        images=images_base64 if images_base64 else None,
        exposure_levels=exposure_levels_list if exposure_levels_list else None,
        successful_captures=successful_captures,
        message=f"HDR capture completed for '{camera}'"
    )

async def capture_hdr_batch(payload: BatchHDRCaptureRequest) -> BatchHDRCaptureResponse:
    """Capture HDR images from multiple cameras in batch.
    
    Args:
        payload: Batch HDR capture request containing camera names and parameters
        
    Returns:
        BatchHDRCaptureResponse with results for each camera
        
    Raises:
        ValueError: If any camera name format is invalid
        CameraNotFoundError: If any camera is not initialized
    """
    manager = get_camera_manager()
    for camera in payload.cameras:
        if ":" not in camera:
            raise ValueError(f"Invalid camera name format '{camera}'. Expected 'Backend:device_name'")
    
    active_cameras = manager.get_active_cameras()
    uninitialized = [cam for cam in payload.cameras if cam not in active_cameras]
    if uninitialized:
        raise CameraNotFoundError(f"Cameras not initialized: {', '.join(uninitialized)}")
    
    hdr_results = await manager.batch_capture_hdr(
        payload.cameras,
        save_path_pattern=payload.save_path_pattern,
        exposure_levels=payload.exposure_levels,
        exposure_multiplier=payload.exposure_multiplier,
        return_images=payload.return_images
    )
    
    response_results = {}
    for camera_name, hdr_result in hdr_results.items():
        if payload.return_images and isinstance(hdr_result, list):
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
            successful_captures = payload.exposure_levels if hdr_result else 0
            response_results[camera_name] = HDRCaptureResponse(
                success=hdr_result,
                message=f"HDR capture {'completed' if hdr_result else 'failed'}",
                successful_captures=successful_captures
            )
        else:
            response_results[camera_name] = HDRCaptureResponse(
                success=False,
                message="HDR capture failed",
                successful_captures=0
            )
    
    return BatchHDRCaptureResponse(
        success=len(response_results) > 0,
        data=response_results,
        message=f"Batch HDR capture completed for {len(response_results)} cameras"
    )

async def video_stream(camera: str) -> StreamingResponse:
    """Start a video stream from a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        StreamingResponse with MJPEG video stream
        
    Raises:
        CameraNotFoundError: If camera is not initialized
    """
    manager = get_camera_manager()
    active_cameras = manager.get_active_cameras()
    if camera not in active_cameras:
        raise CameraNotFoundError(f"Camera '{camera}' not initialized")
    
    camera_proxy = manager.get_camera(camera)
    
    async def generate():
        consecutive_failures = 0
        max_consecutive_failures = 10
        
        while True:
            try:
                # Check if camera is still active before attempting capture
                active_cameras = manager.get_active_cameras()
                if camera not in active_cameras:
                    logger.info(f"Camera '{camera}' no longer active, stopping video stream")
                    break
                
                capture_result = await camera_proxy.capture()
                if isinstance(capture_result, tuple):
                    success, img = capture_result
                else:
                    success = True
                    img = capture_result
                
                if not success or img is None:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        logger.warning(f"Camera '{camera}' failed {max_consecutive_failures} consecutive captures, stopping stream")
                        break
                    await asyncio.sleep(0.1)
                    continue
                
                # Reset failure counter on successful capture
                consecutive_failures = 0
                
                is_success, buffer = await asyncio.to_thread(cv2.imencode, ".jpg", img)
                if not is_success:
                    await asyncio.sleep(0.1)
                    continue
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                await asyncio.sleep(0.01)
            except CameraConnectionError:
                # Camera connection lost, likely closed
                logger.info(f"Camera '{camera}' connection lost, stopping video stream")
                break
            except KeyError:
                # Camera proxy no longer exists, likely closed
                logger.info(f"Camera '{camera}' proxy no longer exists, stopping video stream")
                break
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"video_stream_frame_failed: {e}")
                if consecutive_failures >= max_consecutive_failures:
                    logger.warning(f"Camera '{camera}' failed {max_consecutive_failures} consecutive times, stopping stream")
                    break
                await asyncio.sleep(0.1)
    
    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")

# Configuration Endpoints - Async
async def get_exposure(camera: str) -> FloatResponse:
    """Get the current exposure setting for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        FloatResponse with exposure value in microseconds
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    exposure = await camera_proxy.get_exposure()
    return FloatResponse(success=True, data=exposure, message=f"Exposure: {exposure} μs")

async def set_exposure(camera: str, payload: ExposureRequest) -> BoolResponse:
    """Set the exposure for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        payload: Exposure request containing the exposure value
        
    Returns:
        BoolResponse indicating success/failure
        
    Raises:
        CameraConfigurationError: If setting exposure fails
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    success = await camera_proxy.set_exposure(payload.exposure)
    if not success:
        raise CameraConfigurationError(f"Failed to set exposure to {payload.exposure} μs")
    return BoolResponse(success=True, message=f"Exposure set to {payload.exposure} μs")

async def get_exposure_range(camera: str) -> RangeResponse:
    """Get the valid exposure range for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        RangeResponse with minimum and maximum exposure values
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    exposure_range = await camera_proxy.get_exposure_range()
    return RangeResponse(
        success=True,
        data=exposure_range,
        message=f"Exposure range: {exposure_range[0]} - {exposure_range[1]} μs"
    )

async def get_trigger_mode(camera: str) -> StringResponse:
    """Get the current trigger mode for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        StringResponse with trigger mode ('continuous' or 'trigger')
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    trigger_mode = await camera_proxy.get_trigger_mode()
    return StringResponse(success=True, data=trigger_mode, message=f"Trigger mode: {trigger_mode}")

async def set_trigger_mode(camera: str, payload: TriggerModeRequest) -> BoolResponse:
    """Set the trigger mode for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        payload: Trigger mode request containing the mode
        
    Returns:
        BoolResponse indicating success/failure
        
    Raises:
        ValueError: If trigger mode is invalid
        CameraConfigurationError: If setting trigger mode fails
    """
    manager = get_camera_manager()
    if payload.mode not in ["continuous", "trigger"]:
        raise ValueError("Invalid trigger mode. Must be 'continuous' or 'trigger'")
    camera_proxy = manager.get_camera(camera)
    success = await camera_proxy.set_trigger_mode(payload.mode)
    if not success:
        raise CameraConfigurationError(f"Failed to set trigger mode to {payload.mode}")
    return BoolResponse(success=True, message=f"Trigger mode set to {payload.mode}")

async def get_white_balance(camera: str) -> StringResponse:
    """Get the current white balance setting for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        StringResponse with white balance mode
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    white_balance = await camera_proxy.get_white_balance()
    return StringResponse(success=True, data=white_balance, message=f"White balance: {white_balance}")

async def set_white_balance(camera: str, payload: WhiteBalanceRequest) -> BoolResponse:
    """Set the white balance for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        payload: White balance request containing the mode
        
    Returns:
        BoolResponse indicating success/failure
        
    Raises:
        CameraConfigurationError: If setting white balance fails
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    success = await camera_proxy.set_white_balance(payload.mode)
    if not success:
        raise CameraConfigurationError(f"Failed to set white balance to {payload.mode}")
    return BoolResponse(success=True, message=f"White balance set to {payload.mode}")

async def get_white_balance_modes(camera: str) -> WhiteBalanceListResponse:
    """Get available white balance modes for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        WhiteBalanceListResponse with list of available modes
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    modes = await camera_proxy.get_available_white_balance_modes()
    return WhiteBalanceListResponse(success=True, data=modes, message=f"Available white balance modes")

async def configure_batch_async(payload: BatchCameraConfigRequest) -> BatchOperationResponse:
    """Configure multiple cameras with async parameters in batch.
    
    Args:
        payload: Batch configuration request containing camera settings
        
    Returns:
        BatchOperationResponse with results for each camera
        
    Raises:
        ValueError: If any camera name format is invalid
    """
    manager = get_camera_manager()
    for camera_name in payload.configurations.keys():
        if ":" not in camera_name:
            raise ValueError(f"Invalid camera name format '{camera_name}'. Expected 'Backend:device_name'")
    
    async_configs = {}
    for camera_name, settings in payload.configurations.items():
        async_settings = {}
        for param, value in settings.items():
            if param in ["exposure", "trigger_mode", "white_balance"]:
                async_settings[param] = value
        
        if async_settings:
            async_configs[camera_name] = async_settings
    
    if not async_configs:
        return BatchOperationResponse(
            success=True,
            results={},
            successful_count=0,
            failed_count=0,
            message="No async configuration parameters provided"
        )
    
    results = await manager.batch_configure(async_configs)
    successful_count = sum(1 for success in results.values() if success)
    failed_count = len(results) - successful_count
    
    return BatchOperationResponse(
        success=failed_count == 0,
        results=results,
        successful_count=successful_count,
        failed_count=failed_count,
        message=f"Batch async configuration completed: {successful_count} successful, {failed_count} failed"
    )

# Configuration Endpoints - Sync
async def get_gain(camera: str) -> FloatResponse:
    """Get the current gain setting for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        FloatResponse with gain value
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    gain = await camera_proxy.get_gain()
    return FloatResponse(success=True, data=gain, message=f"Gain: {gain}")

async def set_gain(camera: str, payload: GainRequest) -> BoolResponse:
    """Set the gain for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        payload: Gain request containing the gain value
        
    Returns:
        BoolResponse indicating success/failure
        
    Raises:
        CameraConfigurationError: If setting gain fails
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    success = await camera_proxy.set_gain(payload.gain)
    if not success:
        raise CameraConfigurationError(f"Failed to set gain to {payload.gain}")
    return BoolResponse(success=True, message=f"Gain set to {payload.gain}")

async def get_gain_range(camera: str) -> RangeResponse:
    """Get the valid gain range for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        RangeResponse with minimum and maximum gain values
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    gain_range = await camera_proxy.get_gain_range()
    return RangeResponse(
        success=True,
        data=gain_range,
        message=f"Gain range: {gain_range[0]} - {gain_range[1]}"
    )

async def get_roi(camera: str) -> DictResponse:
    """Get the current ROI (Region of Interest) for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        DictResponse with ROI parameters (x, y, width, height)
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    roi = await camera_proxy.get_roi()
    return DictResponse(success=True, data=roi, message=f"Current ROI: {roi}")

async def set_roi(camera: str, payload: ROIRequest) -> BoolResponse:
    """Set the ROI (Region of Interest) for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        payload: ROI request containing x, y, width, height
        
    Returns:
        BoolResponse indicating success/failure
        
    Raises:
        ValueError: If ROI parameters are invalid
        CameraConfigurationError: If setting ROI fails
    """
    manager = get_camera_manager()
    if payload.width <= 0 or payload.height <= 0:
        raise ValueError("ROI width and height must be positive")
    if payload.x < 0 or payload.y < 0:
        raise ValueError("ROI x and y coordinates must be non-negative")
    
    camera_proxy = manager.get_camera(camera)
    success = await camera_proxy.set_roi(payload.x, payload.y, payload.width, payload.height)
    if not success:
        raise CameraConfigurationError(f"Failed to set ROI")
    return BoolResponse(success=True, message=f"ROI set to ({payload.x}, {payload.y}, {payload.width}, {payload.height})")

async def reset_roi(camera: str) -> BoolResponse:
    """Reset the ROI to full sensor size for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        BoolResponse indicating success/failure
        
    Raises:
        CameraConfigurationError: If resetting ROI fails
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    success = await camera_proxy.reset_roi()
    if not success:
        raise CameraConfigurationError(f"Failed to reset ROI")
    return BoolResponse(success=True, message="ROI reset to full sensor size")

async def get_pixel_format(camera: str) -> StringResponse:
    """Get the current pixel format for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        StringResponse with pixel format
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    pixel_format = await camera_proxy.get_pixel_format()
    return StringResponse(success=True, data=pixel_format, message=f"Pixel format: {pixel_format}")

async def set_pixel_format(camera: str, payload: PixelFormatRequest) -> BoolResponse:
    """Set the pixel format for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        payload: Pixel format request containing the format
        
    Returns:
        BoolResponse indicating success/failure
        
    Raises:
        CameraConfigurationError: If setting pixel format fails
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    success = await camera_proxy.set_pixel_format(payload.format)
    if not success:
        raise CameraConfigurationError(f"Failed to set pixel format to {payload.format}")
    return BoolResponse(success=True, message=f"Pixel format set to {payload.format}")

async def get_pixel_formats(camera: str) -> PixelFormatListResponse:
    """Get available pixel formats for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        PixelFormatListResponse with list of available formats
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    formats = await camera_proxy.get_available_pixel_formats()
    return PixelFormatListResponse(success=True, data=formats, message=f"Available pixel formats")

async def get_image_enhancement(camera: str) -> BoolResponse:
    """Get the current image enhancement status for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        
    Returns:
        BoolResponse with enhancement status
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    enabled = await camera_proxy.get_image_enhancement()
    return BoolResponse(success=True, data=enabled, message=f"Image enhancement: {'enabled' if enabled else 'disabled'}")

async def set_image_enhancement(camera: str, payload: ImageEnhancementRequest) -> BoolResponse:
    """Set the image enhancement for a camera.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        payload: Image enhancement request containing enabled flag
        
    Returns:
        BoolResponse indicating success/failure
        
    Raises:
        CameraConfigurationError: If setting image enhancement fails
    """
    manager = get_camera_manager()
    camera_proxy = manager.get_camera(camera)
    success = await camera_proxy.set_image_enhancement(payload.enabled)
    if not success:
        raise CameraConfigurationError(f"Failed to set image enhancement")
    return BoolResponse(success=True, message=f"Image enhancement {'enabled' if payload.enabled else 'disabled'}")

async def configure_batch_sync(payload: BatchCameraConfigRequest) -> BatchOperationResponse:
    """Configure multiple cameras with sync parameters in batch.
    
    Args:
        payload: Batch configuration request containing camera settings
        
    Returns:
        BatchOperationResponse with results for each camera
        
    Raises:
        ValueError: If any camera name format is invalid
    """
    manager = get_camera_manager()
    for camera_name in payload.configurations.keys():
        if ":" not in camera_name:
            raise ValueError(f"Invalid camera name format '{camera_name}'. Expected 'Backend:device_name'")
    
    sync_configs = {}
    for camera_name, settings in payload.configurations.items():
        sync_settings = {}
        for param, value in settings.items():
            if param in ["gain", "roi", "pixel_format", "image_enhancement"]:
                sync_settings[param] = value
        
        if sync_settings:
            sync_configs[camera_name] = sync_settings
    
    if not sync_configs:
        return BatchOperationResponse(
            success=True,
            results={},
            successful_count=0,
            failed_count=0,
            message="No sync configuration parameters provided"
        )
    
    results = await manager.batch_configure(sync_configs)
    successful_count = sum(1 for success in results.values() if success)
    failed_count = len(results) - successful_count
    
    return BatchOperationResponse(
        success=failed_count == 0,
        results=results,
        successful_count=successful_count,
        failed_count=failed_count,
        message=f"Batch sync configuration completed: {successful_count} successful, {failed_count} failed"
    )

# Configuration Persistence Endpoints
async def export_config(camera: str, payload: ConfigFileRequest) -> BoolResponse:
    """Export camera configuration to a file.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        payload: Config file request containing the file path
        
    Returns:
        BoolResponse indicating success/failure
        
    Raises:
        ValueError: If camera name format is invalid
        CameraNotFoundError: If camera is not initialized
        CameraConfigurationError: If export fails
    """
    manager = get_camera_manager()
    if ":" not in camera:
        raise ValueError("Invalid camera name format. Expected 'Backend:device_name'")
    
    active_cameras = manager.get_active_cameras()
    if camera not in active_cameras:
        raise CameraNotFoundError(f"Camera '{camera}' not initialized")
    
    camera_proxy = manager.get_camera(camera)
    success = await camera_proxy.save_config(payload.config_path)
    
    if not success:
        raise CameraConfigurationError(f"Failed to export configuration")
    
    return BoolResponse(
        success=True,
        message=f"Configuration exported to '{payload.config_path}'"
    )

async def import_config(camera: str, payload: ConfigFileRequest) -> BoolResponse:
    """Import camera configuration from a file.
    
    Args:
        camera: Camera name in format 'Backend:device_name'
        payload: Config file request containing the file path
        
    Returns:
        BoolResponse indicating success/failure
        
    Raises:
        ValueError: If camera name format is invalid
        CameraNotFoundError: If camera is not initialized
        CameraConfigurationError: If import fails
    """
    manager = get_camera_manager()
    if ":" not in camera:
        raise ValueError("Invalid camera name format. Expected 'Backend:device_name'")
    
    active_cameras = manager.get_active_cameras()
    if camera not in active_cameras:
        raise CameraNotFoundError(f"Camera '{camera}' not initialized")
    
    camera_proxy = manager.get_camera(camera)
    success = await camera_proxy.load_config(payload.config_path)
    
    if not success:
        raise CameraConfigurationError(f"Failed to import configuration")
    
    return BoolResponse(
        success=True,
        message=f"Configuration imported from '{payload.config_path}'"
    )

async def export_batch_config(payload: BatchConfigExportRequest) -> BatchOperationResponse:
    """Export configurations for multiple cameras in batch.
    
    Args:
        payload: Batch config export request containing camera names and file path pattern
        
    Returns:
        BatchOperationResponse with results for each camera
        
    Raises:
        ValueError: If any camera name format is invalid
    """
    manager = get_camera_manager()
    
    # Handle cameras as list
    camera_list = payload.cameras
    
    for camera_name in camera_list:
        if ":" not in camera_name:
            raise ValueError(f"Invalid camera name format '{camera_name}'. Expected 'Backend:device_name'")
    
    active_cameras = manager.get_active_cameras()
    results = {}
    for camera_name in camera_list:
        try:
            if camera_name not in active_cameras:
                results[camera_name] = False
                continue
                
            safe_camera_name = camera_name.replace(":", "_")
            config_path = payload.config_path.replace("{camera}", safe_camera_name)
            
            camera = manager.get_camera(camera_name)
            success = await camera.save_config(config_path)
            results[camera_name] = success
            
        except Exception as e:
            results[camera_name] = False
    
    successful_count = sum(1 for success in results.values() if success)
    failed_count = len(results) - successful_count
    
    return BatchOperationResponse(
        success=failed_count == 0,
        results=results,
        successful_count=successful_count,
        failed_count=failed_count,
        message=f"Batch export completed: {successful_count} successful, {failed_count} failed"
    )

async def import_batch_config(payload: BatchConfigImportRequest) -> BatchOperationResponse:
    """Import configurations for multiple cameras in batch.
    
    Args:
        payload: Batch config import request containing camera names and file path pattern
        
    Returns:
        BatchOperationResponse with results for each camera
        
    Raises:
        ValueError: If any camera name format is invalid
    """
    manager = get_camera_manager()
    
    # Handle cameras as list
    camera_list = payload.cameras
    
    active_cameras = manager.get_active_cameras()
    
    for camera_name in camera_list:
        if ":" not in camera_name:
            raise ValueError(f"Invalid camera name format '{camera_name}'. Expected 'Backend:device_name'")
    
    results = {}
    for camera_name in camera_list:
        try:
            if camera_name not in active_cameras:
                results[camera_name] = False
                continue
                
            safe_camera_name = camera_name.replace(":", "_")
            config_path = payload.config_path.replace("{camera}", safe_camera_name)
            
            camera = manager.get_camera(camera_name)
            success = await camera.load_config(config_path)
            results[camera_name] = success
            
        except Exception as e:
            results[camera_name] = False
    
    successful_count = sum(1 for success in results.values() if success)
    failed_count = len(results) - successful_count
    
    return BatchOperationResponse(
        success=failed_count == 0,
        results=results,
        successful_count=successful_count,
        failed_count=failed_count,
        message=f"Batch import completed: {successful_count} successful, {failed_count} failed"
    )

# Network Management Endpoints
async def get_bandwidth_info() -> DictResponse:
    """Get network bandwidth information and camera usage statistics.
    
    Returns:
        DictResponse with bandwidth info, camera counts by type, and network status
    """
    manager = get_camera_manager()
    bandwidth_info = manager.get_network_bandwidth_info()
    active_cameras = list(manager.get_active_cameras())
    
    gige_cameras = [cam for cam in active_cameras if "Basler" in cam or "Daheng" in cam]
    usb_cameras = [cam for cam in active_cameras if "OpenCV" in cam]
    mock_cameras = [cam for cam in active_cameras if "Mock" in cam]
    
    estimated_bandwidth_mb = (len(gige_cameras) * 6) + (len(usb_cameras) * 2)
    
    enhanced_info = {
        **bandwidth_info,
        "active_cameras_by_type": {
            "gige": len(gige_cameras),
            "usb": len(usb_cameras),
            "mock": len(mock_cameras),
            "total": len(active_cameras)
        },
        "camera_details": {
            "gige_cameras": gige_cameras,
            "usb_cameras": usb_cameras,
            "mock_cameras": mock_cameras
        },
        "estimated_bandwidth_mb_per_capture": estimated_bandwidth_mb,
        "network_status": "healthy" if len(active_cameras) <= bandwidth_info["max_concurrent_captures"] else "at_capacity"
    }
    
    return DictResponse(success=True, data=enhanced_info, message="Network bandwidth info retrieved")

async def get_concurrent_limit() -> IntResponse:
    """Get the current maximum concurrent capture limit.
    
    Returns:
        IntResponse with the current limit
    """
    manager = get_camera_manager()
    current_limit = manager.get_max_concurrent_captures()
    return IntResponse(success=True, data=current_limit, message=f"Current concurrent limit: {current_limit}")

async def set_concurrent_limit(payload: NetworkConcurrentLimitRequest) -> BoolResponse:
    """Set the maximum concurrent capture limit.
    
    Args:
        payload: Network concurrent limit request containing the new limit
        
    Returns:
        BoolResponse indicating success/failure
        
    Raises:
        ValueError: If limit is outside valid range (1-10)
    """
    manager = get_camera_manager()
    if payload.limit < 1 or payload.limit > 10:
        raise ValueError(f"Concurrent limit must be between 1 and 10, got {payload.limit}")
    manager.set_max_concurrent_captures(payload.limit)
    return BoolResponse(success=True, message=f"Concurrent limit set to {payload.limit}")

async def get_network_health() -> DictResponse:
    """Get comprehensive network health status and recommendations.
    
    Returns:
        DictResponse with health status, usage statistics, and recommendations
    """
    manager = get_camera_manager()
    active_cameras = list(manager.get_active_cameras())
    bandwidth_info = manager.get_network_bandwidth_info()
    
    max_concurrent = bandwidth_info["max_concurrent_captures"]
    current_usage = len(active_cameras)
    usage_percentage = (current_usage / max_concurrent) * 100 if max_concurrent > 0 else 0
    
    if usage_percentage <= 50:
        health_status = "healthy"
    elif usage_percentage <= 80:
        health_status = "at_capacity"
    else:
        health_status = "overloaded"
    
    recommendations = []
    warning_messages = []
    
    if health_status == "overloaded":
        recommendations.append(f"Consider increasing concurrent capture limit from {max_concurrent}")
        recommendations.append("Monitor network bandwidth during simultaneous captures")
        warning_messages.append(f"Current usage ({current_usage}) exceeds 80% of capacity ({max_concurrent})")
    
    gige_count = len([cam for cam in active_cameras if "Basler" in cam or "Daheng" in cam])
    if gige_count > 2:
        recommendations.append("Monitor GigE network switch performance with multiple cameras")
        if max_concurrent > 2:
            warning_messages.append(f"Multiple GigE cameras ({gige_count}) with high concurrent limit may saturate network")
    
    if not active_cameras:
        recommendations.append("Initialize cameras to begin network monitoring")
    
    health_report = {
        "status": health_status,
        "usage_percentage": round(usage_percentage, 1),
        "current_usage": current_usage,
        "max_capacity": max_concurrent,
        "camera_breakdown": {
            "gige": len([cam for cam in active_cameras if "Basler" in cam or "Daheng" in cam]),
            "usb": len([cam for cam in active_cameras if "OpenCV" in cam]),
            "mock": len([cam for cam in active_cameras if "Mock" in cam])
        },
        "recommendations": recommendations,
        "warning_messages": warning_messages,
        "timestamp": bandwidth_info
    }
    
    return DictResponse(success=True, data=health_report, message=f"Network health: {health_status} ({usage_percentage:.1f}% usage)")

# TaskSchemas
discover_cameras_task = TaskSchema(name="discover_cameras", input_schema=None, output_schema=ListResponse)
list_active_cameras_task = TaskSchema(name="list_active_cameras", input_schema=None, output_schema=ListResponse)
initialize_camera_task = TaskSchema(name="initialize_camera", input_schema=CameraInitializeRequest, output_schema=BoolResponse)
initialize_cameras_batch_task = TaskSchema(name="initialize_cameras_batch", input_schema=BatchCameraInitializeRequest, output_schema=BatchOperationResponse)
close_camera_task = TaskSchema(name="close_camera", input_schema=None, output_schema=BoolResponse)
close_all_cameras_task = TaskSchema(name="close_all_cameras", input_schema=None, output_schema=BoolResponse)
check_camera_connection_task = TaskSchema(name="check_camera_connection", input_schema=None, output_schema=StatusResponse)
get_camera_info_task = TaskSchema(name="get_camera_info", input_schema=None, output_schema=StatusResponse)

list_backends_task = TaskSchema(name="list_backends", input_schema=None, output_schema=ListResponse)
get_backend_info_task = TaskSchema(name="get_backend_info", input_schema=None, output_schema=DictResponse)
get_specific_backend_info_task = TaskSchema(name="get_specific_backend_info", input_schema=None, output_schema=DictResponse)
check_backends_health_task = TaskSchema(name="check_backends_health", input_schema=None, output_schema=DictResponse)

capture_image_task = TaskSchema(name="capture_image", input_schema=CaptureRequest, output_schema=CaptureResponse)
capture_batch_task = TaskSchema(name="capture_batch", input_schema=BatchCaptureRequest, output_schema=BatchOperationResponse)
capture_hdr_task = TaskSchema(name="capture_hdr", input_schema=HDRCaptureRequest, output_schema=HDRCaptureResponse)
capture_hdr_batch_task = TaskSchema(name="capture_hdr_batch", input_schema=BatchHDRCaptureRequest, output_schema=BatchHDRCaptureResponse)
video_stream_task = TaskSchema(name="video_stream", input_schema=None, output_schema=None)

get_exposure_task = TaskSchema(name="get_exposure", input_schema=None, output_schema=FloatResponse)
set_exposure_task = TaskSchema(name="set_exposure", input_schema=ExposureRequest, output_schema=BoolResponse)
get_exposure_range_task = TaskSchema(name="get_exposure_range", input_schema=None, output_schema=RangeResponse)
get_trigger_mode_task = TaskSchema(name="get_trigger_mode", input_schema=None, output_schema=StringResponse)
set_trigger_mode_task = TaskSchema(name="set_trigger_mode", input_schema=TriggerModeRequest, output_schema=BoolResponse)
get_white_balance_task = TaskSchema(name="get_white_balance", input_schema=None, output_schema=StringResponse)
set_white_balance_task = TaskSchema(name="set_white_balance", input_schema=WhiteBalanceRequest, output_schema=BoolResponse)
get_white_balance_modes_task = TaskSchema(name="get_white_balance_modes", input_schema=None, output_schema=WhiteBalanceListResponse)
configure_batch_async_task = TaskSchema(name="configure_batch_async", input_schema=BatchCameraConfigRequest, output_schema=BatchOperationResponse)

get_gain_task = TaskSchema(name="get_gain", input_schema=None, output_schema=FloatResponse)
set_gain_task = TaskSchema(name="set_gain", input_schema=GainRequest, output_schema=BoolResponse)
get_gain_range_task = TaskSchema(name="get_gain_range", input_schema=None, output_schema=RangeResponse)
get_roi_task = TaskSchema(name="get_roi", input_schema=None, output_schema=DictResponse)
set_roi_task = TaskSchema(name="set_roi", input_schema=ROIRequest, output_schema=BoolResponse)
reset_roi_task = TaskSchema(name="reset_roi", input_schema=None, output_schema=BoolResponse)
get_pixel_format_task = TaskSchema(name="get_pixel_format", input_schema=None, output_schema=StringResponse)
set_pixel_format_task = TaskSchema(name="set_pixel_format", input_schema=PixelFormatRequest, output_schema=BoolResponse)
get_pixel_formats_task = TaskSchema(name="get_pixel_formats", input_schema=None, output_schema=PixelFormatListResponse)
get_image_enhancement_task = TaskSchema(name="get_image_enhancement", input_schema=None, output_schema=BoolResponse)
set_image_enhancement_task = TaskSchema(name="set_image_enhancement", input_schema=ImageEnhancementRequest, output_schema=BoolResponse)
configure_batch_sync_task = TaskSchema(name="configure_batch_sync", input_schema=BatchCameraConfigRequest, output_schema=BatchOperationResponse)

export_config_task = TaskSchema(name="export_config", input_schema=ConfigFileRequest, output_schema=BoolResponse)
import_config_task = TaskSchema(name="import_config", input_schema=ConfigFileRequest, output_schema=BoolResponse)
export_batch_config_task = TaskSchema(name="export_batch_config", input_schema=BatchConfigExportRequest, output_schema=BatchOperationResponse)
import_batch_config_task = TaskSchema(name="import_batch_config", input_schema=BatchConfigImportRequest, output_schema=BatchOperationResponse)

get_bandwidth_info_task = TaskSchema(name="get_bandwidth_info", input_schema=None, output_schema=DictResponse)
get_concurrent_limit_task = TaskSchema(name="get_concurrent_limit", input_schema=None, output_schema=IntResponse)
set_concurrent_limit_task = TaskSchema(name="set_concurrent_limit", input_schema=NetworkConcurrentLimitRequest, output_schema=BoolResponse)
get_network_health_task = TaskSchema(name="get_network_health", input_schema=None, output_schema=DictResponse)

class CameraAPIService(Service):
    """Camera API Service providing REST endpoints for camera management and control.
    
    This service extends the base Service class to provide a comprehensive REST API
    for camera operations including discovery, initialization, configuration,
    capture, and network management. It supports multiple camera backends with
    unified async interfaces and proper error handling.
    
    The service includes:
    - Camera management (discovery, initialization, closing)
    - Backend management and health monitoring
    - Image capture (single, batch, HDR)
    - Video streaming
    - Camera configuration (exposure, gain, ROI, etc.)
    - Configuration persistence (import/export)
    - Network bandwidth management
    """
    
    def __init__(self, **kwargs):
        """Initialize the Camera API Service with all endpoints and middleware.
        
        Args:
            **kwargs: Additional arguments passed to the base Service class
        """
        super().__init__(
            summary="Camera API Service",
            description="REST API for camera management and control",
            **kwargs
        )
        
        # Add CORS middleware for web client support
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:8080"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Register exception handlers for proper error responses
        self.app.add_exception_handler(CameraError, camera_error_handler)
        self.app.add_exception_handler(ValueError, value_error_handler)
        self.app.add_exception_handler(KeyError, key_error_handler)
        self.app.add_exception_handler(Exception, general_exception_handler)
        
        # Add request logging middleware
        self.app.middleware("http")(log_requests)
        
        # Register all endpoints with proper HTTP methods
        self._register_camera_management_endpoints()
        self._register_backend_management_endpoints()
        self._register_capture_endpoints()
        self._register_configuration_endpoints()
        self._register_network_management_endpoints()
    
    def _register_camera_management_endpoints(self):
        """Register camera management endpoints."""
        # Camera Management - GET endpoints
        self.add_endpoint("cameras/discover", discover_cameras, discover_cameras_task, methods=["GET"])
        self.add_endpoint("cameras/active", list_active_cameras, list_active_cameras_task, methods=["GET"])
        self.add_endpoint("cameras/{camera}/connection", check_camera_connection, check_camera_connection_task, methods=["GET"])
        self.add_endpoint("cameras/{camera}/info", get_camera_info, get_camera_info_task, methods=["GET"])
        
        # Camera Management - POST endpoints
        self.add_endpoint("cameras/batch/initialize", initialize_cameras_batch, initialize_cameras_batch_task, methods=["POST"])
        self.add_endpoint("cameras/{camera}/initialize", initialize_camera, initialize_camera_task, methods=["POST"])
        
        # Camera Management - DELETE endpoints
        self.add_endpoint("cameras/{camera}", close_camera, close_camera_task, methods=["DELETE"])
        self.add_endpoint("cameras", close_all_cameras, close_all_cameras_task, methods=["DELETE"])
    
    def _register_backend_management_endpoints(self):
        """Register backend management endpoints."""
        # Backend Management - GET endpoints
        self.add_endpoint("backends", list_backends, list_backends_task, methods=["GET"])
        self.add_endpoint("backends/info", get_backend_info, get_backend_info_task, methods=["GET"])
        self.add_endpoint("backends/{backend}/info", get_specific_backend_info, get_specific_backend_info_task, methods=["GET"])
        self.add_endpoint("backends/health", check_backends_health, check_backends_health_task, methods=["GET"])
    
    def _register_capture_endpoints(self):
        """Register capture and streaming endpoints."""
        # Capture - POST endpoints
        self.add_endpoint("cameras/batch/capture", capture_batch, capture_batch_task, methods=["POST"])
        self.add_endpoint("cameras/batch/capture/hdr", capture_hdr_batch, capture_hdr_batch_task, methods=["POST"])
        self.add_endpoint("cameras/{camera}/capture", capture_image, capture_image_task, methods=["POST"])
        self.add_endpoint("cameras/{camera}/capture/hdr", capture_hdr, capture_hdr_task, methods=["POST"])
        
        # Video Streaming - GET endpoints
        self.add_endpoint("cameras/{camera}/stream", video_stream, video_stream_task, methods=["GET"])
    
    def _register_configuration_endpoints(self):
        """Register configuration and persistence endpoints."""
        # Configuration - Async - GET endpoints
        self.add_endpoint("cameras/{camera}/exposure", get_exposure, get_exposure_task, methods=["GET"])
        self.add_endpoint("cameras/{camera}/exposure/range", get_exposure_range, get_exposure_range_task, methods=["GET"])
        self.add_endpoint("cameras/{camera}/trigger-mode", get_trigger_mode, get_trigger_mode_task, methods=["GET"])
        self.add_endpoint("cameras/{camera}/white-balance", get_white_balance, get_white_balance_task, methods=["GET"])
        self.add_endpoint("cameras/{camera}/white-balance/modes", get_white_balance_modes, get_white_balance_modes_task, methods=["GET"])
        
        # Configuration - Async - PUT endpoints
        self.add_endpoint("cameras/{camera}/exposure", set_exposure, set_exposure_task, methods=["PUT"])
        self.add_endpoint("cameras/{camera}/trigger-mode", set_trigger_mode, set_trigger_mode_task, methods=["PUT"])
        self.add_endpoint("cameras/{camera}/white-balance", set_white_balance, set_white_balance_task, methods=["PUT"])
        
        # Configuration - Async - POST endpoints
        self.add_endpoint("cameras/batch/configure/async", configure_batch_async, configure_batch_async_task, methods=["POST"])
        
        # Configuration - Sync - GET endpoints
        self.add_endpoint("cameras/{camera}/gain", get_gain, get_gain_task, methods=["GET"])
        self.add_endpoint("cameras/{camera}/gain/range", get_gain_range, get_gain_range_task, methods=["GET"])
        self.add_endpoint("cameras/{camera}/roi", get_roi, get_roi_task, methods=["GET"])
        self.add_endpoint("cameras/{camera}/pixel-format", get_pixel_format, get_pixel_format_task, methods=["GET"])
        self.add_endpoint("cameras/{camera}/pixel-format/modes", get_pixel_formats, get_pixel_formats_task, methods=["GET"])
        self.add_endpoint("cameras/{camera}/image-enhancement", get_image_enhancement, get_image_enhancement_task, methods=["GET"])
        
        # Configuration - Sync - PUT endpoints
        self.add_endpoint("cameras/{camera}/gain", set_gain, set_gain_task, methods=["PUT"])
        self.add_endpoint("cameras/{camera}/roi", set_roi, set_roi_task, methods=["PUT"])
        self.add_endpoint("cameras/{camera}/pixel-format", set_pixel_format, set_pixel_format_task, methods=["PUT"])
        self.add_endpoint("cameras/{camera}/image-enhancement", set_image_enhancement, set_image_enhancement_task, methods=["PUT"])
        
        # Configuration - Sync - DELETE endpoints
        self.add_endpoint("cameras/{camera}/roi", reset_roi, reset_roi_task, methods=["DELETE"])
        
        # Configuration - Sync - POST endpoints
        self.add_endpoint("cameras/batch/configure/sync", configure_batch_sync, configure_batch_sync_task, methods=["POST"])
        
        # Configuration Persistence - POST endpoints
        self.add_endpoint("cameras/batch/config/export", export_batch_config, export_batch_config_task, methods=["POST"])
        self.add_endpoint("cameras/batch/config/import", import_batch_config, import_batch_config_task, methods=["POST"])
        self.add_endpoint("cameras/{camera}/config/export", export_config, export_config_task, methods=["POST"])
        self.add_endpoint("cameras/{camera}/config/import", import_config, import_config_task, methods=["POST"])
    
    def _register_network_management_endpoints(self):
        """Register network management endpoints."""
        # Network Management - GET endpoints
        self.add_endpoint("network/bandwidth", get_bandwidth_info, get_bandwidth_info_task, methods=["GET"])
        self.add_endpoint("network/concurrent-limit", get_concurrent_limit, get_concurrent_limit_task, methods=["GET"])
        self.add_endpoint("network/health", get_network_health, get_network_health_task, methods=["GET"])
        
        # Network Management - PUT endpoints
        self.add_endpoint("network/concurrent-limit", set_concurrent_limit, set_concurrent_limit_task, methods=["PUT"])

camera_api_service = CameraAPIService()
app = camera_api_service.app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info") 