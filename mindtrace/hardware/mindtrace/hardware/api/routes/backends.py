"""
Backend management routes for Camera API.

This module provides endpoints for managing and querying camera backends.
"""

import logging
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException

from mindtrace.hardware.mindtrace.hardware.cameras.camera_manager import CameraManager
from mindtrace.hardware.mindtrace.hardware.api.dependencies import get_camera_manager
from mindtrace.hardware.mindtrace.hardware.models.responses import (
    ListResponse,
    BackendInfoResponse,
    DictResponse
)
from mindtrace.hardware.mindtrace.hardware.core.exceptions import CameraError


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=ListResponse)
async def list_backends(
    manager: CameraManager = Depends(get_camera_manager)
) -> ListResponse:
    """
    List all available camera backends.
    
    Returns a list of discovered backend names. Backends are automatically
    discovered during CameraManager initialization.
    
    Returns:
        ListResponse: List of available backend names
    """
    try:
        backends = manager._discovered_backends
        
        logger.info(f"Retrieved {len(backends)} available backends")
        
        return ListResponse(
            success=True,
            data=backends,
            message=f"Found {len(backends)} available backends"
        )
    
    except Exception as e:
        logger.error(f"Failed to list backends: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve backends: {str(e)}"
        )


@router.get("/info", response_model=BackendInfoResponse)
async def get_backend_info(
    manager: CameraManager = Depends(get_camera_manager)
) -> BackendInfoResponse:
    """
    Get detailed information about all available backends.
    
    Returns detailed information about each backend including:
    - Backend name
    - Availability status
    - Number of detected cameras
    - SDK availability
    
    Returns:
        BackendInfoResponse: Detailed backend information
    """
    try:
        backends = manager._discovered_backends
        backend_info = {}
        
        for backend in backends:
            try:
                # Get basic backend info
                info = {
                    "name": backend,
                    "available": True,
                    "sdk_available": True,
                    "cameras": []
                }
                
                # Try to get cameras for this backend
                try:
                    cameras = manager.discover_cameras(backends=backend)
                    info["cameras"] = cameras
                    info["camera_count"] = len(cameras)
                except Exception as e:
                    logger.warning(f"Failed to discover cameras for backend {backend}: {e}")
                    info["cameras"] = []
                    info["camera_count"] = 0
                    info["error"] = str(e)
                
                backend_info[backend] = info
                
            except Exception as e:
                logger.warning(f"Failed to get info for backend {backend}: {e}")
                backend_info[backend] = {
                    "name": backend,
                    "available": False,
                    "sdk_available": False,
                    "error": str(e),
                    "cameras": [],
                    "camera_count": 0
                }
        
        logger.info(f"Retrieved information for {len(backend_info)} backends")
        
        return BackendInfoResponse(
            success=True,
            data=backend_info,
            message=f"Backend information retrieved for {len(backend_info)} backends"
        )
    
    except Exception as e:
        logger.error(f"Failed to get backend info: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve backend information: {str(e)}"
        )


@router.get("/{backend_name}", response_model=DictResponse)
async def get_specific_backend_info(
    backend_name: str,
    manager: CameraManager = Depends(get_camera_manager)
) -> DictResponse:
    """
    Get information about a specific backend.
    
    Args:
        backend_name: Name of the backend to get information for
        
    Returns:
        DictResponse: Detailed information about the specified backend
        
    Raises:
        HTTPException: If backend is not found or unavailable
    """
    try:
        backends = manager._discovered_backends
        
        if backend_name not in backends:
            raise HTTPException(
                status_code=404,
                detail=f"Backend '{backend_name}' not found. Available backends: {', '.join(backends)}"
            )
        
        # Get specific backend info
        info = {
            "name": backend_name,
            "available": True,
            "sdk_available": True,
            "cameras": []
        }
        
        try:
            # Get cameras for this specific backend
            cameras = manager.discover_cameras(backends=backend_name)
            info["cameras"] = cameras
            info["camera_count"] = len(cameras)
            
            # Add additional details
            if backend_name.startswith("Mock"):
                info["type"] = "mock"
                info["description"] = f"Mock backend for testing ({backend_name})"
            else:
                info["type"] = "hardware"
                info["description"] = f"Hardware backend for {backend_name} cameras"
                
        except Exception as e:
            logger.warning(f"Failed to get camera info for backend {backend_name}: {e}")
            info["cameras"] = []
            info["camera_count"] = 0
            info["error"] = str(e)
        
        logger.info(f"Retrieved information for backend '{backend_name}'")
        
        return DictResponse(
            success=True,
            data=info,
            message=f"Backend information retrieved for '{backend_name}'"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get backend info for {backend_name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve backend information: {str(e)}"
        )


@router.get("/status/health", response_model=DictResponse)
async def check_backends_health(
    manager: CameraManager = Depends(get_camera_manager)
) -> DictResponse:
    """
    Check the health status of all backends.
    
    Performs a health check on all discovered backends to ensure they
    are functioning properly.
    
    Returns:
        DictResponse: Health status of all backends
    """
    try:
        backends = manager._discovered_backends
        health_status = {
            "total_backends": len(backends),
            "healthy_backends": 0,
            "unhealthy_backends": 0,
            "backend_status": {}
        }
        
        for backend in backends:
            try:
                # Test backend by trying to discover cameras
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
        
        logger.info(
            f"Backend health check completed: {health_status['healthy_backends']} healthy, "
            f"{health_status['unhealthy_backends']} unhealthy"
        )
        
        return DictResponse(
            success=overall_healthy,
            data=health_status,
            message=f"Backend health check completed. {health_status['healthy_backends']} healthy, "
                   f"{health_status['unhealthy_backends']} unhealthy"
        )
    
    except Exception as e:
        logger.error(f"Failed to check backend health: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check backend health: {str(e)}"
        ) 