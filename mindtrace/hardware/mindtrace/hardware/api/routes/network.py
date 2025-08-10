"""
Network Management API Routes

Handles network bandwidth management and concurrent capture limits.
Provides endpoints for monitoring and controlling network usage across cameras.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from mindtrace.hardware.api.dependencies import get_camera_manager
from mindtrace.hardware.cameras.core.camera_manager import CameraManager
from mindtrace.hardware.models.requests import NetworkConcurrentLimitRequest
from mindtrace.hardware.models.responses import (
    BoolResponse,
    DictResponse,
    IntResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/bandwidth", response_model=DictResponse)
async def get_bandwidth_info(manager: CameraManager = Depends(get_camera_manager)) -> DictResponse:
    """Get network bandwidth management information.

    Returns comprehensive information about network bandwidth usage,
    concurrent capture limits, and camera status for network management.

    Args:
        manager: Camera manager instance

    Returns:
        DictResponse: Network bandwidth information including:
        - max_concurrent_captures: Current concurrent capture limit
        - active_cameras: Number of active cameras
        - gige_cameras: Number of GigE cameras (Basler)
        - bandwidth_management_enabled: Always True
        - recommended_settings: Recommended limits for different scenarios

    Raises:
        500: If unexpected error occurs
    """
    try:
        logger.info("Retrieving network bandwidth information")

        # Get bandwidth information from camera manager
        bandwidth_info = manager.get_network_bandwidth_info()

        # Add additional runtime information
        active_cameras = list(manager.get_active_cameras())

        # Categorize cameras by type
        gige_cameras = [cam for cam in active_cameras if "Basler" in cam]
        usb_cameras = [cam for cam in active_cameras if "OpenCV" in cam]
        mock_cameras = [cam for cam in active_cameras if "Mock" in cam]

        # Calculate estimated bandwidth usage
        # Rough estimates: GigE cameras ~6MB/image, USB cameras ~2MB/image
        estimated_bandwidth_mb = (len(gige_cameras) * 6) + (len(usb_cameras) * 2)

        # Enhanced bandwidth information
        enhanced_info = {
            **bandwidth_info,
            "active_cameras_by_type": {
                "gige": len(gige_cameras),
                "usb": len(usb_cameras),
                "mock": len(mock_cameras),
                "total": len(active_cameras),
            },
            "camera_details": {"gige_cameras": gige_cameras, "usb_cameras": usb_cameras, "mock_cameras": mock_cameras},
            "estimated_bandwidth_mb_per_capture": estimated_bandwidth_mb,
            "network_status": "healthy"
            if len(active_cameras) <= bandwidth_info["max_concurrent_captures"]
            else "at_capacity",
        }

        logger.info(f"Network bandwidth info retrieved: {len(active_cameras)} active cameras")

        return DictResponse(
            success=True,
            data=enhanced_info,
            message=f"Network bandwidth information retrieved for {len(active_cameras)} active cameras",
        )

    except Exception as e:
        logger.error(f"Failed to retrieve network bandwidth info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve network bandwidth info: {str(e)}")


@router.get("/concurrent-limit", response_model=IntResponse)
async def get_concurrent_limit(manager: CameraManager = Depends(get_camera_manager)) -> IntResponse:
    """Get current concurrent capture limit.

    Returns the current maximum number of cameras that can capture simultaneously.
    This limit is used for network bandwidth management.

    Args:
        manager: Camera manager instance

    Returns:
        IntegerResponse: Current concurrent capture limit

    Raises:
        500: If unexpected error occurs
    """
    try:
        logger.info("Retrieving concurrent capture limit")

        # Get current limit from camera manager
        current_limit = manager.get_max_concurrent_captures()

        logger.info(f"Current concurrent capture limit: {current_limit}")

        return IntResponse(
            success=True, data=current_limit, message=f"Current concurrent capture limit: {current_limit}"
        )

    except Exception as e:
        logger.error(f"Failed to retrieve concurrent capture limit: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve concurrent capture limit: {str(e)}")


@router.post("/concurrent-limit", response_model=BoolResponse)
async def set_concurrent_limit(
    request: NetworkConcurrentLimitRequest, manager: CameraManager = Depends(get_camera_manager)
) -> BoolResponse:
    """Set concurrent capture limit for network bandwidth management.

    Updates the maximum number of cameras that can capture simultaneously.
    This is crucial for managing network bandwidth, especially with GigE cameras.

    **Recommendations:**
    - Conservative: 1 (for critical applications)
    - Balanced: 2 (for most applications)
    - Aggressive: 3+ (only for high-bandwidth networks)

    Args:
        request: Network concurrent limit request with new limit
        manager: Camera manager instance

    Returns:
        BoolResponse: Success status and confirmation

    Raises:
        400: If limit value is invalid
        500: If unexpected error occurs
    """
    try:
        logger.info(f"Setting concurrent capture limit to {request.limit}")

        # Validate limit value
        if request.limit < 1 or request.limit > 10:
            raise ValueError(f"Concurrent capture limit must be between 1 and 10, got {request.limit}")

        # Set the new limit
        manager.set_max_concurrent_captures(request.limit)

        logger.info(f"Concurrent capture limit set to {request.limit}")

        return BoolResponse(success=True, data=True, message=f"Concurrent capture limit set to {request.limit}")

    except ValueError:
        # Re-raise ValueError to let app.py handlers convert to 400
        raise
    except Exception as e:
        logger.error(f"Failed to set concurrent capture limit: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to set concurrent capture limit: {str(e)}")


@router.get("/health", response_model=DictResponse)
async def get_network_health(manager: CameraManager = Depends(get_camera_manager)) -> DictResponse:
    """Get network health status and recommendations.

    Provides a comprehensive health check of the network configuration
    including current usage, capacity, and optimization recommendations.

    Args:
        manager: Camera manager instance

    Returns:
        DictResponse: Network health information including:
        - status: "healthy", "at_capacity", or "overloaded"
        - usage_percentage: Current usage as percentage of capacity
        - recommendations: Optimization suggestions
        - warning_messages: Any warnings or issues

    Raises:
        500: If unexpected error occurs
    """
    try:
        logger.info("Checking network health status")

        # Get current network information
        bandwidth_info = manager.diagnostics()
        active_cameras = list(manager.active_cameras)

        # Calculate health metrics
        max_concurrent = bandwidth_info["max_concurrent_captures"]
        current_usage = len(active_cameras)
        usage_percentage = (current_usage / max_concurrent) * 100 if max_concurrent > 0 else 0

        # Determine health status
        if usage_percentage <= 50:
            health_status = "healthy"
        elif usage_percentage <= 80:
            health_status = "at_capacity"
        else:
            health_status = "overloaded"

        # Generate recommendations
        recommendations = []
        warning_messages = []

        if health_status == "overloaded":
            recommendations.append(f"Consider increasing concurrent capture limit from {max_concurrent}")
            recommendations.append("Monitor network bandwidth during simultaneous captures")
            warning_messages.append(f"Current usage ({current_usage}) exceeds 80% of capacity ({max_concurrent})")

        gige_count = len([cam for cam in active_cameras if "Basler" in cam])
        if gige_count > 2:
            recommendations.append("Monitor GigE network switch performance with multiple cameras")
            if max_concurrent > 2:
                warning_messages.append(
                    f"Multiple GigE cameras ({gige_count}) with high concurrent limit may saturate network"
                )

        if not active_cameras:
            recommendations.append("Initialize cameras to begin network monitoring")

        # Compile health report
        health_report = {
            "status": health_status,
            "usage_percentage": round(usage_percentage, 1),
            "current_usage": current_usage,
            "max_capacity": max_concurrent,
            "camera_breakdown": {
                "gige": len([cam for cam in active_cameras if "Basler" in cam]),
                "usb": len([cam for cam in active_cameras if "OpenCV" in cam]),
                "mock": len([cam for cam in active_cameras if "Mock" in cam]),
            },
            "recommendations": recommendations,
            "warning_messages": warning_messages,
            "timestamp": manager.diagnostics(),  # This will include timestamp if available
        }

        logger.info(f"Network health check completed: {health_status} ({usage_percentage:.1f}% usage)")

        return DictResponse(
            success=True, data=health_report, message=f"Network health: {health_status} ({usage_percentage:.1f}% usage)"
        )

    except Exception as e:
        logger.error(f"Failed to check network health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check network health: {str(e)}")
