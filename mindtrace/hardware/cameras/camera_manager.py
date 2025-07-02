"""
Modern Camera Manager for Mindtrace Hardware System

A clean, intuitive camera management system that provides unified access to
multiple camera backends with async operations and proper resource management.

Key Features:
    - Automatic backend discovery and lazy loading
    - Clean async API with context manager support  
    - Unified camera proxy interface
    - Thread-safe operations with proper locking
    - Comprehensive configuration management
    - Integrated error handling

Supported Backends:
    - Daheng: Industrial cameras (gxipy SDK)
    - Basler: Industrial cameras (pypylon SDK)  
    - OpenCV: USB cameras and webcams
    - Mock backends for testing

Usage:
    # Simple usage
    async with CameraManager() as manager:
        cameras = manager.discover_cameras()
        camera = await manager.get_camera(cameras[0])
        image = await camera.capture()
    
    # With configuration
    async with CameraManager(include_mocks=True) as manager:
        camera = await manager.get_camera("MockDaheng:test_camera")
        await camera.configure(exposure=20000, gain=2.5)
        image = await camera.capture("output.jpg")
"""

import os
import asyncio
from typing import Dict, List, Optional, Any, Tuple, Union
import cv2

from mindtrace.hardware.cameras.backends.base import BaseCamera
from mindtrace.core.base.mindtrace_base import Mindtrace
from mindtrace.hardware.core.exceptions import (
    CameraError, CameraNotFoundError, CameraInitializationError,
    CameraCaptureError, CameraConfigurationError, CameraConnectionError,
    SDKNotAvailableError, CameraTimeoutError
)

# Backend discovery and lazy loading
_backend_cache = {
    "daheng": {"checked": False, "available": False, "class": None},
    "basler": {"checked": False, "available": False, "class": None},
    "opencv": {"checked": False, "available": False, "class": None}
}


def _discover_backend(backend_name: str, logger=None) -> Tuple[bool, Optional[Any]]:
    """Discover and cache backend availability."""
    cache_key = backend_name.lower()
    if cache_key not in _backend_cache:
        return False, None
    
    cache = _backend_cache[cache_key]
    if cache["checked"]:
        return cache["available"], cache["class"]
    
    try:
        if cache_key == "daheng":
            from mindtrace.hardware.cameras.backends.daheng import DahengCamera, DAHENG_AVAILABLE
            cache["available"] = DAHENG_AVAILABLE
            cache["class"] = DahengCamera if DAHENG_AVAILABLE else None
        
        elif cache_key == "basler":
            from mindtrace.hardware.cameras.backends.basler import BaslerCamera, BASLER_AVAILABLE
            cache["available"] = BASLER_AVAILABLE
            cache["class"] = BaslerCamera if BASLER_AVAILABLE else None
        
        elif cache_key == "opencv":
            from mindtrace.hardware.cameras.backends.opencv import OpenCVCamera, OPENCV_AVAILABLE
            cache["available"] = OPENCV_AVAILABLE
            cache["class"] = OpenCVCamera if OPENCV_AVAILABLE else None
        
        if logger and cache["available"]:
            logger.debug(f"{backend_name} backend loaded successfully")
    
    except ImportError as e:
        cache["available"] = False
        cache["class"] = None
        if logger:
            logger.debug(f"{backend_name} backend not available: {e}")
    
    finally:
        cache["checked"] = True
    
    return cache["available"], cache["class"]


def _get_mock_camera(backend_name: str):
    """Get mock camera class for backend."""
    try:
        if backend_name.lower() == "daheng":
            from mindtrace.hardware.cameras.backends.daheng.mock_daheng import MockDahengCamera
            return MockDahengCamera
        elif backend_name.lower() == "basler":
            from mindtrace.hardware.cameras.backends.basler.mock_basler import MockBaslerCamera
            return MockBaslerCamera
        else:
            raise CameraInitializationError(f"Mock backend not available for {backend_name}")
    except ImportError as e:
        raise CameraInitializationError(f"Mock {backend_name} backend not available: {e}")


class CameraProxy:
    """
    Unified camera interface that wraps backend-specific camera instances.
    
    Provides a clean, consistent API regardless of the underlying camera backend
    while maintaining thread-safe operations through internal locking.
    """
    
    def __init__(self, camera: BaseCamera, full_name: str):
        self._camera = camera
        self._full_name = full_name
        self._lock = asyncio.Lock()
        
        # Parse backend and device name
        parts = full_name.split(":", 1)
        self._backend = parts[0]
        self._device_name = parts[1] if len(parts) > 1 else full_name
    
    @property
    def name(self) -> str:
        """Full camera name (Backend:device)."""
        return self._full_name
    
    @property
    def backend(self) -> str:
        """Backend name."""
        return self._backend
    
    @property
    def device_name(self) -> str:
        """Device name without backend prefix."""
        return self._device_name
    
    @property
    def is_connected(self) -> bool:
        """Check if camera is initialized and connected."""
        return self._camera.initialized
    
    # Core Operations
    async def capture(self, save_path: Optional[str] = None) -> Any:
        """
        Capture image from camera with advanced retry logic.
        
        This method uses sophisticated retry logic with exponential backoff
        to handle different types of errors appropriately:
        - Capture errors: Fast retry (0.1s base delay)
        - Connection errors: Slower retry (0.5s base delay)
        - Timeout errors: Moderate retry (0.3s base delay)
        
        Args:
            save_path: Optional path to save image
            
        Returns:
            Captured image as numpy array
            
        Raises:
            CameraCaptureError: If capture fails after all retries
            CameraConnectionError: If connection fails after all retries
            CameraTimeoutError: If timeout occurs after all retries
        """
        async with self._lock:
            # Get retry count from the camera
            retry_count = self._camera.retrieve_retry_count
            
            for attempt in range(retry_count):
                try:
                    # Call the actual capture method
                    success, image = await self._camera.capture()
                    
                    if success and image is not None:
                        # Save image if path provided
                        if save_path:
                            os.makedirs(os.path.dirname(save_path), exist_ok=True)
                            cv2.imwrite(save_path, image)
                        return image
                    else:
                        # Capture returned False or None - treat as capture error
                        raise CameraCaptureError(f"Capture returned failure for camera '{self._full_name}'")
                        
                except CameraCaptureError as e:
                    # Fast retry for capture-specific errors (e.g., buffer issues, timing)
                    delay = 0.1 * (2 ** attempt)
                    self._camera.logger.warning(
                        f"Capture retry {attempt + 1}/{retry_count} for camera '{self._full_name}': {e}"
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(delay)
                    else:
                        self._camera.logger.error(f"Capture failed after {retry_count} attempts for camera '{self._full_name}': {e}")
                        raise CameraCaptureError(f"Capture failed after {retry_count} attempts for camera '{self._full_name}': {e}")
                        
                except CameraConnectionError as e:
                    # Slower retry for network/connection issues (e.g., GigE camera network glitches)
                    delay = 0.5 * (2 ** attempt)
                    self._camera.logger.warning(
                        f"Network retry {attempt + 1}/{retry_count} for camera '{self._full_name}': {e}"
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(delay)
                    else:
                        self._camera.logger.error(f"Connection failed after {retry_count} attempts for camera '{self._full_name}': {e}")
                        raise CameraConnectionError(f"Connection failed after {retry_count} attempts for camera '{self._full_name}': {e}")
                        
                except CameraTimeoutError as e:
                    # Moderate retry for timeout issues
                    delay = 0.3 * (2 ** attempt)
                    self._camera.logger.warning(
                        f"Timeout retry {attempt + 1}/{retry_count} for camera '{self._full_name}': {e}"
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(delay)
                    else:
                        self._camera.logger.error(f"Timeout failed after {retry_count} attempts for camera '{self._full_name}': {e}")
                        raise CameraTimeoutError(f"Timeout failed after {retry_count} attempts for camera '{self._full_name}': {e}")
                        
                except (CameraNotFoundError, CameraInitializationError, CameraConfigurationError) as e:
                    # These errors are not retryable - fail immediately
                    self._camera.logger.error(f"Non-retryable error for camera '{self._full_name}': {e}")
                    raise
                    
                except Exception as e:
                    # Unexpected errors - log and retry with moderate delay
                    delay = 0.2 * (2 ** attempt)
                    self._camera.logger.warning(
                        f"Unexpected error retry {attempt + 1}/{retry_count} for camera '{self._full_name}': {e}"
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(delay)
                    else:
                        self._camera.logger.error(f"Unexpected error failed after {retry_count} attempts for camera '{self._full_name}': {e}")
                        raise RuntimeError(f"Failed to capture image from camera '{self._full_name}' after {retry_count} attempts: {e}")
            
            # This should never be reached, but just in case
            raise RuntimeError(f"Failed to capture image from camera '{self._full_name}' after {retry_count} attempts")
    
    async def configure(self, **settings) -> bool:
        """
        Configure multiple camera settings at once.
        
        Args:
            exposure: Exposure time in microseconds
            gain: Gain value
            roi: ROI as (x, y, width, height) tuple
            trigger_mode: "continuous" or "trigger"
            pixel_format: Pixel format string  
            white_balance: White balance mode
            image_enhancement: Enable/disable enhancement
            
        Returns:
            True if all settings applied successfully
        """
        async with self._lock:
            success = True
            
            if "exposure" in settings:
                success &= await self._camera.set_exposure(settings["exposure"])
            
            if "gain" in settings:
                success &= self._camera.set_gain(settings["gain"])
            
            if "roi" in settings:
                x, y, w, h = settings["roi"]
                success &= self._camera.set_ROI(x, y, w, h)
            
            if "trigger_mode" in settings:
                success &= await self._camera.set_triggermode(settings["trigger_mode"])
            
            if "pixel_format" in settings:
                success &= self._camera.set_pixel_format(settings["pixel_format"])
            
            if "white_balance" in settings:
                success &= await self._camera.set_auto_wb_once(settings["white_balance"])
            
            if "image_enhancement" in settings:
                success &= self._camera.set_image_quality_enhancement(settings["image_enhancement"])
            
            return success
    
    # Exposure Control
    async def set_exposure(self, exposure: Union[int, float]) -> bool:
        """Set exposure time in microseconds."""
        async with self._lock:
            return await self._camera.set_exposure(exposure)
    
    async def get_exposure(self) -> float:
        """Get current exposure time."""
        return await self._camera.get_exposure()
    
    async def get_exposure_range(self) -> Tuple[float, float]:
        """Get exposure range as (min, max)."""
        range_list = await self._camera.get_exposure_range()
        return range_list[0], range_list[1]
    
    # Gain Control
    def set_gain(self, gain: Union[int, float]) -> bool:
        """Set camera gain."""
        return self._camera.set_gain(gain)
    
    def get_gain(self) -> float:
        """Get current gain."""
        return self._camera.get_gain()
    
    def get_gain_range(self) -> Tuple[float, float]:
        """Get gain range as (min, max)."""
        range_list = self._camera.get_gain_range()
        return range_list[0], range_list[1]
    
    # ROI Control
    def set_roi(self, x: int, y: int, width: int, height: int) -> bool:
        """Set Region of Interest."""
        return self._camera.set_ROI(x, y, width, height)
    
    def get_roi(self) -> Dict[str, int]:
        """Get current ROI settings."""
        return self._camera.get_ROI()
    
    def reset_roi(self) -> bool:
        """Reset ROI to full sensor."""
        return self._camera.reset_ROI()
    
    # Trigger Control  
    async def set_trigger_mode(self, mode: str) -> bool:
        """Set trigger mode ('continuous' or 'trigger')."""
        async with self._lock:
            return await self._camera.set_triggermode(mode)
    
    async def get_trigger_mode(self) -> str:
        """Get current trigger mode."""
        return await self._camera.get_triggermode()
    
    # Pixel Format
    def set_pixel_format(self, format: str) -> bool:
        """Set pixel format."""
        return self._camera.set_pixel_format(format)
    
    def get_pixel_format(self) -> str:
        """Get current pixel format."""
        return self._camera.get_current_pixel_format()
    
    def get_available_pixel_formats(self) -> List[str]:
        """Get available pixel formats."""
        return self._camera.get_pixel_format_range()
    
    # White Balance
    async def set_white_balance(self, mode: str) -> bool:
        """Set white balance mode."""
        async with self._lock:
            return await self._camera.set_auto_wb_once(mode)
    
    async def get_white_balance(self) -> str:
        """Get current white balance mode."""
        return await self._camera.get_wb()
    
    def get_available_white_balance_modes(self) -> List[str]:
        """Get available white balance modes."""
        return self._camera.get_wb_range()
    
    # Image Enhancement
    def set_image_enhancement(self, enabled: bool) -> bool:
        """Enable/disable image enhancement."""
        return self._camera.set_image_quality_enhancement(enabled)
    
    def get_image_enhancement(self) -> bool:
        """Get image enhancement status."""
        return self._camera.get_image_quality_enhancement()
    
    # Configuration Management
    async def save_config(self, path: str) -> bool:
        """Save camera configuration to file."""
        async with self._lock:
            return await self._camera.export_config(path)
    
    async def load_config(self, path: str) -> bool:
        """Load camera configuration from file."""
        async with self._lock:
            return await self._camera.import_config(path)
    
    # Status and Info
    async def check_connection(self) -> bool:
        """Check if camera is connected and responding."""
        return await self._camera.check_connection()
    
    async def get_sensor_info(self) -> Dict[str, Any]:
        """
        Get sensor information and capabilities.
        
        Returns:
            Dictionary with sensor information
        """
        # This would need to be implemented per backend
        # For now, return basic info
        return {
            "name": self._full_name,
            "backend": self._backend,
            "device_name": self._device_name,
            "connected": self.is_connected
        }
    
    async def capture_hdr(
        self, 
        save_path_pattern: Optional[str] = None,
        exposure_levels: int = 3,
        exposure_multiplier: float = 2.0,
        return_images: bool = True
    ) -> Union[List[Any], bool]:
        """
        Capture HDR (High Dynamic Range) images with multiple exposure levels.
        
        This method captures multiple images at different exposure levels to create
        HDR imagery. It temporarily modifies the camera's exposure settings and
        restores the original exposure when complete.
        
        Args:
            save_path_pattern: Optional path pattern for saving images. Use {} for exposure placeholder.
                              Example: "hdr_image_{}.jpg" will save as "hdr_image_1000.jpg", etc.
            exposure_levels: Number of different exposure levels to capture (default: 3)
            exposure_multiplier: Multiplier between exposure levels (default: 2.0)
            return_images: Whether to return the captured images (default: True)
            
        Returns:
            If return_images=True: List of captured images as numpy arrays
            If return_images=False: True if all captures successful, False otherwise
            
        Raises:
            CameraCaptureError: If HDR capture fails
            CameraConnectionError: If camera connection fails
            CameraConfigurationError: If exposure settings are invalid
            
        Example:
            # Capture 5 exposure levels with 1.5x multiplier
            images = await camera.capture_hdr(
                save_path_pattern="hdr_{}.jpg",
                exposure_levels=5,
                exposure_multiplier=1.5
            )
            
            # Just capture without returning images
            success = await camera.capture_hdr(
                save_path_pattern="hdr_{}.jpg",
                return_images=False
            )
        """
        async with self._lock:
            try:
                # Get current exposure to restore later
                original_exposure = await self._camera.get_exposure()
                
                # Get exposure range to validate settings
                exposure_range = await self._camera.get_exposure_range()
                min_exposure, max_exposure = exposure_range[0], exposure_range[1]
                
                # Calculate exposure levels
                # Use geometric progression centered around current exposure
                base_exposure = original_exposure
                
                # Create exposure levels: under-exposed, normal, over-exposed, etc.
                exposures = []
                for i in range(exposure_levels):
                    # Center the progression around the middle index
                    center_index = (exposure_levels - 1) / 2
                    multiplier = exposure_multiplier ** (i - center_index)
                    exposure = base_exposure * multiplier
                    
                    # Clamp to valid range
                    exposure = max(min_exposure, min(max_exposure, exposure))
                    exposures.append(exposure)
                
                # Remove duplicates and sort
                exposures = sorted(list(set(exposures)))
                
                self._camera.logger.info(
                    f"Starting HDR capture for camera '{self._full_name}' with {len(exposures)} exposure levels: {exposures}"
                )
                
                captured_images = []
                successful_captures = 0
                
                for i, exposure in enumerate(exposures):
                    try:
                        # Set exposure for this capture
                        success = await self._camera.set_exposure(exposure)
                        if not success:
                            self._camera.logger.warning(
                                f"Failed to set exposure {exposure} for HDR capture {i+1}/{len(exposures)}"
                            )
                            continue
                        
                        # Small delay to let exposure settle
                        await asyncio.sleep(0.1)
                        
                        # Capture image
                        save_path = None
                        if save_path_pattern:
                            save_path = save_path_pattern.format(exposure=int(exposure))
                        
                        # Call the underlying camera's capture method directly to avoid deadlock
                        success, image = await self._camera.capture()
                        
                        if success and image is not None:
                            # Save image if path provided
                            if save_path and save_path.strip():
                                save_dir = os.path.dirname(save_path)
                                if save_dir:  # Only create directory if it's not empty
                                    os.makedirs(save_dir, exist_ok=True)
                                cv2.imwrite(save_path, image)
                            
                            if return_images:
                                captured_images.append(image)
                            successful_captures += 1
                            
                            self._camera.logger.debug(
                                f"HDR capture {i+1}/{len(exposures)} successful at exposure {exposure}μs"
                            )
                        else:
                            self._camera.logger.warning(
                                f"HDR capture {i+1}/{len(exposures)} failed at exposure {exposure}μs"
                            )
                            
                    except Exception as e:
                        self._camera.logger.warning(
                            f"HDR capture {i+1}/{len(exposures)} failed at exposure {exposure}μs: {e}"
                        )
                        continue
                
                # Restore original exposure
                try:
                    await self._camera.set_exposure(original_exposure)
                    self._camera.logger.debug(f"Restored original exposure {original_exposure}μs")
                except Exception as e:
                    self._camera.logger.warning(f"Failed to restore original exposure: {e}")
                
                # Check results
                if successful_captures == 0:
                    raise CameraCaptureError(f"HDR capture failed - no successful captures from camera '{self._full_name}'")
                
                if successful_captures < len(exposures):
                    self._camera.logger.warning(
                        f"HDR capture partially successful: {successful_captures}/{len(exposures)} captures succeeded"
                    )
                
                self._camera.logger.info(
                    f"HDR capture completed for camera '{self._full_name}': {successful_captures}/{len(exposures)} successful"
                )
                
                if return_images:
                    return captured_images
                else:
                    return successful_captures == len(exposures)
                    
            except (CameraCaptureError, CameraConnectionError, CameraConfigurationError):
                # Re-raise camera-specific errors
                raise
            except Exception as e:
                self._camera.logger.error(f"HDR capture failed for camera '{self._full_name}': {e}")
                raise CameraCaptureError(f"HDR capture failed for camera '{self._full_name}': {str(e)}")

    async def close(self):
        """Close camera and release resources."""
        await self._camera.close()


class CameraManager(Mindtrace):
    """
    Modern camera manager with clean API and automatic backend discovery.
    
    Provides unified access to multiple camera backends with proper resource
    management, async operations, and comprehensive error handling.
    """
    
    def __init__(self, include_mocks: bool = False):
        """
        Initialize camera manager.
        
        Args:
            include_mocks: Include mock cameras in discovery
        """
        super().__init__()
        
        self._cameras: Dict[str, CameraProxy] = {}
        self._include_mocks = include_mocks
        self._discovered_backends = self._discover_all_backends()
        
        self.logger.info(f"CameraManager initialized. Available backends: {self._discovered_backends}")
    
    def _discover_all_backends(self) -> List[str]:
        """Discover all available camera backends."""
        backends = []
        
        # Check hardware backends
        for backend_name in ["Daheng", "Basler", "OpenCV"]:
            available, _ = _discover_backend(backend_name, self.logger)
            if available:
                backends.append(backend_name)
        
        # Add mock backends if requested
        if self._include_mocks:
            backends.extend(["MockDaheng", "MockBasler"])
        
        return backends
    
    def get_available_backends(self) -> List[str]:
        """Get list of available backend names."""
        return self._discovered_backends.copy()
    
    def get_backend_info(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed information about all backends."""
        info = {}
        
        for backend in ["Daheng", "Basler", "OpenCV"]:
            available, _ = _discover_backend(backend.lower())
            info[backend] = {
                "available": available,
                "type": "hardware",
                "sdk_required": True
            }
        
        if self._include_mocks:
            info["MockDaheng"] = {"available": True, "type": "mock", "sdk_required": False}
            info["MockBasler"] = {"available": True, "type": "mock", "sdk_required": False}
        
        return info
    
    def discover_cameras(self) -> List[str]:
        """
        Discover all available cameras across all backends.
        
        Returns:
            List of camera names in format "Backend:device_name"
        """
        all_cameras = []
        
        for backend in self._discovered_backends:
            try:
                if backend in ["Daheng", "Basler", "OpenCV"]:
                    available, camera_class = _discover_backend(backend.lower())
                    if available and camera_class:
                        cameras = camera_class.get_available_cameras()
                        all_cameras.extend([f"{backend}:{cam}" for cam in cameras])
                
                elif backend.startswith("Mock"):
                    backend_name = backend.replace("Mock", "").lower()
                    mock_class = _get_mock_camera(backend_name)
                    cameras = mock_class.get_available_cameras()
                    all_cameras.extend([f"{backend}:{cam}" for cam in cameras])
            
            except Exception as e:
                self.logger.error(f"Camera discovery failed for {backend}: {e}")
        
        return all_cameras
    
    def _parse_camera_name(self, camera_name: str) -> Tuple[str, str]:
        """Parse full camera name into backend and device name."""
        if ":" not in camera_name:
            raise CameraConfigurationError(
                f"Invalid camera name format: '{camera_name}'. Expected 'Backend:device_name'"
            )
        
        backend, device_name = camera_name.split(":", 1)
        return backend, device_name
    
    def _create_camera_instance(self, backend: str, device_name: str, **kwargs) -> BaseCamera:
        """Create camera instance for specified backend."""
        if backend not in self._discovered_backends:
            raise CameraNotFoundError(f"Backend '{backend}' not available")
        
        try:
            if backend in ["Daheng", "Basler", "OpenCV"]:
                available, camera_class = _discover_backend(backend.lower())
                if not available or not camera_class:
                    raise CameraNotFoundError(f"Backend '{backend}' not available")
                return camera_class(device_name, **kwargs)
            
            elif backend.startswith("Mock"):
                backend_name = backend.replace("Mock", "").lower()
                mock_class = _get_mock_camera(backend_name)
                return mock_class(device_name, **kwargs)
            
            else:
                raise CameraNotFoundError(f"Unknown backend: {backend}")
        
        except Exception as e:
            raise CameraInitializationError(f"Failed to create camera '{backend}:{device_name}': {e}")
    
    async def initialize_camera(
        self, 
        camera_name: str, 
        test_connection: bool = True, 
        **kwargs
    ) -> None:
        """
        Initialize a single camera with optional connection testing.
        
        Args:
            camera_name: Full camera name "Backend:device_name"
            test_connection: Whether to test camera by capturing a test image
            **kwargs: Camera configuration parameters
            
        Raises:
            CameraInitializationError: If camera initialization fails
            CameraConnectionError: If connection test fails
            ValueError: If camera is already initialized
        """
        # Check if already initialized
        if camera_name in self._cameras:
            raise ValueError(f"Camera '{camera_name}' is already initialized")
        
        # Parse and validate camera name
        backend, device_name = self._parse_camera_name(camera_name)
        
        # Create camera instance
        camera = self._create_camera_instance(backend, device_name, **kwargs)
        
        # Initialize camera
        try:
            await camera.setup_camera()
        except Exception as e:
            raise CameraInitializationError(f"Failed to initialize camera '{camera_name}': {e}")
        
        # Test camera connection by attempting to capture
        if test_connection:
            self.logger.info(f"Testing connection for camera '{camera_name}'...")
            try:
                success = await camera.check_connection()
                if not success:
                    # Try actual capture as additional test
                    success, test_image = await camera.capture()
                    if not success or test_image is None:
                        await camera.close()  # Clean up before raising
                        raise CameraConnectionError(
                            f"Camera '{camera_name}' failed connection test - could not capture test image"
                        )
                
                self.logger.info(f"Camera '{camera_name}' passed connection test")
                
            except Exception as e:
                await camera.close()  # Clean up before raising
                if isinstance(e, CameraConnectionError):
                    raise
                raise CameraConnectionError(f"Camera '{camera_name}' connection test failed: {e}")
        
        # Create proxy and store
        proxy = CameraProxy(camera, camera_name)
        self._cameras[camera_name] = proxy
        
        self.logger.info(f"Camera '{camera_name}' initialized successfully")
    
    async def initialize_cameras(
        self, 
        camera_names: List[str], 
        test_connections: bool = True,
        **kwargs
    ) -> List[str]:
        """
        Initialize multiple cameras with optional connection testing.
        
        Args:
            camera_names: List of camera names to initialize
            test_connections: Whether to test camera connections
            **kwargs: Camera configuration parameters
            
        Returns:
            List of camera names that failed to initialize
        """
        failed_cameras = []
        
        self.logger.info(f"Initializing {len(camera_names)} cameras...")
        
        for camera_name in camera_names:
            try:
                # Skip if already initialized
                if camera_name in self._cameras:
                    self.logger.info(f"Camera '{camera_name}' already initialized")
                    continue
                
                # Initialize camera with connection testing
                await self.initialize_camera(camera_name, test_connection=test_connections, **kwargs)
                self.logger.info(f"Camera '{camera_name}' initialized successfully")
                
            except (CameraInitializationError, CameraConnectionError, ValueError) as e:
                self.logger.error(f"Failed to initialize camera '{camera_name}': {e}")
                failed_cameras.append(camera_name)
                
                # Clean up any partial initialization
                if camera_name in self._cameras:
                    try:
                        await self.close_camera(camera_name)
                    except Exception:
                        pass  # Already failed, ignore cleanup errors
                        
            except Exception as e:
                self.logger.error(f"Unexpected error initializing camera '{camera_name}': {e}")
                failed_cameras.append(camera_name)
        
        if failed_cameras:
            self.logger.warning(f"Failed to initialize cameras: {failed_cameras}")
        else:
            self.logger.info("All cameras initialized successfully")
            
        return failed_cameras

    def get_camera(self, camera_name: str) -> CameraProxy:
        """
        Get an initialized camera by name.
        
        Args:
            camera_name: Full camera name "Backend:device_name"
            
        Returns:
            CameraProxy instance
            
        Raises:
            KeyError: If camera is not initialized
        """
        if camera_name not in self._cameras:
            raise KeyError(f"Camera '{camera_name}' is not initialized. Use initialize_camera() first.")
        
        return self._cameras[camera_name]

    def get_cameras(self, camera_names: List[str]) -> Dict[str, CameraProxy]:
        """
        Get multiple initialized cameras by name.
        
        Args:
            camera_names: List of camera names to retrieve
            
        Returns:
            Dictionary mapping camera names to CameraProxy instances.
            Only includes successfully retrieved cameras.
        """
        cameras = {}
        
        for camera_name in camera_names:
            try:
                cameras[camera_name] = self.get_camera(camera_name)
            except KeyError as e:
                self.logger.warning(f"Could not retrieve camera '{camera_name}': {e}")
        
        return cameras

    def get_active_cameras(self) -> List[str]:
        """Get names of currently active cameras."""
        return list(self._cameras.keys())
    
    async def close_camera(self, camera_name: str) -> None:
        """Close and remove specific camera."""
        if camera_name in self._cameras:
            try:
                await self._cameras[camera_name].close()
                del self._cameras[camera_name]
                self.logger.info(f"Camera '{camera_name}' closed")
            except Exception as e:
                self.logger.error(f"Error closing camera '{camera_name}': {e}")
                raise
    
    async def close_all_cameras(self) -> None:
        """Close all active cameras."""
        for camera_name in list(self._cameras.keys()):
            try:
                await self.close_camera(camera_name)
            except Exception as e:
                self.logger.error(f"Error closing camera '{camera_name}': {e}")
    
    async def batch_configure(self, configurations: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """
        Configure multiple cameras simultaneously.
        
        Args:
            configurations: Dict mapping camera names to their settings
            
        Returns:
            Dict mapping camera names to success status
        """
        results = {}
        
        # Execute all configurations in parallel
        async def configure_camera(camera_name: str, settings: Dict[str, Any]) -> Tuple[str, bool]:
            try:
                camera = self.get_camera(camera_name)  # Now synchronous retrieval
                success = await camera.configure(**settings)
                return camera_name, success
            except Exception as e:
                self.logger.error(f"Configuration failed for '{camera_name}': {e}")
                return camera_name, False
        
        tasks = [
            configure_camera(name, settings) 
            for name, settings in configurations.items()
        ]
        
        config_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in config_results:
            if isinstance(result, Exception):
                self.logger.error(f"Configuration task failed: {result}")
            else:
                camera_name, success = result
                results[camera_name] = success
        
        return results
    
    async def batch_capture(self, camera_names: List[str]) -> Dict[str, Any]:
        """
        Capture from multiple cameras simultaneously.
        
        Args:
            camera_names: List of camera names to capture from
            
        Returns:
            Dict mapping camera names to captured images
        """
        results = {}
        
        async def capture_from_camera(camera_name: str) -> Tuple[str, Any]:
            try:
                camera = self.get_camera(camera_name)  # Now synchronous retrieval
                image = await camera.capture()
                return camera_name, image
            except Exception as e:
                self.logger.error(f"Capture failed for '{camera_name}': {e}")
                return camera_name, None
        
        tasks = [capture_from_camera(name) for name in camera_names]
        capture_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in capture_results:
            if isinstance(result, Exception):
                self.logger.error(f"Capture task failed: {result}")
            else:
                camera_name, image = result
                results[camera_name] = image
        
        return results
    
    async def batch_capture_hdr(
        self, 
        camera_names: List[str],
        save_path_pattern: Optional[str] = None,
        exposure_levels: int = 3,
        exposure_multiplier: float = 2.0,
        return_images: bool = True
    ) -> Dict[str, Union[List[Any], bool]]:
        """
        Capture HDR images from multiple cameras simultaneously.
        
        Args:
            camera_names: List of camera names to capture HDR from
            save_path_pattern: Optional path pattern. Use {camera} and {exposure} placeholders.
                              Example: "hdr_{camera}_{exposure}.jpg"
            exposure_levels: Number of different exposure levels to capture
            exposure_multiplier: Multiplier between exposure levels
            return_images: Whether to return the captured images
            
        Returns:
            Dict mapping camera names to HDR capture results
            
        Example:
            # Capture HDR from multiple cameras
            results = await manager.batch_capture_hdr(
                ["Daheng:cam1", "Basler:cam2"],
                save_path_pattern="hdr_{camera}_{exposure}.jpg",
                exposure_levels=5
            )
        """
        results = {}
        
        async def capture_hdr_from_camera(camera_name: str) -> Tuple[str, Union[List[Any], bool]]:
            try:
                camera = self.get_camera(camera_name)
                
                # Format save path for this camera
                camera_save_pattern = None
                if save_path_pattern:
                    # Replace {camera} placeholder with camera name (sanitized)
                    safe_camera_name = camera_name.replace(":", "_")
                    camera_save_pattern = save_path_pattern.replace("{camera}", safe_camera_name)
                
                result = await camera.capture_hdr(
                    save_path_pattern=camera_save_pattern,
                    exposure_levels=exposure_levels,
                    exposure_multiplier=exposure_multiplier,
                    return_images=return_images
                )
                return camera_name, result
            except Exception as e:
                self.logger.error(f"HDR capture failed for '{camera_name}': {e}")
                return camera_name, [] if return_images else False
        
        tasks = [capture_hdr_from_camera(name) for name in camera_names]
        hdr_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in hdr_results:
            if isinstance(result, Exception):
                self.logger.error(f"HDR capture task failed: {result}")
            else:
                camera_name, hdr_result = result
                results[camera_name] = hdr_result
        
        return results
    
    # Context manager support
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with proper cleanup."""
        await self.close_all_cameras()
    
    def __del__(self):
        """Destructor warning for improper cleanup."""
        if hasattr(self, '_cameras') and self._cameras:
            if hasattr(self, 'logger'):
                self.logger.warning(
                    f"CameraManager destroyed with {len(self._cameras)} active cameras. "
                    "Use 'async with CameraManager()' for proper cleanup."
                )


# Convenience functions for quick access
async def initialize_and_get_camera(camera_name: str, **kwargs) -> CameraProxy:
    """
    Quick access function to initialize and get a single camera.
    
    Args:
        camera_name: Camera name "Backend:device_name" 
        **kwargs: Camera configuration parameters
        
    Returns:
        CameraProxy instance
    """
    manager = CameraManager()
    await manager.initialize_camera(camera_name, **kwargs)
    return manager.get_camera(camera_name)


def discover_all_cameras(include_mocks: bool = False) -> List[str]:
    """
    Quick function to discover all cameras.
    
    Args:
        include_mocks: Include mock cameras in discovery
        
    Returns:
        List of available camera names
    """
    manager = CameraManager(include_mocks=include_mocks)
    return manager.discover_cameras() 