"""
Camera Manager for Mindtrace Hardware System

This module provides a unified interface for managing multiple camera backends
with graceful SDK handling, comprehensive error management, and async operations.

Features:
    - Multiple camera backends (Daheng, Basler, OpenCV)
    - Mock implementations for testing
    - Lazy loading of camera SDKs
    - Async camera operations with thread-safe locks
    - Configuration management
    - Comprehensive error handling
    - Batch camera initialization

Supported Backends:
    - Daheng: Industrial cameras with gxipy SDK
    - Basler: Industrial cameras with pypylon SDK  
    - OpenCV: USB/webcam cameras with opencv-python
    - MockDaheng: Mock Daheng cameras for testing
    - MockBasler: Mock Basler cameras for testing

Error Handling:
    - CameraError: Base camera operation errors
    - CameraNotFoundError: Camera not found or not registered
    - CameraInitializationError: Camera setup failures
    - CameraCaptureError: Image capture failures
    - CameraConfigurationError: Configuration errors
    - SDKNotAvailableError: Required SDK not installed
    - CameraTimeoutError: Operation timeout errors

Usage:
    from mindtrace.hardware.cameras import CameraManager
    
    # Initialize manager with specific backends
    manager = CameraManager(backends=["Daheng", "Basler"])
    
    # Get available cameras
    cameras = manager.get_available_cameras()
    
    # Initialize and use cameras
    await manager.initialize_cameras([cameras[0]])
    image = await manager.capture(cameras[0])
    
    # Cleanup
    manager.de_initialize_cameras([cameras[0]])
"""

import os
import asyncio
from typing import Dict, List, Optional, Any, Tuple
import cv2

from mindtrace.hardware.cameras.backends.base import BaseCamera
from mindtrace.core.base.mindtrace_base import Mindtrace
from mindtrace.hardware.core.exceptions import (
    CameraError, CameraNotFoundError, CameraInitializationError,
    CameraCaptureError, CameraConfigurationError, SDKNotAvailableError,
    CameraTimeoutError, HardwareTimeoutError
)

# Global caches for lazy loading
_daheng_cache = {"checked": False, "available": False, "class": None}
_basler_cache = {"checked": False, "available": False, "class": None}
_opencv_cache = {"checked": False, "available": False, "class": None}


def _get_daheng_backend(logger=None) -> Tuple[bool, Optional[Any]]:
    """
    Lazy import and cache Daheng camera backend.
    
    Args:
        logger: Optional logger to use for logging messages
    
    Returns:
        Tuple of (availability_flag, camera_class)
    """
    if not _daheng_cache["checked"]:
        try:
            from mindtrace.hardware.cameras.backends.daheng import DahengCamera, DAHENG_AVAILABLE
            _daheng_cache["available"] = DAHENG_AVAILABLE
            _daheng_cache["class"] = DahengCamera if DAHENG_AVAILABLE else None
            if logger:
                logger.debug("Daheng backend loaded successfully")
        except ImportError as e:
            _daheng_cache["available"] = False
            _daheng_cache["class"] = None
            if logger:
                logger.debug(f"Daheng backend not available: {e}")
        finally:
            _daheng_cache["checked"] = True
    
    return _daheng_cache["available"], _daheng_cache["class"]


def _get_basler_backend(logger=None) -> Tuple[bool, Optional[Any]]:
    """
    Lazy import and cache Basler camera backend.
    
    Args:
        logger: Optional logger to use for logging messages
    
    Returns:
        Tuple of (availability_flag, camera_class)
    """
    if not _basler_cache["checked"]:
        try:
            from mindtrace.hardware.cameras.backends.basler import BaslerCamera, BASLER_AVAILABLE
            _basler_cache["available"] = BASLER_AVAILABLE
            _basler_cache["class"] = BaslerCamera if BASLER_AVAILABLE else None
            if logger:
                logger.debug("Basler backend loaded successfully")
        except ImportError as e:
            _basler_cache["available"] = False
            _basler_cache["class"] = None
            if logger:
                logger.debug(f"Basler backend not available: {e}")
        finally:
            _basler_cache["checked"] = True
    
    return _basler_cache["available"], _basler_cache["class"]


def _get_opencv_backend(logger=None) -> Tuple[bool, Optional[Any]]:
    """
    Lazy import and cache OpenCV camera backend.
    
    Args:
        logger: Optional logger to use for logging messages
    
    Returns:
        Tuple of (availability_flag, camera_class)
    """
    if not _opencv_cache["checked"]:
        try:
            from mindtrace.hardware.cameras.backends.opencv import OpenCVCamera, OPENCV_AVAILABLE
            _opencv_cache["available"] = OPENCV_AVAILABLE
            _opencv_cache["class"] = OpenCVCamera if OPENCV_AVAILABLE else None
            if logger:
                logger.debug("OpenCV backend loaded successfully")
        except ImportError as e:
            _opencv_cache["available"] = False
            _opencv_cache["class"] = None
            if logger:
                logger.debug(f"OpenCV backend not available: {e}")
        finally:
            _opencv_cache["checked"] = True
    
    return _opencv_cache["available"], _opencv_cache["class"]


# Mock implementations will be imported lazily when needed
def _get_mock_daheng_camera():
    """Lazy import for MockDahengCamera."""
    try:
        from mindtrace.hardware.cameras.backends.daheng.mock_daheng import MockDahengCamera
        return MockDahengCamera
    except ImportError as e:
        raise CameraInitializationError(f"MockDahengCamera not available: {e}")

def _get_mock_basler_camera():
    """Lazy import for MockBaslerCamera."""
    try:
        from mindtrace.hardware.cameras.backends.basler.mock_basler import MockBaslerCamera
        return MockBaslerCamera
    except ImportError as e:
        raise CameraInitializationError(f"MockBaslerCamera not available: {e}")


class CameraManager(Mindtrace):
    """
    Unified camera manager supporting multiple camera backends.
    
    This class provides a high-level interface for managing cameras from different
    manufacturers with graceful SDK handling, comprehensive error management,
    and async operations support. Supports both sync and async camera backends.
    
    Attributes:
        backends: List of registered backend names
        cameras: Dictionary of initialized camera instances
        camera_locks: Dictionary of async locks for thread-safe operations
        config: Core configuration instance
        logger: Centralized logger instance
    """
    
    def __init__(self, backends: Optional[List[str]] = None):
        """
        Initialize camera manager.
        
        Args:
            backends: List of backend names to register initially.
                     If None, no backends are registered by default.
        """
        super().__init__()
        
        self.camera_locks: Dict[str, asyncio.Lock] = {}
        self.cameras: Dict[str, BaseCamera] = {}
        self.backends: List[str] = backends.copy() if backends else []
        
        self.logger.info(f"Camera manager initialized with backends: {self.backends}")



    def register_backend(self, backend_name: str) -> bool:
        """
        Register a single camera backend.
        
        Args:
            backend_name: Name of backend to register (case-insensitive)
            
        Returns:
            True if registration successful, False otherwise
            
        Raises:
            CameraConfigurationError: If backend name is invalid
        """
        if not isinstance(backend_name, str) or not backend_name.strip():
            raise CameraConfigurationError("Backend name must be a non-empty string")
            
        backend_name = backend_name.strip()
        
        if backend_name not in self.backends:
            if self._is_backend_available(backend_name):
                self.backends.append(backend_name)
                self.logger.info(f"Backend '{backend_name}' registered successfully")
                return True
            else:
                self.logger.warning(f"Backend '{backend_name}' is not available")
                return False
        else:
            self.logger.debug(f"Backend '{backend_name}' already registered")
            return True
    
    def register_backends(self, backend_names: List[str]) -> bool:
        """
        Register multiple camera backends.
        
        Args:
            backend_names: List of backend names to register
            
        Returns:
            True if all registrations successful, False if any failed
            
        Raises:
            CameraConfigurationError: If backend_names is not a list
        """
        if not isinstance(backend_names, list):
            raise CameraConfigurationError("backend_names must be a list")
            
        self.logger.info(f"Registering backends: {backend_names}")
        
        success = True
        for backend_name in backend_names:
            try:
                if not self.register_backend(backend_name):
                    success = False
            except Exception as e:
                self.logger.error(f"Failed to register backend '{backend_name}': {e}")
                success = False
                
        return success

    def _is_backend_available(self, backend_name: str) -> bool:
        """
        Check if a camera backend is available.
        
        Args:
            backend_name: Name of backend to check
            
        Returns:
            True if backend is available, False otherwise
        """
        backend_lower = backend_name.lower()
        
        if backend_lower == "daheng":
            available, _ = _get_daheng_backend(self.logger)
            return available
        elif backend_lower == "basler":
            available, _ = _get_basler_backend(self.logger)
            return available
        elif backend_lower == "opencv":
            available, _ = _get_opencv_backend(self.logger)
            return available
        elif backend_lower in ["mockdaheng", "mockbasler"]:
            return True
        else:
            self.logger.warning(f"Unknown backend: {backend_name}")
            return False

    def get_supported_backends(self) -> List[str]:
        """
        Get list of currently registered backends.
        
        Returns:
            Copy of registered backends list
        """
        return self.backends.copy()

    def get_available_backends(self) -> List[str]:
        """
        Get list of all available backends (including unregistered ones).
        
        Returns:
            List of available backend names
        """
        available = []
        
        daheng_available, _ = _get_daheng_backend()
        if daheng_available:
            available.append("Daheng")
            
        basler_available, _ = _get_basler_backend()
        if basler_available:
            available.append("Basler")
            
        opencv_available, _ = _get_opencv_backend()
        if opencv_available:
            available.append("OpenCV")
        
        available.extend(["MockDaheng", "MockBasler"])
        
        return available

    def get_backend_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get detailed status information for all backends.
        
        Returns:
            Dictionary with backend status information including:
            - available: Whether the backend is available
            - registered: Whether the backend is registered
            - sdk_name: Name of required SDK
            - error: Error message if not available
        """
        status = {}
        
        daheng_available, _ = _get_daheng_backend()
        status["Daheng"] = {
            "available": daheng_available,
            "registered": "Daheng" in self.backends,
            "sdk_name": "gxipy",
            "error": None if daheng_available else "gxipy SDK not installed"
        }
        
        basler_available, _ = _get_basler_backend()
        status["Basler"] = {
            "available": basler_available,
            "registered": "Basler" in self.backends,
            "sdk_name": "pypylon",
            "error": None if basler_available else "pypylon SDK not installed"
        }
        
        opencv_available, _ = _get_opencv_backend()
        status["OpenCV"] = {
            "available": opencv_available,
            "registered": "OpenCV" in self.backends,
            "sdk_name": "opencv-python",
            "error": None if opencv_available else "opencv-python not installed"
        }
        
        status["MockDaheng"] = {
            "available": True,
            "registered": "MockDaheng" in self.backends,
            "sdk_name": "built-in",
            "error": None
        }
        
        status["MockBasler"] = {
            "available": True,
            "registered": "MockBasler" in self.backends,
            "sdk_name": "built-in",
            "error": None
        }
        
        return status

    def get_installation_instructions(self, backend: str) -> Optional[str]:
        """
        Get installation instructions for a specific backend.
        
        Args:
            backend: Backend name
            
        Returns:
            Installation instructions string, or None if backend unknown
        """
        backend_lower = backend.lower()
        
        if backend_lower == "daheng":
            return (
                "Install gxipy to use Daheng cameras:\n"
                "1. Github repository: https://github.com/Mindtrace/gxipy\n"
                "2. uv run pip install git+https://github.com/Mindtrace/gxipy.git\n"
                "3. If using Windows, restart VS Code after DahengSDK installation for environment variable updates."
            )
        elif backend_lower == "basler":
            return (
                "Install pypylon to use Basler cameras:\n"
                "1. Download and install Basler pylon SDK from https://www.baslerweb.com/en/downloads/software-downloads/\n"
                "2. pip install pypylon\n"
                "3. Ensure camera drivers are properly installed."
            )
        elif backend_lower == "opencv":
            return (
                "Install opencv-python to use USB/webcam cameras:\n"
                "1. pip install opencv-python\n"
                "2. Connect USB camera or webcam\n"
                "3. No additional drivers needed for most USB cameras."
            )
        else:
            return None

    def get_available_cameras(self) -> List[str]:
        """
        Get list of available cameras from all registered backends.
        
        Returns:
            List of camera names in format "Backend:camera_name"
            
        Raises:
            CameraError: If camera discovery fails for critical reasons
        """
        cam_list = []
        
        for backend in self.backends:
            try:
                backend_lower = backend.lower()
                
                if backend_lower == "daheng":
                    available, DahengCamera = _get_daheng_backend()
                    if available and DahengCamera:
                        cams = DahengCamera.get_available_cameras()
                        cams = [f"{backend}:{cam}" for cam in cams]
                        cam_list.extend(cams)
                elif backend_lower == "basler":
                    available, BaslerCamera = _get_basler_backend()
                    if available and BaslerCamera:
                        cams = BaslerCamera.get_available_cameras()
                        cams = [f"{backend}:{cam}" for cam in cams]
                        cam_list.extend(cams)
                elif backend_lower == "opencv":
                    available, OpenCVCamera = _get_opencv_backend()
                    if available and OpenCVCamera:
                        cams = OpenCVCamera.get_available_cameras()
                        cams = [f"{backend}:{cam}" for cam in cams]
                        cam_list.extend(cams)
                elif backend_lower == "mockdaheng":
                    MockDahengCamera = _get_mock_daheng_camera()
                    cams = MockDahengCamera.get_available_cameras()
                    cams = [f"{backend}:{cam}" for cam in cams]
                    cam_list.extend(cams)
                elif backend_lower == "mockbasler":
                    MockBaslerCamera = _get_mock_basler_camera()
                    cams = MockBaslerCamera.get_available_cameras()
                    cams = [f"{backend}:{cam}" for cam in cams]
                    cam_list.extend(cams)
                else:
                    self.logger.warning(f"Unknown backend: {backend}")
                    
            except Exception as e:
                self.logger.error(f"Backend discovery failed for '{backend}': {e}")
                
        return cam_list

    def setup_camera(
        self, 
        camera_name: str, 
        camera_config: Optional[str] = None, 
        img_quality_enhancement: bool = False, 
        retrieve_retry_count: int = 3
    ) -> BaseCamera:
        """
        Setup and initialize a camera instance.
        
        Args:
            camera_name: Camera name in format "Backend:camera_name"
            camera_config: Path to camera configuration file
            img_quality_enhancement: Whether to enable image quality enhancement
            retrieve_retry_count: Number of retry attempts for operations
            
        Returns:
            Initialized camera instance
            
        Raises:
            CameraConfigurationError: If camera name format is invalid
            CameraNotFoundError: If backend is not registered
            SDKNotAvailableError: If required SDK is not available
            CameraInitializationError: If camera setup fails
        """
        try:
            backend, actual_camera_name = camera_name.split(":", 1)
        except ValueError:
            raise CameraConfigurationError(
                f"Invalid camera name format: '{camera_name}'. Expected 'Backend:camera_name'"
            )
        
        if backend not in self.backends:
            raise CameraNotFoundError(
                f"Backend '{backend}' not registered. Available backends: {self.backends}"
            )
        
        backend_lower = backend.lower()
        
        try:
            if backend_lower == "daheng":
                available, DahengCamera = _get_daheng_backend()
                if not available or not DahengCamera:
                    raise SDKNotAvailableError(
                        "gxipy", 
                        self.get_installation_instructions("daheng")
                    )
                camera = DahengCamera(
                    actual_camera_name, camera_config, 
                    img_quality_enhancement, retrieve_retry_count
                )
                
            elif backend_lower == "basler":
                available, BaslerCamera = _get_basler_backend()
                if not available or not BaslerCamera:
                    raise SDKNotAvailableError(
                        "pypylon", 
                        self.get_installation_instructions("basler")
                    )
                camera = BaslerCamera(
                    actual_camera_name, camera_config, 
                    img_quality_enhancement, retrieve_retry_count
                )
                
            elif backend_lower == "opencv":
                available, OpenCVCamera = _get_opencv_backend()
                if not available or not OpenCVCamera:
                    raise SDKNotAvailableError(
                        "opencv-python", 
                        self.get_installation_instructions("opencv")
                    )
                camera = OpenCVCamera(
                    actual_camera_name, camera_config, 
                    img_quality_enhancement, retrieve_retry_count
                )
                
            elif backend_lower == "mockdaheng":
                MockDahengCamera = _get_mock_daheng_camera()
                camera = MockDahengCamera(
                    actual_camera_name, camera_config, 
                    img_quality_enhancement, retrieve_retry_count
                )
                
            elif backend_lower == "mockbasler":
                MockBaslerCamera = _get_mock_basler_camera()
                camera = MockBaslerCamera(
                    actual_camera_name, camera_config, 
                    img_quality_enhancement, retrieve_retry_count
                )
                
            else:
                raise CameraNotFoundError(f"Backend '{backend}' not supported")
                
            self.logger.info(f"Camera '{camera_name}' setup successfully")
            return camera
            
        except (SDKNotAvailableError, CameraInitializationError, CameraNotFoundError):
            raise
        except Exception as e:
            self.logger.error(f"Camera setup failed for '{camera_name}': {e}")
            raise CameraInitializationError(f"Failed to setup camera '{camera_name}': {e}")

    def get_camera(self, camera_name: str, **kwargs) -> BaseCamera:
        """
        Get a camera instance, creating it if it doesn't exist.
        
        Args:
            camera_name: Camera name in format "Backend:camera_name"
            **kwargs: Additional arguments for camera creation
            
        Returns:
            Camera instance
            
        Raises:
            CameraConfigurationError: If camera name format is invalid
            CameraNotFoundError: If backend is not registered
            CameraInitializationError: If camera creation fails
        """
        if camera_name in self.cameras:
            return self.cameras[camera_name]
        
        # Create new camera
        camera = self.setup_camera(camera_name, **kwargs)
        self.cameras[camera_name] = camera
        return camera

    async def remove_camera(self, camera_name: str) -> None:
        """
        Remove camera from managed cameras and clean up resources.
        
        Args:
            camera_name: Name of camera to remove
        """
        if camera_name in self.cameras:
            try:
                await self.cameras[camera_name].close()
                self.logger.info(f"Camera '{camera_name}' closed successfully")
            except Exception as e:
                self.logger.warning(f"Error closing camera '{camera_name}': {e}")
            finally:
                del self.cameras[camera_name]
            
        if camera_name in self.camera_locks:
            del self.camera_locks[camera_name]
            
        self.logger.info(f"Camera '{camera_name}' removed from manager")

    async def initialize_cameras(
        self, 
        camera_names: List[str], 
        camera_configs: Optional[List[str]] = None,
        img_quality_enhancement: bool = False,
        retrieve_retry_count: int = 3
    ) -> List[str]:
        """
        Initialize multiple cameras asynchronously.
        
        Args:
            camera_names: List of camera names to initialize
            camera_configs: List of camera config paths (optional)
            img_quality_enhancement: Whether to use image quality enhancement
            retrieve_retry_count: Number of retries for camera operations
            
        Returns:
            List of camera names that failed to initialize
            
        Raises:
            CameraConfigurationError: If input parameters are invalid
        """
        if not isinstance(camera_names, list):
            raise CameraConfigurationError("camera_names must be a list")
            
        not_initialized = []
        cameras_to_test_connection = []
        
        # Ensure camera_configs has same length as camera_names
        if camera_configs is None:
            camera_configs = []
        if len(camera_configs) != len(camera_names):
            camera_configs.extend(["" for _ in range(len(camera_names) - len(camera_configs))])

        # Create locks for all cameras first to prevent race conditions
        for camera_name in camera_names:
            if camera_name not in self.camera_locks:
                self.camera_locks[camera_name] = asyncio.Lock()

        for camera_name, camera_config in zip(camera_names, camera_configs):
            initialized = False
            
            try:
                backend, actual_camera_name = camera_name.split(":", 1)
            except ValueError:
                self.logger.error(f"Invalid camera name format: '{camera_name}'")
                not_initialized.append(camera_name)
                continue
            
            if backend not in self.backends:
                self.logger.error(f"Backend '{backend}' not registered for camera '{camera_name}'")
                not_initialized.append(camera_name)
                continue
            
            # Acquire lock for this camera to prevent parallel initialization
            async with self.camera_locks[camera_name]:
                if camera_name not in self.cameras:
                    try:
                        camera = self.setup_camera(
                            camera_name, 
                            camera_config if camera_config else None, 
                            img_quality_enhancement, 
                            retrieve_retry_count
                        )
                        self.cameras[camera_name] = camera
                        
                        # Now call async initialize method
                        success, camera_obj, device_manager = await camera.initialize()
                        if success:
                            cameras_to_test_connection.append(camera_name)
                            initialized = True
                            self.logger.info(f"Camera '{camera_name}' initialized successfully")
                        else:
                            self.logger.warning(f"Camera '{camera_name}' initialization failed")
                            await self.remove_camera(camera_name)
                            initialized = False
                            
                    except Exception as e:
                        self.logger.error(f"Camera setup error for '{camera_name}': {e}")
                        await self.remove_camera(camera_name)
                        initialized = False
                else:
                    initialized = True
                    self.logger.debug(f"Camera '{camera_name}' already initialized")
            
            if not initialized:
                not_initialized.append(camera_name)
        
        # Test connection for newly initialized cameras
        for cam in cameras_to_test_connection:
            async with self.camera_locks[cam]:
                try:
                    status = await self.cameras[cam].check_connection()
                    if not status:
                        self.logger.warning(f"Connection test failed for camera '{cam}'")
                        not_initialized.append(cam)
                        await self.remove_camera(cam)
                except Exception as e:
                    self.logger.error(f"Connection test error for camera '{cam}': {e}")
                    not_initialized.append(cam)
                    await self.remove_camera(cam)
                    
        if not_initialized:
            self.logger.warning(f"Failed to initialize cameras: {not_initialized}")
        else:
            self.logger.info(f"All cameras initialized successfully: {camera_names}")
            
        return not_initialized

    async def capture(self, camera_name: str, save_path: Optional[str] = None):
        """
        Capture image from specified camera.
        
        Args:
            camera_name: Name of camera to capture from
            save_path: Optional path to save captured image
            
        Returns:
            Captured image as numpy array
            
        Raises:
            CameraNotFoundError: If camera not found or not initialized
            CameraCaptureError: If capture operation fails
            CameraTimeoutError: If capture times out
        """
        if camera_name not in self.cameras:
            raise CameraNotFoundError(
                f"Camera '{camera_name}' not initialized. Available cameras: {list(self.cameras.keys())}"
            )
            
        try:
            async with self.camera_locks[camera_name]:
                # Direct async call - all cameras are now async
                status, img = await self.cameras[camera_name].capture()
                
                if not status or img is None:
                    raise CameraCaptureError(f"Camera '{camera_name}' failed to capture image")
                
                if save_path is not None:
                    base_path = os.path.dirname(save_path)
                    if base_path:
                        os.makedirs(base_path, mode=0o755, exist_ok=True)
                    
                    success = await asyncio.to_thread(cv2.imwrite, save_path, img)
                    if not success:
                        raise CameraCaptureError(f"Failed to save image to '{save_path}'")
                    self.logger.info(f"Image saved to '{save_path}' from camera '{camera_name}'")
                
                self.logger.debug(f"Image captured successfully from camera '{camera_name}'")
                return img
                
        except (CameraNotFoundError, CameraCaptureError):
            raise
        except asyncio.TimeoutError:
            raise CameraTimeoutError(f"Capture timeout for camera '{camera_name}'")
        except Exception as e:
            self.logger.error(f"Capture failed for camera '{camera_name}': {e}")
            raise CameraCaptureError(f"Failed to capture image from '{camera_name}': {e}")

    async def set_config(self, camera_name: str, config: str) -> None:
        """
        Set camera configuration.
        
        Args:
            camera_name: Name of camera to configure
            config: Configuration string or path
            
        Raises:
            CameraNotFoundError: If camera not found
            CameraConfigurationError: If configuration fails
        """
        if camera_name not in self.cameras:
            raise CameraNotFoundError(f"Camera '{camera_name}' not initialized")
            
        try:
            async with self.camera_locks[camera_name]:
                success = await self.cameras[camera_name].set_config(config)
                if not success:
                    raise CameraConfigurationError(f"Failed to set config for '{camera_name}'")
                self.logger.info(f"Configuration set for camera '{camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Configuration failed for camera '{camera_name}': {e}")
            raise CameraConfigurationError(f"Failed to configure camera '{camera_name}': {e}")

    async def export_config(self, camera_name: str, config_path: str) -> None:
        """
        Export camera configuration to file.
        
        Args:
            camera_name: Name of camera to export config from
            config_path: Path to save configuration file
            
        Raises:
            CameraNotFoundError: If camera not found
            CameraConfigurationError: If export fails
        """
        if camera_name not in self.cameras:
            raise CameraNotFoundError(f"Camera '{camera_name}' not initialized")
            
        try:
            async with self.camera_locks[camera_name]:
                success = await self.cameras[camera_name].export_config(config_path)
                if not success:
                    raise CameraConfigurationError(f"Failed to export config for '{camera_name}'")
                self.logger.info(f"Configuration exported for camera '{camera_name}' to '{config_path}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Config export failed for camera '{camera_name}': {e}")
            raise CameraConfigurationError(f"Failed to export config for '{camera_name}': {e}")

    async def get_exposure_range(self, camera_name: str) -> Dict[str, float]:
        """
        Get camera exposure range.
        
        Args:
            camera_name: Name of camera
            
        Returns:
            Dictionary with 'min' and 'max' exposure values
            
        Raises:
            CameraNotFoundError: If camera not found
        """
        if camera_name not in self.cameras:
            raise CameraNotFoundError(f"Camera '{camera_name}' not initialized")
            
        try:
            exposure_range = await self.cameras[camera_name].get_exposure_range()
            return {"min": exposure_range[0], "max": exposure_range[1]}
        except Exception as e:
            self.logger.debug(f"Failed to get exposure range for camera '{camera_name}': {e}")
            raise CameraError(f"Failed to get exposure range for '{camera_name}': {e}")

    async def get_exposure(self, camera_name: str) -> float:
        """
        Get current camera exposure.
        
        Args:
            camera_name: Name of camera
            
        Returns:
            Current exposure value
            
        Raises:
            CameraNotFoundError: If camera not found
        """
        if camera_name not in self.cameras:
            raise CameraNotFoundError(f"Camera '{camera_name}' not initialized")
            
        try:
            return await self.cameras[camera_name].get_exposure()
        except Exception as e:
            self.logger.error(f"Failed to get exposure for camera '{camera_name}': {e}")
            raise CameraError(f"Failed to get exposure for '{camera_name}': {e}")

    async def set_exposure(self, camera_name: str, exposure: float) -> None:
        """
        Set camera exposure.
        
        Args:
            camera_name: Name of camera
            exposure: Exposure value to set
            
        Raises:
            CameraNotFoundError: If camera not found
            CameraConfigurationError: If exposure setting fails
        """
        if camera_name not in self.cameras:
            raise CameraNotFoundError(f"Camera '{camera_name}' not initialized")
            
        try:
            async with self.camera_locks[camera_name]:
                success = await self.cameras[camera_name].set_exposure(exposure)
                if not success:
                    raise CameraConfigurationError(f"Failed to set exposure for '{camera_name}'")
                self.logger.info(f"Exposure set to {exposure} for camera '{camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set exposure for camera '{camera_name}': {e}")
            raise CameraConfigurationError(f"Failed to set exposure for '{camera_name}': {e}")

    async def de_initialize_cameras(self, camera_names: List[str]) -> bool:
        """
        De-initialize and clean up multiple cameras.
        
        Args:
            camera_names: List of camera names to de-initialize
            
        Returns:
            True if all cameras de-initialized successfully, False otherwise
        """
        success = True
        
        for camera_name in camera_names:
            try:
                if camera_name in self.cameras:
                    await self.remove_camera(camera_name)
            except Exception as e:
                self.logger.error(f"Failed to de-initialize camera '{camera_name}': {e}")
                success = False
                
        if success:
            self.logger.info(f"All cameras de-initialized successfully: {camera_names}")
        else:
            self.logger.warning(f"Some cameras failed to de-initialize: {camera_names}")
            
        return success

    async def get_wb(self, camera_name: str) -> str:
        """
        Get camera white balance setting.
        
        Args:
            camera_name: Name of camera
            
        Returns:
            Current white balance setting
            
        Raises:
            CameraNotFoundError: If camera not found
        """
        if camera_name not in self.cameras:
            raise CameraNotFoundError(f"Camera '{camera_name}' not initialized")
            
        try:
            return await self.cameras[camera_name].get_wb()
        except Exception as e:
            self.logger.error(f"Failed to get white balance for camera '{camera_name}': {e}")
            raise CameraError(f"Failed to get white balance for '{camera_name}': {e}")

    async def set_wb_once(self, camera_name: str, wb: str) -> None:
        """
        Set camera white balance.
        
        Args:
            camera_name: Name of camera
            wb: White balance setting
            
        Raises:
            CameraNotFoundError: If camera not found
            CameraConfigurationError: If white balance setting fails
        """
        if camera_name not in self.cameras:
            raise CameraNotFoundError(f"Camera '{camera_name}' not initialized")
            
        try:
            async with self.camera_locks[camera_name]:
                success = await self.cameras[camera_name].set_auto_wb_once(wb)
                if not success:
                    raise CameraConfigurationError(f"Failed to set white balance for '{camera_name}'")
                self.logger.info(f"White balance set to '{wb}' for camera '{camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.debug(f"Failed to set white balance for camera '{camera_name}': {e}")
            raise CameraConfigurationError(f"Failed to set white balance for '{camera_name}': {e}")

    def __del__(self):
        """
        Cleanup when camera manager is destroyed.
        
        Ensures all cameras are properly closed and resources are freed.
        """
        try:
            if hasattr(self, 'cameras') and self.cameras:
                camera_names = list(self.cameras.keys())
                for camera_name in camera_names:
                    try:
                        if camera_name in self.cameras:
                            try:
                                # Try async close if possible
                                import inspect
                                if inspect.iscoroutinefunction(self.cameras[camera_name].close):
                                    # This is an async close - need to run in event loop
                                    try:
                                        loop = asyncio.get_event_loop()
                                        if loop.is_running():
                                            # Schedule the async close
                                            loop.create_task(self.cameras[camera_name].close())
                                        else:
                                            loop.run_until_complete(self.cameras[camera_name].close())
                                    except RuntimeError:
                                        # No event loop available, fallback to sync warning
                                        self.logger.warning(f"Cannot properly close async camera '{camera_name}' in destructor")
                                else:
                                    # Sync close
                                    self.cameras[camera_name].close()
                            except Exception:
                                pass  # Ignore errors during shutdown
                    except Exception:
                        pass  # Ignore errors during shutdown
                self.cameras.clear()
                
            if hasattr(self, 'camera_locks'):
                self.camera_locks.clear()
                
        except Exception:
            pass  # Ignore all errors during shutdown

