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
    async def capture(
        self, 
        save_path: Optional[str] = None,
        gcs_bucket: Optional[str] = None,
        gcs_path: Optional[str] = None,
        gcs_metadata: Optional[Dict[str, str]] = None
    ) -> Any:
        """
        Capture image from camera with advanced retry logic and optional GCS upload.
        
        This method uses sophisticated retry logic with exponential backoff
        to handle different types of errors appropriately:
        - Capture errors: Fast retry (0.1s base delay)
        - Connection errors: Slower retry (0.5s base delay)
        - Timeout errors: Moderate retry (0.3s base delay)
        
        Args:
            save_path: Optional path to save image locally
            gcs_bucket: Optional GCS bucket name for cloud storage
            gcs_path: Optional GCS path within bucket for cloud storage
            gcs_metadata: Optional metadata for GCS upload
            
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
                        # Save image locally if path provided
                        if save_path:
                            # Only create directory if the path contains a directory component
                            dirname = os.path.dirname(save_path)
                            if dirname:  # Only create directory if there is one
                                os.makedirs(dirname, exist_ok=True)
                            cv2.imwrite(save_path, image)
                        
                        # Upload to GCS if bucket and path provided, or if auto-upload is enabled
                        should_upload = False
                        gcs_uri = None
                        
                        try:
                            import tempfile
                            from datetime import datetime, UTC
                            from mindtrace.storage import GCSStorageHandler
                            from mindtrace.hardware.core.config import get_hardware_config
                            
                            # Get GCS configuration
                            config = get_hardware_config()
                            gcs_config = config.get_config().gcs
                            
                            should_upload = (gcs_bucket and gcs_path) or (gcs_config.auto_upload and gcs_config.default_bucket)
                            
                            if should_upload:
                                # Use provided bucket/path or default from config
                                upload_bucket = gcs_bucket or gcs_config.default_bucket
                                upload_path = gcs_path or f"auto_upload/{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{self._full_name.replace(':', '_')}.{gcs_config.default_image_format}"
                                
                                # Create GCS handler with configuration
                                gcs_handler = GCSStorageHandler(
                                    bucket_name=upload_bucket,
                                    project_id=gcs_config.project_id or None,
                                    credentials_path=gcs_config.credentials_path or None,
                                    create_if_missing=gcs_config.create_if_missing,
                                    location=gcs_config.location,
                                    storage_class=gcs_config.storage_class
                                )
                                
                                # Create temporary file with configured format
                                with tempfile.NamedTemporaryFile(suffix=f".{gcs_config.default_image_format}", delete=False) as temp_file:
                                    # Save image to temp file with configured quality
                                    if gcs_config.default_image_format.lower() == "jpg":
                                        encode_params = [cv2.IMWRITE_JPEG_QUALITY, gcs_config.default_image_quality]
                                    else:
                                        encode_params = []
                                    
                                    success, encoded_image = cv2.imencode(f".{gcs_config.default_image_format}", image, encode_params)
                                    if not success:
                                        raise ValueError(f"Failed to encode image as {gcs_config.default_image_format}")
                                    
                                    temp_file.write(encoded_image.tobytes())
                                    temp_path = temp_file.name
                                
                                try:
                                    # Prepare metadata
                                    upload_metadata = gcs_metadata or {}
                                    if gcs_config.upload_metadata:
                                        upload_metadata.update({
                                            "camera_name": self._full_name,
                                            "camera_backend": self._camera.__class__.__name__,
                                            "capture_timestamp": datetime.now(UTC).isoformat(),
                                            "upload_timestamp": datetime.now(UTC).isoformat(),
                                            "image_format": gcs_config.default_image_format,
                                            "image_shape": f"{image.shape[1]}x{image.shape[0]}",
                                            "image_channels": str(image.shape[2]) if len(image.shape) > 2 else "1"
                                        })
                                    
                                    # Upload to GCS
                                    gcs_uri = gcs_handler.upload(
                                        local_path=temp_path,
                                        remote_path=upload_path,
                                        metadata=upload_metadata
                                    )
                                    
                                    self._camera.logger.info(f"Image uploaded to GCS: {gcs_uri}")
                                    
                                finally:
                                    # Clean up temporary file
                                    if os.path.exists(temp_path):
                                        os.unlink(temp_path)
                                        
                        except Exception as e:
                            self._camera.logger.warning(f"Failed to upload image to GCS: {e}")
                            # Continue with capture even if GCS upload fails
                        
                        # Return both image and GCS URI if upload was successful
                        if should_upload:
                            return {
                                "image": image,
                                "gcs_uri": gcs_uri
                            }
                        else:
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
            results = {}
            failed_settings = []
            
            # Configure each setting independently
            if "exposure" in settings:
                try:
                    exposure_success = await self._camera.set_exposure(settings["exposure"])
                    results["exposure"] = exposure_success
                    if not exposure_success:
                        failed_settings.append(f"exposure={settings['exposure']}")
                except Exception as e:
                    self._camera.logger.error(f"Failed to set exposure {settings['exposure']}: {e}")
                    failed_settings.append(f"exposure={settings['exposure']} (error: {e})")
                    results["exposure"] = False
            
            if "gain" in settings:
                try:
                    gain_success = await self._camera.set_gain(settings["gain"])
                    results["gain"] = gain_success
                    if not gain_success:
                        failed_settings.append(f"gain={settings['gain']}")
                except Exception as e:
                    self._camera.logger.error(f"Failed to set gain {settings['gain']}: {e}")
                    failed_settings.append(f"gain={settings['gain']} (error: {e})")
                    results["gain"] = False
            
            if "roi" in settings:
                try:
                    x, y, w, h = settings["roi"]
                    roi_success = await self._camera.set_ROI(x, y, w, h)
                    results["roi"] = roi_success
                    if not roi_success:
                        failed_settings.append(f"roi=({x},{y},{w},{h})")
                except Exception as e:
                    self._camera.logger.error(f"Failed to set ROI {settings['roi']}: {e}")
                    failed_settings.append(f"roi={settings['roi']} (error: {e})")
                    results["roi"] = False
            
            if "trigger_mode" in settings:
                try:
                    trigger_success = await self._camera.set_triggermode(settings["trigger_mode"])
                    results["trigger_mode"] = trigger_success
                    if not trigger_success:
                        failed_settings.append(f"trigger_mode={settings['trigger_mode']}")
                except Exception as e:
                    self._camera.logger.error(f"Failed to set trigger_mode {settings['trigger_mode']}: {e}")
                    failed_settings.append(f"trigger_mode={settings['trigger_mode']} (error: {e})")
                    results["trigger_mode"] = False
            
            if "pixel_format" in settings:
                try:
                    pixel_success = await self._camera.set_pixel_format(settings["pixel_format"])
                    results["pixel_format"] = pixel_success
                    if not pixel_success:
                        failed_settings.append(f"pixel_format={settings['pixel_format']}")
                except Exception as e:
                    self._camera.logger.error(f"Failed to set pixel_format {settings['pixel_format']}: {e}")
                    failed_settings.append(f"pixel_format={settings['pixel_format']} (error: {e})")
                    results["pixel_format"] = False
            
            if "white_balance" in settings:
                try:
                    wb_success = await self._camera.set_auto_wb_once(settings["white_balance"])
                    results["white_balance"] = wb_success
                    if not wb_success:
                        failed_settings.append(f"white_balance={settings['white_balance']}")
                except Exception as e:
                    self._camera.logger.error(f"Failed to set white_balance {settings['white_balance']}: {e}")
                    failed_settings.append(f"white_balance={settings['white_balance']} (error: {e})")
                    results["white_balance"] = False
            
            if "image_enhancement" in settings:
                try:
                    enhancement_success = await self._camera.set_image_quality_enhancement(settings["image_enhancement"])
                    results["image_enhancement"] = enhancement_success
                    if not enhancement_success:
                        failed_settings.append(f"image_enhancement={settings['image_enhancement']}")
                except Exception as e:
                    self._camera.logger.error(f"Failed to set image_enhancement {settings['image_enhancement']}: {e}")
                    failed_settings.append(f"image_enhancement={settings['image_enhancement']} (error: {e})")
                    results["image_enhancement"] = False
            
            # Log results
            if failed_settings:
                self._camera.logger.warning(f"Configuration partially failed for camera '{self._full_name}'. Failed settings: {', '.join(failed_settings)}")
                self._camera.logger.info(f"Configuration results: {results}")
            else:
                self._camera.logger.info(f"Configuration successful for camera '{self._full_name}': {results}")
            
            # Return True if at least one setting was successful
            return any(results.values())
    
    # Exposure Control
    async def set_exposure(self, exposure: Union[int, float]) -> bool:
        """
        Set camera exposure time.
        
        Args:
            exposure: Exposure time in microseconds
            
        Returns:
            True if exposure was set successfully, False otherwise
            
        Raises:
            CameraConfigurationError: If exposure value is invalid
            CameraConnectionError: If camera is not connected
        """
        async with self._lock:
            return await self._camera.set_exposure(exposure)
    
    async def get_exposure(self) -> float:
        """
        Get current camera exposure time.
        
        Returns:
            Current exposure time in microseconds
            
        Raises:
            CameraConnectionError: If camera is not connected
        """
        return await self._camera.get_exposure()
    
    async def get_exposure_range(self) -> Tuple[float, float]:
        """
        Get camera exposure range.
        
        Returns:
            Tuple of (minimum_exposure, maximum_exposure) in microseconds
            
        Raises:
            CameraConnectionError: If camera is not connected
        """
        range_list = await self._camera.get_exposure_range()
        return range_list[0], range_list[1]
    
    # Gain Control
    async def set_gain(self, gain: Union[int, float]) -> bool:
        """
        Set camera gain value.
        
        Args:
            gain: Gain value (range depends on camera model)
            
        Returns:
            True if gain was set successfully, False otherwise
            
        Raises:
            CameraConfigurationError: If gain value is invalid
        """
        async with self._lock:
            return await self._camera.set_gain(gain)
    
    async def get_gain(self) -> float:
        """
        Get current camera gain value.
        
        Returns:
            Current gain value
            
        Raises:
            CameraConnectionError: If camera is not connected
        """
        async with self._lock:
            return await self._camera.get_gain()
    
    async def get_gain_range(self) -> Tuple[float, float]:
        """
        Get camera gain range.
        
        Returns:
            Tuple of (minimum_gain, maximum_gain)
            
        Raises:
            CameraConnectionError: If camera is not connected
        """
        async with self._lock:
            range_list = await self._camera.get_gain_range()
            return range_list[0], range_list[1]
    
    # ROI Control
    async def set_roi(self, x: int, y: int, width: int, height: int) -> bool:
        """
        Set camera Region of Interest (ROI).
        
        Args:
            x: X offset in pixels
            y: Y offset in pixels
            width: ROI width in pixels
            height: ROI height in pixels
            
        Returns:
            True if ROI was set successfully, False otherwise
            
        Raises:
            CameraConfigurationError: If ROI parameters are invalid
        """
        async with self._lock:
            return await self._camera.set_ROI(x, y, width, height)
    
    async def get_roi(self) -> Dict[str, int]:
        """
        Get current Region of Interest settings.
        
        Returns:
            Dictionary with keys: 'x', 'y', 'width', 'height'
            
        Raises:
            CameraConnectionError: If camera is not connected
        """
        async with self._lock:
            return await self._camera.get_ROI()
    
    async def reset_roi(self) -> bool:
        """
        Reset ROI to full sensor size.
        
        Returns:
            True if ROI was reset successfully, False otherwise
            
        Raises:
            CameraConnectionError: If camera is not connected
            CameraConfigurationError: If ROI reset fails
        """
        async with self._lock:
            return await self._camera.reset_ROI()
    
    # Trigger Control  
    async def set_trigger_mode(self, mode: str) -> bool:
        """
        Set camera trigger mode.
        
        Args:
            mode: Trigger mode ('continuous' for free-running, 'trigger' for external trigger)
            
        Returns:
            True if trigger mode was set successfully, False otherwise
            
        Raises:
            CameraConfigurationError: If trigger mode is invalid
            CameraConnectionError: If camera is not connected
        """
        async with self._lock:
            return await self._camera.set_triggermode(mode)
    
    async def get_trigger_mode(self) -> str:
        """
        Get current trigger mode.
        
        Returns:
            Current trigger mode ('continuous' or 'trigger')
            
        Raises:
            CameraConnectionError: If camera is not connected
        """
        return await self._camera.get_triggermode()
    
    # Pixel Format
    async def set_pixel_format(self, format: str) -> bool:
        """
        Set camera pixel format.
        
        Args:
            format: Pixel format string (e.g., 'BGR8', 'Mono8', 'RGB8')
            
        Returns:
            True if pixel format was set successfully, False otherwise
            
        Raises:
            CameraConfigurationError: If pixel format is not supported
        """
        async with self._lock:
            return await self._camera.set_pixel_format(format)
    
    async def get_pixel_format(self) -> str:
        """
        Get current pixel format.
        
        Returns:
            Current pixel format string
            
        Raises:
            CameraConnectionError: If camera is not connected
        """
        async with self._lock:
            return await self._camera.get_current_pixel_format()
    
    async def get_available_pixel_formats(self) -> List[str]:
        """
        Get list of available pixel formats.
        
        Returns:
            List of supported pixel format strings
            
        Raises:
            CameraConnectionError: If camera is not connected
        """
        async with self._lock:
            return await self._camera.get_pixel_format_range()
    
    # White Balance
    async def set_white_balance(self, mode: str) -> bool:
        """
        Set white balance mode.
        
        Args:
            mode: White balance mode ('auto', 'once', 'off', or specific mode)
            
        Returns:
            True if white balance was set successfully, False otherwise
            
        Raises:
            CameraConfigurationError: If white balance mode is invalid
            CameraConnectionError: If camera is not connected
        """
        async with self._lock:
            return await self._camera.set_auto_wb_once(mode)
    
    async def get_white_balance(self) -> str:
        """
        Get current white balance mode.
        
        Returns:
            Current white balance mode string
            
        Raises:
            CameraConnectionError: If camera is not connected
        """
        return await self._camera.get_wb()
    
    async def get_available_white_balance_modes(self) -> List[str]:
        """
        Get list of available white balance modes.
        
        Returns:
            List of supported white balance mode strings
            
        Raises:
            CameraConnectionError: If camera is not connected
        """
        async with self._lock:
            return await self._camera.get_wb_range()
    
    # Image Enhancement
    async def set_image_enhancement(self, enabled: bool) -> bool:
        """
        Enable or disable image quality enhancement.
        
        Image enhancement may include gamma correction, contrast adjustment,
        and color correction depending on the camera backend.
        
        Args:
            enabled: True to enable enhancement, False to disable
            
        Returns:
            True if setting was applied successfully, False otherwise
        """
        async with self._lock:
            return await self._camera.set_image_quality_enhancement(enabled)
    
    async def get_image_enhancement(self) -> bool:
        """
        Get current image enhancement status.
        
        Returns:
            True if image enhancement is enabled, False otherwise
        """
        async with self._lock:
            return await self._camera.get_image_quality_enhancement()
    
    # Configuration Management
    async def save_config(self, path: str) -> bool:
        """
        Save current camera configuration to file.
        
        Args:
            path: File path to save configuration to
            
        Returns:
            True if configuration was saved successfully, False otherwise
            
        Raises:
            CameraConnectionError: If camera is not connected
            IOError: If file cannot be written
        """
        async with self._lock:
            return await self._camera.export_config(path)
    
    async def load_config(self, path: str) -> bool:
        """
        Load camera configuration from file.
        
        Args:
            path: Path to configuration file
            
        Returns:
            True if configuration was loaded successfully
        """
        async with self._lock:
            return await self._camera.import_config(path)
    
    # Status and Info
    async def check_connection(self) -> bool:
        """
        Check if camera is connected and responding.
        
        Returns:
            True if camera is connected and responsive, False otherwise
        """
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
        return_images: bool = True,
        gcs_bucket: Optional[str] = None,
        gcs_path_pattern: Optional[str] = None,
        gcs_metadata: Optional[Dict[str, str]] = None
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
                gcs_uris = []
                
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
                            # Save image locally if path provided
                            if save_path and save_path.strip():
                                save_dir = os.path.dirname(save_path)
                                if save_dir:  # Only create directory if it's not empty
                                    os.makedirs(save_dir, exist_ok=True)
                                cv2.imwrite(save_path, image)
                            
                            # Upload to GCS if bucket and path pattern provided, or if auto-upload is enabled
                            should_upload = False
                            gcs_uri = None
                            
                            try:
                                import tempfile
                                from datetime import datetime, UTC
                                from mindtrace.storage import GCSStorageHandler
                                from mindtrace.hardware.core.config import get_hardware_config
                                
                                # Get GCS configuration
                                config = get_hardware_config()
                                gcs_config = config.get_config().gcs
                                
                                should_upload = (gcs_bucket and gcs_path_pattern) or (gcs_config.auto_upload and gcs_config.default_bucket)
                                
                                if should_upload:
                                    # Use provided bucket/path or default from config
                                    upload_bucket = gcs_bucket or gcs_config.default_bucket
                                    upload_path_pattern = gcs_path_pattern or f"auto_upload/{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{self._full_name.replace(':', '_')}/exposure_{{exposure}}.{gcs_config.default_image_format}"
                                    
                                    # Format GCS path with exposure
                                    gcs_path = upload_path_pattern.format(exposure=int(exposure))
                                    
                                    # Create GCS handler with configuration
                                    gcs_handler = GCSStorageHandler(
                                        bucket_name=upload_bucket,
                                        project_id=gcs_config.project_id or None,
                                        credentials_path=gcs_config.credentials_path or None,
                                        create_if_missing=gcs_config.create_if_missing,
                                        location=gcs_config.location,
                                        storage_class=gcs_config.storage_class
                                    )
                                    
                                    # Create temporary file with configured format
                                    with tempfile.NamedTemporaryFile(suffix=f".{gcs_config.default_image_format}", delete=False) as temp_file:
                                        # Save image to temp file with configured quality
                                        if gcs_config.default_image_format.lower() == "jpg":
                                            encode_params = [cv2.IMWRITE_JPEG_QUALITY, gcs_config.default_image_quality]
                                        else:
                                            encode_params = []
                                        
                                        success, encoded_image = cv2.imencode(f".{gcs_config.default_image_format}", image, encode_params)
                                        if not success:
                                            raise ValueError(f"Failed to encode image as {gcs_config.default_image_format}")
                                        
                                        temp_file.write(encoded_image.tobytes())
                                        temp_path = temp_file.name
                                    
                                    try:
                                        # Prepare metadata
                                        upload_metadata = gcs_metadata or {}
                                        if gcs_config.upload_metadata:
                                            upload_metadata.update({
                                                "camera_name": self._full_name,
                                                "camera_backend": self._camera.__class__.__name__,
                                                "capture_timestamp": datetime.now(UTC).isoformat(),
                                                "upload_timestamp": datetime.now(UTC).isoformat(),
                                                "exposure_level": str(exposure),
                                                "exposure_index": str(i),
                                                "total_exposures": str(len(exposures)),
                                                "image_format": gcs_config.default_image_format,
                                                "image_shape": f"{image.shape[1]}x{image.shape[0]}",
                                                "image_channels": str(image.shape[2]) if len(image.shape) > 2 else "1"
                                            })
                                        
                                        # Upload to GCS
                                        gcs_uri = gcs_handler.upload(
                                            local_path=temp_path,
                                            remote_path=gcs_path,
                                            metadata=upload_metadata
                                        )
                                        
                                        gcs_uris.append(gcs_uri)
                                        self._camera.logger.debug(f"HDR image uploaded to GCS: {gcs_uri}")
                                        
                                    finally:
                                        # Clean up temporary file
                                        if os.path.exists(temp_path):
                                            os.unlink(temp_path)
                                            
                            except Exception as e:
                                self._camera.logger.warning(f"Failed to upload HDR image to GCS: {e}")
                                # Continue with capture even if GCS upload fails
                            
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
                    # Return both images and GCS URIs if available
                    if gcs_uris:
                        return {
                            "images": captured_images,
                            "gcs_uris": gcs_uris,
                            "exposure_levels": exposures
                        }
                    else:
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
        """
        Close camera connection and release resources.
        
        This method safely closes the camera connection, releases any allocated
        resources, and performs cleanup operations. After calling this method,
        the camera proxy should not be used for further operations.
        
        Raises:
            CameraConnectionError: If error occurs during cleanup
        """
        async with self._lock:
            await self._camera.close()


class CameraManager(Mindtrace):
    """
    Modern camera manager with clean API and automatic backend discovery.
    
    Provides unified access to multiple camera backends with proper resource
    management, async operations, and comprehensive error handling.
    """
    
    def __init__(self, include_mocks: bool = False, max_concurrent_captures: int = None):
        """
        Initialize camera manager.
        
        Args:
            include_mocks: Include mock cameras in discovery
            max_concurrent_captures: Maximum number of concurrent captures across all cameras
                                    (important for network bandwidth management, especially for GigE cameras).
                                    If None, uses value from configuration system.
        """
        super().__init__()
        
        self._cameras: Dict[str, CameraProxy] = {}
        self._include_mocks = include_mocks
        self._discovered_backends = self._discover_all_backends()
        
        # Get max_concurrent_captures from config if not provided
        if max_concurrent_captures is None:
            from mindtrace.hardware.core.config import get_hardware_config
            config = get_hardware_config()
            max_concurrent_captures = config.get_config().cameras.max_concurrent_captures
        
        # Network bandwidth management - global semaphore to limit concurrent captures
        # This prevents network saturation when multiple GigE cameras capture simultaneously
        # Typical GigE bandwidth: 125 MB/s, high-res image: ~6MB, so limit concurrent captures
        self._capture_semaphore = asyncio.Semaphore(max_concurrent_captures)
        
        self.logger.info(
            f"CameraManager initialized. Available backends: {self._discovered_backends}, "
            f"max_concurrent_captures={max_concurrent_captures}"
        )
    
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
    
    def discover_cameras(self, backends: Optional[Union[str, List[str]]] = None) -> List[str]:
        """
        Discover available cameras across specified backends or all backends.
        
        Args:
            backends: Optional backend(s) to discover cameras from. Can be:
                     - None: Discover from all available backends (default behavior)
                     - str: Single backend name (e.g., "Basler", "OpenCV", "Daheng")
                     - List[str]: Multiple backend names (e.g., ["Basler", "Daheng"])
        
        Returns:
            List of camera names in format "Backend:device_name"
            
        Examples:
            # Discover all cameras (existing behavior)
            all_cameras = manager.discover_cameras()
            
            # Discover only Basler cameras
            basler_cameras = manager.discover_cameras("Basler")
            
            # Discover from multiple specific backends
            cameras = manager.discover_cameras(["Basler", "Daheng"])
        """
        all_cameras = []
        
        # Determine which backends to search
        if backends is None:
            # Default behavior: search all discovered backends
            backends_to_search = self._discovered_backends
        elif isinstance(backends, str):
            # Single backend specified
            backends_to_search = [backends]
        elif isinstance(backends, list):
            # Multiple backends specified
            backends_to_search = backends
        else:
            raise ValueError(f"Invalid backends parameter: {backends}. Must be None, str, or List[str]")
        
        # Validate that specified backends are available
        for backend in backends_to_search:
            if backend not in self._discovered_backends:
                self.logger.warning(f"Backend '{backend}' not available or not discovered. Available backends: {self._discovered_backends}")
                continue
        
        # Filter to only include available backends
        backends_to_search = [b for b in backends_to_search if b in self._discovered_backends]
        
        for backend in backends_to_search:
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
        self.logger.info(f"_parse_camera_name called with: '{camera_name}' (contains ':' = {':' in camera_name})")
        if ":" not in camera_name:
            self.logger.error(f"Camera name validation failed: '{camera_name}'")
            raise CameraConfigurationError(
                f"Invalid camera name format: '{camera_name}'. Expected 'Backend:device_name'"
            )
        
        backend, device_name = camera_name.split(":", 1)
        self.logger.info(f"Camera name parsed successfully: backend='{backend}', device_name='{device_name}'")
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
        """
        Get names of currently active (initialized) cameras.
        
        Returns:
            List of camera names that are currently initialized and active
        """
        return list(self._cameras.keys())
    
    def get_max_concurrent_captures(self) -> int:
        """
        Get the current maximum number of concurrent captures.
        
        Returns:
            Current maximum concurrent captures limit
        """
        return self._capture_semaphore._value
    
    def set_max_concurrent_captures(self, max_captures: int) -> None:
        """
        Set the maximum number of concurrent captures allowed.
        
        This is important for network bandwidth management, especially for GigE cameras.
        Typical values:
        - 1: Conservative, ensures no network saturation
        - 2: Balanced, allows some concurrency while managing bandwidth
        - 3+: Aggressive, may cause network issues with many high-res cameras
        
        Args:
            max_captures: Maximum number of concurrent captures
            
        Raises:
            ValueError: If max_captures is less than 1
        """
        if max_captures < 1:
            raise ValueError("max_captures must be at least 1")
        
        # Create new semaphore with updated limit
        self._capture_semaphore = asyncio.Semaphore(max_captures)
        self.logger.info(f"Max concurrent captures set to {max_captures}")
    
    def get_network_bandwidth_info(self) -> Dict[str, Any]:
        """
        Get information about network bandwidth management.
        
        Returns:
            Dictionary with bandwidth management information including:
            - max_concurrent_captures: Current limit
            - active_cameras: Number of active cameras
            - gige_cameras: Number of GigE cameras (Basler/Daheng)
            - bandwidth_management_enabled: Always True
            - recommended_settings: Recommended limits for different scenarios
        """
        return {
            "max_concurrent_captures": self.get_max_concurrent_captures(),
            "active_cameras": len(self._cameras),
            "gige_cameras": len([cam for cam in self._cameras.keys() if "Basler" in cam or "Daheng" in cam]),
            "bandwidth_management_enabled": True,
            "recommended_settings": {
                "conservative": 1,  # For critical applications
                "balanced": 2,      # For most applications  
                "aggressive": 3     # Only for high-bandwidth networks
            }
        }
    
    async def close_camera(self, camera_name: str) -> None:
        """
        Close and remove a specific camera.
        
        This method safely closes the camera connection, releases resources,
        and removes the camera from the active cameras list.
        
        Args:
            camera_name: Name of the camera to close
            
        Raises:
            Exception: If error occurs during camera closure
        """
        if camera_name in self._cameras:
            try:
                await self._cameras[camera_name].close()
                del self._cameras[camera_name]
                self.logger.info(f"Camera '{camera_name}' closed")
            except Exception as e:
                self.logger.error(f"Error closing camera '{camera_name}': {e}")
                raise
    
    async def close_all_cameras(self) -> None:
        """
        Close all active cameras.
        
        This method attempts to close all cameras, continuing even if some
        fail to close properly. Errors are logged but do not stop the process.
        """
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
        Capture from multiple cameras with network bandwidth management.
        
        Uses a global semaphore to limit concurrent captures to prevent network saturation,
        especially important for GigE cameras where bandwidth is limited.
        
        Args:
            camera_names: List of camera names to capture from
            
        Returns:
            Dict mapping camera names to captured images
        """
        results = {}
        
        async def capture_from_camera(camera_name: str) -> Tuple[str, Any]:
            try:
                # Acquire semaphore to limit concurrent captures (network bandwidth management)
                async with self._capture_semaphore:
                    camera = self.get_camera(camera_name)
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
        return_images: bool = True,
        gcs_bucket: Optional[str] = None,
        gcs_path_pattern: Optional[str] = None,
        gcs_metadata: Optional[Dict[str, str]] = None
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
            gcs_bucket: Optional GCS bucket name for cloud storage
            gcs_path_pattern: Optional GCS path pattern. Use {camera} and {exposure} placeholders
            gcs_metadata: Optional metadata for GCS upload
            
        Returns:
            Dict mapping camera names to HDR capture results
            
        Example:
            # Capture HDR from multiple cameras
            results = await manager.batch_capture_hdr(
                ["Daheng:cam1", "Basler:cam2"],
                save_path_pattern="hdr_{camera}_{exposure}.jpg",
                exposure_levels=5,
                gcs_bucket="my-bucket",
                gcs_path_pattern="hdr/{camera}/exposure_{exposure}.jpg"
            )
        """
        results = {}
        
        async def capture_hdr_from_camera(camera_name: str) -> Tuple[str, Union[List[Any], bool]]:
            try:
                # Acquire semaphore to limit concurrent captures (network bandwidth management)
                async with self._capture_semaphore:
                    camera = self.get_camera(camera_name)
                    
                    # Format save path for this camera
                    camera_save_pattern = None
                    if save_path_pattern:
                        # Replace {camera} placeholder with camera name (sanitized)
                        safe_camera_name = camera_name.replace(":", "_")
                        camera_save_pattern = save_path_pattern.replace("{camera}", safe_camera_name)
                    
                    # Format GCS path pattern for this camera
                    camera_gcs_pattern = None
                    if gcs_path_pattern:
                        # Replace {camera} placeholder with camera name (sanitized)
                        safe_camera_name = camera_name.replace(":", "_")
                        camera_gcs_pattern = gcs_path_pattern.replace("{camera}", safe_camera_name)
                    
                    result = await camera.capture_hdr(
                        save_path_pattern=camera_save_pattern,
                        exposure_levels=exposure_levels,
                        exposure_multiplier=exposure_multiplier,
                        return_images=return_images,
                        gcs_bucket=gcs_bucket,
                        gcs_path_pattern=camera_gcs_pattern,
                        gcs_metadata=gcs_metadata
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


def discover_all_cameras(
    include_mocks: bool = False, 
    max_concurrent_captures: int = 2,
    backends: Optional[Union[str, List[str]]] = None
) -> List[str]:
    """
    Quick function to discover cameras from all or specific backends.
    
    Args:
        include_mocks: Include mock cameras in discovery
        max_concurrent_captures: Maximum concurrent captures for network bandwidth management
        backends: Optional backend(s) to discover cameras from. Can be:
                 - None: Discover from all available backends (default)
                 - str: Single backend name (e.g., "Basler", "OpenCV", "Daheng")
                 - List[str]: Multiple backend names (e.g., ["Basler", "Daheng"])
        
    Returns:
        List of available camera names
        
    Examples:
        # Discover all cameras
        all_cameras = discover_all_cameras()
        
        # Discover only Basler cameras
        basler_cameras = discover_all_cameras(backends="Basler")
        
        # Discover from multiple backends
        cameras = discover_all_cameras(backends=["Basler", "Daheng"])
    """
    manager = CameraManager(include_mocks=include_mocks, max_concurrent_captures=max_concurrent_captures)
    return manager.discover_cameras(backends=backends) 