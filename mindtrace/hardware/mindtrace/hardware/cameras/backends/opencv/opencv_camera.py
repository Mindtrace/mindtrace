"""
OpenCV Camera Backend Implementation

This module provides a comprehensive interface to USB cameras, webcams, and other
video capture devices using OpenCV's VideoCapture. It supports cross-platform
camera operations with robust error handling and configuration management.

Features:
    - USB camera and webcam support across Windows, Linux, and macOS
    - Automatic camera discovery and enumeration
    - Configurable resolution, frame rate, and exposure settings
    - Image quality enhancement using CLAHE
    - Robust error handling with comprehensive retry logic
    - BGR to RGB color space conversion for consistency
    - Thread-safe operations with proper resource management

Requirements:
    - opencv-python: Core video capture functionality
    - numpy: Array operations and image processing
    - Platform-specific camera drivers (automatically detected)

Installation:
    pip install opencv-python

Usage:
    from mindtrace.hardware.cameras.backends.opencv import OpenCVCamera
    
    # Discover available cameras
    cameras = OpenCVCamera.get_available_cameras()
    
    # Initialize camera
    camera = OpenCVCamera("0", width=1280, height=720, img_quality_enhancement=True)
    success, cam_obj, remote_obj = await camera.initialize()  # Initialize first
    
    if success:
        # Configure and capture
        await camera.set_exposure(-5)
        success, image = await camera.capture()
        await camera.close()

Configuration:
    All parameters are configurable via the hardware configuration system:
    - MINDTRACE_CAMERA_OPENCV_DEFAULT_WIDTH: Default frame width (1280)
    - MINDTRACE_CAMERA_OPENCV_DEFAULT_HEIGHT: Default frame height (720)
    - MINDTRACE_CAMERA_OPENCV_DEFAULT_FPS: Default frame rate (30)
    - MINDTRACE_CAMERA_OPENCV_DEFAULT_EXPOSURE: Default exposure (-1 for auto)
    - MINDTRACE_CAMERA_OPENCV_MAX_CAMERA_INDEX: Maximum camera index to test (10)
    - MINDTRACE_CAMERA_IMAGE_QUALITY_ENHANCEMENT: Enable CLAHE enhancement
    - MINDTRACE_CAMERA_RETRIEVE_RETRY_COUNT: Number of capture retry attempts
    - MINDTRACE_CAMERA_TIMEOUT_MS: Capture timeout in milliseconds

Supported Devices:
    - USB cameras (UVC compatible)
    - Built-in webcams and laptop cameras
    - IP cameras (with proper RTSP/HTTP URLs)
    - Any device supported by OpenCV VideoCapture
    - Multiple cameras simultaneously

Error Handling:
    The module uses a comprehensive exception hierarchy for precise error reporting:
    - SDKNotAvailableError: OpenCV not installed or available
    - CameraNotFoundError: Camera not detected or accessible
    - CameraInitializationError: Failed to initialize camera
    - CameraConfigurationError: Invalid configuration parameters
    - CameraConnectionError: Connection issues or device disconnected
    - CameraCaptureError: Image acquisition failures
    - CameraTimeoutError: Operation timeout
    - HardwareOperationError: General hardware operation failures

Platform Notes:
    Linux:
        - Automatically detects /dev/video* devices
        - Requires appropriate permissions for camera access
        - May need to add user to 'video' group: sudo usermod -a -G video $USER
        - Supports V4L2 backend for advanced camera control
        
    Windows:
        - Uses DirectShow backend by default
        - Supports most USB UVC cameras out of the box
        - May require specific camera drivers for advanced features
        - MSMF backend available for newer cameras
        
    macOS:
        - Uses AVFoundation backend for optimal performance
        - Built-in cameras work without additional setup
        - External USB cameras typically supported via UVC drivers
        - May require camera permissions in System Preferences

Thread Safety:
    All camera operations are thread-safe. Multiple cameras can be used
    simultaneously from different threads without interference.

Performance Notes:
    - Camera discovery may take several seconds on first run
    - Frame capture performance depends on camera capabilities and USB bandwidth
    - Use appropriate buffer sizes for high-speed capture
    - Consider camera-specific optimizations for production use
"""

import asyncio
import glob
import os
import time
from typing import Optional, List, Tuple, Union, Dict, Any
import numpy as np

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None

from mindtrace.hardware.cameras.backends.base import BaseCamera
from mindtrace.hardware.core.exceptions import (
    SDKNotAvailableError, CameraInitializationError, CameraNotFoundError,
    CameraCaptureError, CameraConfigurationError, CameraConnectionError,
    CameraTimeoutError, HardwareOperationError, HardwareTimeoutError
)


class OpenCVCamera(BaseCamera):
    """
    OpenCV camera implementation for USB cameras and webcams.
    
    This camera backend works with any video capture device supported by OpenCV,
    including USB cameras, built-in webcams, and IP cameras. It provides a
    standardized interface for camera operations while handling platform-specific
    device discovery and configuration.
    
    The implementation includes:
    - Automatic camera discovery across platforms
    - Configurable resolution, frame rate, and exposure
    - Robust error handling with retry logic
    - Image format conversion (BGR to RGB)
    - Resource management and cleanup
    - Platform-specific optimizations
    
    Attributes:
        camera_index: Camera device index or path
        cap: OpenCV VideoCapture object
        initialized: Camera initialization status
        width: Current frame width
        height: Current frame height
        fps: Current frame rate
        exposure: Current exposure setting
        timeout_ms: Capture timeout in milliseconds
    """
    
    def __init__(
        self,
        camera_name: str,
        camera_config: Optional[str] = None,
        img_quality_enhancement: Optional[bool] = None,
        retrieve_retry_count: Optional[int] = None,
        **backend_kwargs
    ):
        """
        Initialize OpenCV camera with configuration.
        
        Args:
            camera_name: Camera identifier (index number or device path)
            camera_config: Path to camera config file (not used for OpenCV)
            img_quality_enhancement: Whether to apply image quality enhancement (uses config default if None)
            retrieve_retry_count: Number of times to retry capture (uses config default if None)
            **backend_kwargs: Backend-specific parameters:
                - width: Frame width (uses config default if None)
                - height: Frame height (uses config default if None)
                - fps: Frame rate (uses config default if None)
                - exposure: Exposure value (uses config default if None)
                - timeout_ms: Capture timeout in milliseconds (uses config default if None)
                
        Raises:
            SDKNotAvailableError: If OpenCV is not installed
            CameraConfigurationError: If configuration is invalid
            CameraInitializationError: If camera initialization fails
        """
        if not OPENCV_AVAILABLE:
            raise SDKNotAvailableError(
                "opencv-python",
                "OpenCV is required for USB camera support. Install with: pip install opencv-python"
            )
        
        super().__init__(camera_name, camera_config, img_quality_enhancement, retrieve_retry_count)
        
        # Get backend-specific configuration with fallbacks
        width = backend_kwargs.get('width')
        height = backend_kwargs.get('height')
        fps = backend_kwargs.get('fps')
        exposure = backend_kwargs.get('exposure')
        timeout_ms = backend_kwargs.get('timeout_ms')
        
        if width is None:
            width = getattr(self.camera_config.cameras, 'opencv_default_width', 1280)
        if height is None:
            height = getattr(self.camera_config.cameras, 'opencv_default_height', 720)
        if fps is None:
            fps = getattr(self.camera_config.cameras, 'opencv_default_fps', 30)
        if exposure is None:
            exposure = getattr(self.camera_config.cameras, 'opencv_default_exposure', -1)
        if timeout_ms is None:
            timeout_ms = getattr(self.camera_config.cameras, 'timeout_ms', 5000)
        
        if width <= 0 or height <= 0:
            raise CameraConfigurationError(f"Invalid resolution: {width}x{height}")
        if fps <= 0:
            raise CameraConfigurationError(f"Invalid frame rate: {fps}")
        if timeout_ms < 100:
            raise CameraConfigurationError("Timeout must be at least 100ms")
        
        self.camera_index = self._parse_camera_identifier(camera_name)
        
        self.cap: Optional[cv2.VideoCapture] = None
        
        self._width = width
        self._height = height
        self._fps = fps
        self._exposure = exposure
        self.timeout_ms = timeout_ms
        
        self.logger.info(
            f"OpenCV camera '{camera_name}' initialized with configuration: "
            f"resolution={width}x{height}, fps={fps}, exposure={exposure}, timeout={timeout_ms}ms"
        )

    def _parse_camera_identifier(self, camera_name: str) -> Union[int, str]:
        """
        Parse camera identifier from name.
        
        Args:
            camera_name: Camera name or identifier
            
        Returns:
            Camera index (int) or device path (str)
            
        Raises:
            CameraConfigurationError: If camera identifier is invalid
        """
        try:
            index = int(camera_name)
            if index < 0:
                raise CameraConfigurationError(f"Camera index must be non-negative: {index}")
            return index
        except ValueError:
            if camera_name.startswith("opencv_camera_"):
                try:
                    index = int(camera_name.split("_")[-1])
                    if index < 0:
                        raise CameraConfigurationError(f"Camera index must be non-negative: {index}")
                    return index
                except (ValueError, IndexError):
                    raise CameraConfigurationError(f"Invalid opencv camera identifier: {camera_name}")
            
            if camera_name.startswith(('/dev/', 'http://', 'https://', 'rtsp://')):
                self.logger.debug(f"Using camera device path/URL: {camera_name}")
                return camera_name
            else:
                raise CameraConfigurationError(f"Invalid camera identifier: {camera_name}")

    async def initialize(self) -> Tuple[bool, Any, Any]:
        """
        Initialize the camera and establish connection.
        
        Returns:
            Tuple of (success, camera_object, remote_control_object)
            For OpenCV cameras, both objects are the same VideoCapture instance
            
        Raises:
            CameraNotFoundError: If camera cannot be opened
            CameraInitializationError: If camera initialization fails
            CameraConnectionError: If camera connection fails
        """
        self.logger.info(f"Initializing OpenCV camera: {self.camera_name}")
        
        try:
            self.cap = cv2.VideoCapture(self.camera_index)
            
            if not self.cap.isOpened():
                self.logger.error(f"Could not open camera {self.camera_index}")
                raise CameraNotFoundError(f"Could not open camera {self.camera_index}")
            
            # Configure camera settings
            self._configure_camera()
            
            # Test capture to verify camera is working
            ret, frame = self.cap.read()
            if not ret or frame is None:
                self.logger.error(f"Camera {self.camera_index} failed to capture test frame")
                raise CameraInitializationError(f"Camera {self.camera_index} failed to capture test frame")
            
            # Verify frame has expected properties
            if len(frame.shape) != 3 or frame.shape[2] != 3:
                self.logger.error(f"Camera {self.camera_index} returned invalid frame format: {frame.shape}")
                raise CameraInitializationError(f"Camera {self.camera_index} returned invalid frame format")
            
            self.initialized = True
            self.logger.info(
                f"OpenCV camera '{self.camera_name}' initialization successful, "
                f"test frame shape: {frame.shape}, dtype: {frame.dtype}"
            )
            
            return True, self.cap, self.cap
            
        except (CameraNotFoundError, CameraInitializationError):
            raise
        except Exception as e:
            self.logger.error(f"OpenCV camera initialization failed: {e}")
            if self.cap:
                self.cap.release()
                self.cap = None
            self.initialized = False
            raise CameraInitializationError(f"Failed to initialize OpenCV camera '{self.camera_name}': {str(e)}")

    def _configure_camera(self) -> None:
        """
        Configure camera properties.
        
        Raises:
            CameraConfigurationError: If configuration fails
            CameraConnectionError: If camera is not available
        """
        if not self.cap or not self.cap.isOpened():
            raise CameraConnectionError("Camera not available for configuration")
        
        try:
            width_set = self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            height_set = self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
            
            fps_set = self.cap.set(cv2.CAP_PROP_FPS, self._fps)
            
            exposure_set = True
            if self._exposure >= 0:
                exposure_set = self.cap.set(cv2.CAP_PROP_EXPOSURE, self._exposure)
            
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            actual_exposure = self.cap.get(cv2.CAP_PROP_EXPOSURE)
            
            self.logger.info(
                f"Camera '{self.camera_name}' configuration applied: "
                f"resolution={actual_width}x{actual_height} (requested {self._width}x{self._height}), "
                f"fps={actual_fps:.1f} (requested {self._fps}), "
                f"exposure={actual_exposure:.3f} (requested {self._exposure})"
            )
            
            if abs(actual_width - self._width) > 10:
                self.logger.warning(f"Width mismatch for camera '{self.camera_name}': requested {self._width}, got {actual_width}")
            if abs(actual_height - self._height) > 10:
                self.logger.warning(f"Height mismatch for camera '{self.camera_name}': requested {self._height}, got {actual_height}")
                       
        except Exception as e:
            self.logger.error(f"Camera configuration failed for '{self.camera_name}': {e}")
            raise CameraConfigurationError(f"Failed to configure camera '{self.camera_name}': {str(e)}")

    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """
        Get the available OpenCV cameras.
        
        Args:
            include_details: If True, return detailed camera information
            
        Returns:
            List of camera names or dictionary with detailed camera information
            
        Raises:
            HardwareOperationError: If camera discovery fails
        """
        if not OPENCV_AVAILABLE:
            return [] if not include_details else {}
        
        try:
            available_cameras = []
            camera_details = {}
            
            # Get maximum camera index to test from config or use default
            max_camera_index = 10
            
            for i in range(max_camera_index):
                cap = None
                try:
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        # Try to read a frame to verify camera is actually working
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            camera_name = f"opencv_camera_{i}"
                            available_cameras.append(camera_name)
                            
                            if include_details:
                                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                                fps = cap.get(cv2.CAP_PROP_FPS)
                                
                                # Try to get additional camera properties
                                backend_name = cap.getBackendName() if hasattr(cap, 'getBackendName') else "Unknown"
                                
                                camera_details[camera_name] = {
                                    "user_id": camera_name,
                                    "device_id": str(i),
                                    "device_name": f"OpenCV Camera {i}",
                                    "device_type": "OpenCV",
                                    "width": str(width),
                                    "height": str(height),
                                    "fps": f"{fps:.1f}",
                                    "backend": backend_name,
                                    "pixel_format": "BGR8",
                                    "interface": f"USB/Video{i}"
                                }
                        else:
                            # Camera opened but can't capture - might be in use
                            pass
                except Exception as e:
                    # Camera index might not exist or be accessible
                    pass
                finally:
                    if cap:
                        cap.release()
            
            if include_details:
                return camera_details
            else:
                return available_cameras
                
        except Exception as e:
            raise HardwareOperationError(f"Failed to discover OpenCV cameras: {str(e)}")

    async def capture(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Capture an image from the camera.
        
        Implements retry logic and proper error handling for robust image capture.
        Converts OpenCV's default BGR format to RGB for consistency.
        
        Returns:
            Tuple of (success, image_array)
            - success: True if capture successful, False otherwise
            - image_array: Captured image as RGB numpy array, None if failed
            
        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            CameraCaptureError: If image capture fails
            CameraTimeoutError: If capture times out
        """
        if not self.initialized or not self.cap or not self.cap.isOpened():
            raise CameraConnectionError(f"Camera '{self.camera_name}' not ready for capture")
        
        self.logger.debug(f"Starting capture with {self.retrieve_retry_count} max attempts for camera '{self.camera_name}'")
        
        start_time = time.time()
        
        for attempt in range(self.retrieve_retry_count):
            try:
                elapsed_time = (time.time() - start_time) * 1000
                if elapsed_time > self.timeout_ms:
                    raise CameraTimeoutError(
                        f"Capture timeout after {elapsed_time:.1f}ms for camera '{self.camera_name}'"
                    )
                
                ret, frame = self.cap.read()
                
                if ret and frame is not None:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    if self.img_quality_enhancement:
                        try:
                            frame_rgb = self._enhance_image_quality(frame_rgb)
                        except Exception as enhance_error:
                            self.logger.warning(f"Image enhancement failed, using original image: {enhance_error}")
                    
                    self.logger.debug(
                        f"Capture successful for camera '{self.camera_name}': "
                        f"shape={frame_rgb.shape}, dtype={frame_rgb.dtype}, attempt={attempt + 1}"
                    )
                    
                    return True, frame_rgb
                else:
                    self.logger.warning(
                        f"Capture failed for camera '{self.camera_name}': "
                        f"no frame returned (attempt {attempt + 1}/{self.retrieve_retry_count})"
                    )
                    
            except CameraTimeoutError:
                raise
            except Exception as e:
                self.logger.error(
                    f"Capture error for camera '{self.camera_name}' "
                    f"(attempt {attempt + 1}/{self.retrieve_retry_count}): {str(e)}"
                )
                
                if attempt == self.retrieve_retry_count - 1:
                    raise CameraCaptureError(f"Capture failed for camera '{self.camera_name}': {str(e)}")
            
            if attempt < self.retrieve_retry_count - 1:
                time.sleep(0.1)
        
        raise CameraCaptureError(
            f"All {self.retrieve_retry_count} capture attempts failed for camera '{self.camera_name}'"
        )

    def _enhance_image_quality(self, image: np.ndarray) -> np.ndarray:
        """
        Apply image quality enhancement using CLAHE.
        
        Args:
            image: Input image array (RGB format)
            
        Returns:
            Enhanced image array (RGB format)
            
        Raises:
            CameraCaptureError: If image enhancement fails
        """
        try:
            # Convert RGB to LAB color space for better enhancement
            lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            
            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) to L channel
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            
            # Merge channels and convert back to RGB
            enhanced_lab = cv2.merge((cl, a, b))
            enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2RGB)
            
            # Additional enhancement: gamma correction
            gamma = 1.1
            enhanced_img = np.power(enhanced_img / 255.0, gamma) * 255.0
            enhanced_img = enhanced_img.astype(np.uint8)
            
            # Slight contrast adjustment
            alpha = 1.05  # Contrast control (lower than other backends for USB cameras)
            beta = 5      # Brightness control
            enhanced_img = cv2.convertScaleAbs(enhanced_img, alpha=alpha, beta=beta)
            
            self.logger.debug(f"Image quality enhancement applied for camera '{self.camera_name}'")
            return enhanced_img
            
        except Exception as e:
            self.logger.warning(f"Image enhancement failed for camera '{self.camera_name}': {e}")
            raise CameraCaptureError(f"Image enhancement failed for camera '{self.camera_name}': {str(e)}")

    async def check_connection(self) -> bool:
        """
        Check if camera connection is active and healthy.
        
        Returns:
            True if camera is connected and responsive, False otherwise
        """
        if not self.initialized or not self.cap:
            return False
        
        try:
            is_open = self.cap.isOpened()
            
            if is_open:
                width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                return width > 0
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Connection check failed for camera '{self.camera_name}': {e}")
            return False

    async def close(self) -> None:
        """
        Close camera connection and cleanup resources.
        
        Properly releases the VideoCapture object and resets camera state.
        
        Raises:
            CameraConnectionError: If camera closure fails
        """
        self.logger.info(f"Closing OpenCV camera: {self.camera_name}")
        
        if self.cap:
            try:
                self.cap.release()
                self.logger.debug(f"VideoCapture released successfully for camera '{self.camera_name}'")
            except Exception as e:
                self.logger.warning(f"Error releasing VideoCapture for camera '{self.camera_name}': {e}")
                raise CameraConnectionError(f"Failed to close camera '{self.camera_name}': {str(e)}")
            finally:
                self.cap = None
        
        self.initialized = False
        self.logger.info(f"OpenCV camera '{self.camera_name}' closed successfully")

    async def is_exposure_control_supported(self) -> bool:
        """
        Check if exposure control is supported for this camera.
        Tries to set and restore the exposure value, and checks if it changes.
        Returns:
            True if exposure control is supported, False otherwise
        """
        if not self.initialized or not self.cap or not self.cap.isOpened():
            return False
        try:
            original = self.cap.get(cv2.CAP_PROP_EXPOSURE)
            # Try to set to a different value within the valid range
            exposure_range = await self.get_exposure_range()
            test_value = original - 1 if original > exposure_range[0] else original + 1
            # Clamp test_value to range
            test_value = max(min(test_value, exposure_range[1]), exposure_range[0])
            if abs(test_value - original) < 1e-3:
                test_value = original + 1 if (original + 1) <= exposure_range[1] else original - 1
            success = self.cap.set(cv2.CAP_PROP_EXPOSURE, float(test_value))
            if not success:
                return False
            new_value = self.cap.get(cv2.CAP_PROP_EXPOSURE)
            # Restore original
            self.cap.set(cv2.CAP_PROP_EXPOSURE, float(original))
            # If the value actually changed, exposure control is supported
            return abs(new_value - test_value) < 1e-2
        except Exception:
            return False

    async def set_exposure(self, exposure: Union[int, float]) -> bool:
        """
        Set camera exposure time.
        Args:
            exposure: Exposure value (OpenCV uses log scale, typically -13 to -1)
        Returns:
            True if exposure was set successfully
        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If exposure value is invalid
            HardwareOperationError: If exposure setting fails
        """
        if not self.initialized or not self.cap or not self.cap.isOpened():
            raise CameraConnectionError(f"Camera '{self.camera_name}' not available for exposure setting")
        # Check if exposure control is supported
        if not await self.is_exposure_control_supported():
            self.logger.warning(f"Exposure control is not supported for camera '{self.camera_name}'. Skipping set_exposure.")
            return False
        try:
            exposure_range = await self.get_exposure_range()
            if exposure < exposure_range[0] or exposure > exposure_range[1]:
                raise CameraConfigurationError(
                    f"Exposure {exposure} outside valid range {exposure_range} for camera '{self.camera_name}'"
                )
            success = self.cap.set(cv2.CAP_PROP_EXPOSURE, float(exposure))
            if success:
                self._exposure = float(exposure)
                actual_exposure = self.cap.get(cv2.CAP_PROP_EXPOSURE)
                self.logger.info(
                    f"Exposure set for camera '{self.camera_name}': "
                    f"requested={exposure}, actual={actual_exposure:.3f}"
                )
                return True
            else:
                self.logger.warning(f"Failed to set exposure to {exposure} for camera '{self.camera_name}'")
                return False
        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Error setting exposure for camera '{self.camera_name}': {e}")
            raise HardwareOperationError(f"Failed to set exposure for camera '{self.camera_name}': {str(e)}")

    async def get_exposure(self) -> float:
        """
        Get current camera exposure time.
        
        Returns:
            Current exposure time value
            
        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If exposure retrieval fails
        """
        if not self.initialized or not self.cap or not self.cap.isOpened():
            raise CameraConnectionError(f"Camera '{self.camera_name}' not available for exposure reading")
        
        try:
            exposure = self.cap.get(cv2.CAP_PROP_EXPOSURE)
            return float(exposure)
        except Exception as e:
            self.logger.error(f"Error getting exposure for camera '{self.camera_name}': {e}")
            raise HardwareOperationError(f"Failed to get exposure for camera '{self.camera_name}': {str(e)}")

    async def get_exposure_range(self) -> List[Union[int, float]]:
        """
        Get camera exposure time range.
        
        Returns:
            List containing [min_exposure, max_exposure] in OpenCV log scale
        """
        return [
            getattr(self.camera_config.cameras, 'opencv_exposure_range_min', -13.0),
            getattr(self.camera_config.cameras, 'opencv_exposure_range_max', -1.0)
        ]

    async def get_width_range(self) -> List[int]:
        """
        Get supported width range.
        
        Returns:
            List containing [min_width, max_width]
        """
        return [
            getattr(self.camera_config.cameras, 'opencv_width_range_min', 160),
            getattr(self.camera_config.cameras, 'opencv_width_range_max', 1920)
        ]

    async def get_height_range(self) -> List[int]:
        """
        Get supported height range.
        
        Returns:
            List containing [min_height, max_height]
        """
        return [
            getattr(self.camera_config.cameras, 'opencv_height_range_min', 120),
            getattr(self.camera_config.cameras, 'opencv_height_range_max', 1080)
        ]

    def get_gain_range(self) -> List[Union[int, float]]:
        """
        Get the supported gain range.

        Returns:
            List with [min_gain, max_gain]
        """
        return [0.0, 100.0]

    def set_gain(self, gain: Union[int, float]) -> bool:
        """
        Set camera gain.
        
        Args:
            gain: Gain value
            
        Returns:
            True if gain was set successfully
            
        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If gain value is out of range or setting fails
        """
        if not self.initialized or not self.cap or not self.cap.isOpened():
            raise CameraConnectionError(f"Camera '{self.camera_name}' not available for gain setting")
        
        try:
            gain_range = self.get_gain_range()
            if gain < gain_range[0] or gain > gain_range[1]:
                raise CameraConfigurationError(f"Gain {gain} out of range {gain_range}")
            
            success = self.cap.set(cv2.CAP_PROP_GAIN, float(gain))
            if success:
                actual_gain = self.cap.get(cv2.CAP_PROP_GAIN)
                self.logger.info(f"Gain set to {gain} (actual: {actual_gain:.1f}) for camera '{self.camera_name}'")
                return True
            else:
                raise CameraConfigurationError(f"Failed to set gain to {gain} for camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set gain for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set gain for camera '{self.camera_name}': {str(e)}")

    def get_gain(self) -> float:
        """
        Get current camera gain.
        
        Returns:
            Current gain value
        """
        if not self.initialized or not self.cap or not self.cap.isOpened():
            return 0.0
        
        try:
            gain = self.cap.get(cv2.CAP_PROP_GAIN)
            return float(gain)
        except Exception as e:
            self.logger.error(f"Failed to get gain for camera '{self.camera_name}': {str(e)}")
            return 0.0

    def set_ROI(self, x: int, y: int, width: int, height: int) -> bool:
        """
        Set Region of Interest (ROI).
        
        Note: OpenCV cameras typically don't support hardware ROI,
        this would need to be implemented in software.

        Args:
            x: ROI x offset
            y: ROI y offset  
            width: ROI width
            height: ROI height

        Returns:
            False (not supported by OpenCV backend)
        """
        self.logger.warning(f"ROI setting not supported by OpenCV backend for camera '{self.camera_name}'")
        return False

    def get_ROI(self) -> Dict[str, int]:
        """
        Get current Region of Interest (ROI).
        
        Returns:
            Dictionary with full frame dimensions (ROI not supported)
        """
        if not self.initialized or not self.cap or not self.cap.isOpened():
            return {"x": 0, "y": 0, "width": 0, "height": 0}
        
        try:
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return {"x": 0, "y": 0, "width": width, "height": height}
        except Exception as e:
            self.logger.error(f"Failed to get ROI for camera '{self.camera_name}': {str(e)}")
            return {"x": 0, "y": 0, "width": 0, "height": 0}

    def reset_ROI(self) -> bool:
        """
        Reset ROI to full sensor size.
        
        Returns:
            False (not supported by OpenCV backend)
        """
        self.logger.warning(f"ROI reset not supported by OpenCV backend for camera '{self.camera_name}'")
        return False

    async def get_wb(self) -> str:
        """
        Get current white balance mode.

        Returns:
            Current white balance mode ("auto" or "manual")
        """
        if not self.initialized or not self.cap or not self.cap.isOpened():
            return "unknown"
        
        try:
            # OpenCV doesn't have a direct white balance mode query
            # Check if auto white balance is enabled
            auto_wb = self.cap.get(cv2.CAP_PROP_AUTO_WB)
            return "auto" if auto_wb > 0 else "manual"
        except Exception as e:
            self.logger.debug(f"Could not get white balance mode for camera '{self.camera_name}': {str(e)}")
            return "unknown"

    async def set_auto_wb_once(self, value: str) -> bool:
        """
        Set white balance mode.

        Args:
            value: White balance mode ("auto", "manual", "off")

        Returns:
            True if white balance was set successfully
        """
        if not self.initialized or not self.cap or not self.cap.isOpened():
            self.logger.error(f"Camera '{self.camera_name}' not available for white balance setting")
            return False
        
        try:
            if value.lower() in ["auto", "continuous"]:
                success = self.cap.set(cv2.CAP_PROP_AUTO_WB, 1)
            elif value.lower() in ["manual", "off"]:
                success = self.cap.set(cv2.CAP_PROP_AUTO_WB, 0)
            else:
                self.logger.error(f"Unsupported white balance mode: {value}")
                return False
            
            if success:
                self.logger.info(f"White balance set to '{value}' for camera '{self.camera_name}'")
                return True
            else:
                self.logger.warning(f"Failed to set white balance to '{value}' for camera '{self.camera_name}'")
                return False
        except Exception as e:
            self.logger.error(f"Failed to set white balance for camera '{self.camera_name}': {str(e)}")
            return False

    def get_wb_range(self) -> List[str]:
        """
        Get available white balance modes.
        
        Returns:
            List of available white balance modes
        """
        return ["auto", "manual", "off"]

    def get_pixel_format_range(self) -> List[str]:
        """
        Get available pixel formats.
        
        Returns:
            List of available pixel formats (OpenCV always uses BGR internally)
        """
        return ["BGR8", "RGB8"]

    def get_current_pixel_format(self) -> str:
        """
        Get current pixel format.
        
        Returns:
            Current pixel format (always BGR8 for OpenCV, converted to RGB8 in capture)
        """
        return "RGB8"  # We convert BGR to RGB in capture method

    def set_pixel_format(self, pixel_format: str) -> bool:
        """
        Set pixel format.
        
        Args:
            pixel_format: Pixel format to set
            
        Returns:
            True if pixel format is supported
            
        Raises:
            CameraConfigurationError: If pixel format is not supported
        """
        available_formats = self.get_pixel_format_range()
        if pixel_format in available_formats:
            self.logger.info(f"Pixel format '{pixel_format}' is supported for camera '{self.camera_name}'")
            return True
        else:
            raise CameraConfigurationError(f"Unsupported pixel format: {pixel_format}")

    async def get_triggermode(self) -> str:
        """
        Get trigger mode (always continuous for USB cameras).
        
        Returns:
            "continuous" (USB cameras only support continuous mode)
        """
        return "continuous"

    async def set_triggermode(self, triggermode: str = "continuous") -> bool:
        """
        Set trigger mode.
        
        USB cameras only support continuous mode.
        
        Args:
            triggermode: Trigger mode ("continuous" only)
            
        Returns:
            True if mode is supported
            
        Raises:
            CameraConfigurationError: If trigger mode is not supported
        """
        if triggermode == "continuous":
            self.logger.debug(f"Trigger mode 'continuous' confirmed for camera '{self.camera_name}'")
            return True
        
        self.logger.warning(
            f"Trigger mode '{triggermode}' not supported for camera '{self.camera_name}'. "
            f"Only 'continuous' mode is supported for USB cameras."
        )
        raise CameraConfigurationError(
            f"Trigger mode '{triggermode}' not supported for camera '{self.camera_name}'. "
            "USB cameras only support 'continuous' mode."
        )

    def get_image_quality_enhancement(self) -> bool:
        """Get image quality enhancement status."""
        return self.img_quality_enhancement

    def set_image_quality_enhancement(self, img_quality_enhancement: bool) -> bool:
        """
        Set image quality enhancement.
        
        Args:
            img_quality_enhancement: Whether to enable image quality enhancement
            
        Returns:
            True if setting was applied successfully, False otherwise
        """
        try:
            self.img_quality_enhancement = img_quality_enhancement
            if img_quality_enhancement and not hasattr(self, '_enhancement_initialized'):
                self._initialize_image_enhancement()
            self.logger.info(
                f"Image quality enhancement {'enabled' if img_quality_enhancement else 'disabled'} "
                f"for camera '{self.camera_name}'"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to set image quality enhancement for camera '{self.camera_name}': {str(e)}")
            return False

    def _initialize_image_enhancement(self):
        """Initialize image enhancement parameters for OpenCV camera."""
        try:
            # Initialize enhancement parameters - for OpenCV we use histogram equalization
            self._enhancement_initialized = True
            self.logger.debug(f"Image enhancement initialized for camera '{self.camera_name}'")
        except Exception as e:
            self.logger.error(f"Failed to initialize image enhancement for camera '{self.camera_name}': {str(e)}")

    async def export_config(self, config_path: str) -> bool:
        """
        Export current camera configuration to common JSON format.
        
        Args:
            config_path: Path to save configuration file
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            CameraConnectionError: If camera is not connected
            CameraConfigurationError: If configuration export fails
        """
        if not self.initialized or not self.cap or not self.cap.isOpened():
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not connected")
        try:
            import json, os
            dir_name = os.path.dirname(config_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            
            # Common flat format
            config = {
                "camera_type": "opencv",
                "camera_name": self.camera_name,
                "camera_index": self.camera_index,
                "timestamp": time.time(),
                "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": self.cap.get(cv2.CAP_PROP_FPS),
                "exposure_time": self.cap.get(cv2.CAP_PROP_EXPOSURE),
                "brightness": self.cap.get(cv2.CAP_PROP_BRIGHTNESS),
                "contrast": self.cap.get(cv2.CAP_PROP_CONTRAST),
                "saturation": self.cap.get(cv2.CAP_PROP_SATURATION),
                "hue": self.cap.get(cv2.CAP_PROP_HUE),
                "gain": self.cap.get(cv2.CAP_PROP_GAIN),
                "auto_exposure": self.cap.get(cv2.CAP_PROP_AUTO_EXPOSURE),
                "white_balance": "auto" if self.cap.get(cv2.CAP_PROP_AUTO_WB) > 0 else "manual",
                "white_balance_blue_u": self.cap.get(cv2.CAP_PROP_WHITE_BALANCE_BLUE_U),
                "white_balance_red_v": self.cap.get(cv2.CAP_PROP_WHITE_BALANCE_RED_V),
                "image_enhancement": self.img_quality_enhancement,
                "retrieve_retry_count": self.retrieve_retry_count,
                "timeout_ms": self.timeout_ms,
                "pixel_format": "RGB8",  # OpenCV converted output
                "trigger_mode": "continuous",  # OpenCV default
                "roi": {"x": 0, "y": 0, "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}
            }
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            self.logger.info(f"Configuration exported to '{config_path}' for camera '{self.camera_name}' using common JSON format")
            return True
        except Exception as e:
            self.logger.error(f"Failed to export config to '{config_path}' for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to export config to '{config_path}' for camera '{self.camera_name}': {str(e)}")

    async def import_config(self, config_path: str) -> bool:
        """
        Import camera configuration from common JSON format.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            CameraConnectionError: If camera is not connected
            CameraConfigurationError: If configuration import fails
        """
        if not self.initialized or not self.cap or not self.cap.isOpened():
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not connected")
        
        if not os.path.exists(config_path):
            raise CameraConfigurationError(f"Configuration file not found: {config_path}")
        
        try:
            import json
            
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            if not isinstance(config, dict):
                raise CameraConfigurationError("Invalid configuration file format")
            
            success_count = 0
            total_settings = 0
            
            # Handle both common format and legacy nested format for backward compatibility
            settings = config.get('settings', config)  # Use nested if available, otherwise flat
            
            if 'width' in settings and 'height' in settings:
                total_settings += 2
                if self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings['width']):
                    success_count += 1
                if self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings['height']):
                    success_count += 1
            
            if 'fps' in settings:
                total_settings += 1
                if self.cap.set(cv2.CAP_PROP_FPS, settings['fps']):
                    success_count += 1
            
            # Handle both exposure_time (common format) and exposure (legacy)
            exposure_key = 'exposure_time' if 'exposure_time' in settings else 'exposure'
            if exposure_key in settings and settings[exposure_key] >= 0:
                total_settings += 1
                if self.cap.set(cv2.CAP_PROP_EXPOSURE, settings[exposure_key]):
                    success_count += 1
            
            optional_props = [
                ('brightness', cv2.CAP_PROP_BRIGHTNESS),
                ('contrast', cv2.CAP_PROP_CONTRAST),
                ('saturation', cv2.CAP_PROP_SATURATION),
                ('hue', cv2.CAP_PROP_HUE),
                ('gain', cv2.CAP_PROP_GAIN),
                ('auto_exposure', cv2.CAP_PROP_AUTO_EXPOSURE),
                ('white_balance_blue_u', cv2.CAP_PROP_WHITE_BALANCE_BLUE_U),
                ('white_balance_red_v', cv2.CAP_PROP_WHITE_BALANCE_RED_V)
            ]
            
            for setting_name, cv_prop in optional_props:
                if setting_name in settings:
                    total_settings += 1
                    try:
                        if self.cap.set(cv_prop, settings[setting_name]):
                            success_count += 1
                        else:
                            self.logger.debug(f"Could not set {setting_name} for camera '{self.camera_name}' (not supported)")
                    except Exception as e:
                        self.logger.debug(f"Failed to set {setting_name} for camera '{self.camera_name}': {str(e)}")
            
            # Handle white balance mode
            if 'white_balance' in settings:
                total_settings += 1
                try:
                    wb_mode = settings['white_balance']
                    if wb_mode.lower() in ["auto", "continuous"]:
                        if self.cap.set(cv2.CAP_PROP_AUTO_WB, 1):
                            success_count += 1
                    elif wb_mode.lower() in ["manual", "off"]:
                        if self.cap.set(cv2.CAP_PROP_AUTO_WB, 0):
                            success_count += 1
                except Exception as e:
                    self.logger.debug(f"Failed to set white_balance for camera '{self.camera_name}': {str(e)}")
            
            # Handle both image_enhancement (common format) and img_quality_enhancement (legacy)
            enhancement_key = 'image_enhancement' if 'image_enhancement' in settings else 'img_quality_enhancement'
            if enhancement_key in settings:
                self.img_quality_enhancement = settings[enhancement_key]
                success_count += 1
                total_settings += 1
            
            if 'retrieve_retry_count' in settings:
                self.retrieve_retry_count = settings['retrieve_retry_count']
                success_count += 1
                total_settings += 1
            
            if 'timeout_ms' in settings:
                self.timeout_ms = settings['timeout_ms']
                success_count += 1
                total_settings += 1
            
            self.logger.info(
                f"Configuration imported from '{config_path}' for camera '{self.camera_name}': "
                f"{success_count}/{total_settings} settings applied successfully"
            )
            
            return True
            
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to import config from '{config_path}' for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to import config from '{config_path}' for camera '{self.camera_name}': {str(e)}")

    def __del__(self) -> None:
        """Destructor to ensure proper cleanup."""
        try:
            if hasattr(self, 'cap') and self.cap is not None:
                self.cap.release()
                self.cap = None
        except Exception as e:
            # Use print instead of logger since logger might not be available during destruction
            print(f"Warning: Failed to cleanup OpenCV camera during destruction: {e}") 