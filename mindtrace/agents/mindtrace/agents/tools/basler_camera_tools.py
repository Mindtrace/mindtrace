from typing import Any, Dict
from mindtrace.hardware import AsyncCameraManager


# Tool metadata for discovery and serving
__toolkit_name__ = "basler_camera_tools"
__toolkit_description__ = "Tools for controlling and configuring Basler cameras"
__toolkit_tags__ = ["camera", "hardware", "basler"]
__toolkit_version__ = "0.7.1"

async def discover_available_cameras() -> Dict[str, Any]:
    """
    Discover all available Basler cameras connected to the system. Get detailed information about the cameras.
    
    Returns:
        {
            "status": "success",
            "cameras": [
                {
                    "name": "cam1",
                    "serial_number": "12345678",
                    "model": "acA1920-40gm",
                    "vendor": "Basler",
                    "device_class": "BaslerGigE",
                    "interface": "GigE",
                    "friendly_name": "cam1",
                    "ip_address": "192.168.1.100"
                    "user_defined_name": "cam1"
                },
                ...
            ],
            "count": 3
        }
    
    Usage Example:
        User: "Discover all cameras" or "Find all Basler cameras" or "List all Basler cameras"
        Agent: Calls discover_available_cameras()
        Response: "I found 3 Basler cameras: cam1 (acA1920-40gm), cam2 (...), cam3 (...)"
    """
        # discover() is a class method, not an instance method, and not async
    camera_details = AsyncCameraManager.discover(backends=["Basler"], details=True, include_mocks=False)
    return {
        "status": "success",
        "cameras": camera_details,
        "count": len(camera_details)
    }

async def discover_camera_parameters(camera_name: str) -> Dict[str, Any]:
    """Discover the parameters of a Basler camera.
    
    This tool connects to a Basler camera and retrieves all available
    parameters that can be configured.
    
    Args:
        camera_name: The name of the camera to discover the parameters of.
                    If not prefixed with "Basler:", it will be added automatically.

    Returns:
        A dictionary with the parameters of the camera, including their
        current values, types, and valid ranges.
    """    
    async with AsyncCameraManager(include_mocks=False) as camera_manager:
        if not camera_name.startswith("Basler:"):
            camera_name = f"Basler:{camera_name}"
        cam = await camera_manager.open(names=camera_name, test_connection=True)
        params = await cam.discover_camera_parameters()
        return params

async def set_camera_parameter(
    camera_name: str, 
    parameter_name: str, 
    value: Any
) -> Dict[str, Any]:
    """Set a camera parameter by name.
    
    This tool allows you to configure a specific parameter on a Basler camera.
    Use discover_camera_parameters first to see available parameters.
    
    Args:
        camera_name: The name of the camera to set the parameter of.
                    If not prefixed with "Basler:", it will be added automatically.
        parameter_name: The name of the parameter to set (e.g., "ExposureTime", "Gain").
        value: The value to set the parameter to. Type depends on the parameter.
        
    Returns:
        A dictionary containing the result of the operation, including
        the parameter name, old value, new value, and success status.
        
    Example:
        >>> result = await set_camera_parameter("MyCamera", "ExposureTime", 10000)
        >>> print(result["success"])
    """    
    async with AsyncCameraManager(include_mocks=False) as camera_manager:
        if not camera_name.startswith("Basler:"):
            camera_name = f"Basler:{camera_name}"
        cam = await camera_manager.open(names=camera_name, test_connection=True)
        return await cam.set_camera_parameter(parameter_name, value)

async def get_camera_status(camera_name: str) -> Dict[str, Any]:
    """
    Get the status of a Basler camera. Get the current settings and connection status of the camera.
    
    Args:
        camera_name: Name of the camera
    
    Returns:
        {
            "status": "success",
            "camera_name": "cam1",
            "connected": true,
            "current_settings": {
                "ExposureTime": 5000,
                "Gain": 0,
                "TriggerMode": "Off",
                ...
            },
        }
    """
    async with AsyncCameraManager(include_mocks=False) as camera_manager:
        if not camera_name.startswith("Basler:"):
            camera_name = f"Basler:{camera_name}"
        
        cam = await camera_manager.open(names=camera_name, test_connection=True)
        params = await cam.discover_camera_parameters()
        
        # Extract current values
        current_settings = {}
        for param_name, param_info in params.get("parameters", {}).items():
            if "current_value" in param_info:
                current_settings[param_name] = param_info["current_value"]
        
        return {
            "status": "success",
            "camera_name": camera_name,
            "connected": True,
            "current_settings": current_settings
        }


# Export all tools
__all__ = [
    "discover_available_cameras",
    "discover_camera_parameters",
    "set_camera_parameter",
    "get_camera_status",
]