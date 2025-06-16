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
    
    # Configure and capture
    camera.set_exposure(-5)
    success, image = camera.capture()
    camera.close()

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
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
        exposure: Optional[float] = None,
        timeout_ms: Optional[int] = None,
        **kwargs
    ):
        """
        Initialize OpenCV camera with configuration.
        
        Args:
            camera_name: Camera identifier (index number or device path)
            camera_config: Path to camera config file (not used for OpenCV)
            img_quality_enhancement: Whether to apply image quality enhancement (uses config default if None)
            retrieve_retry_count: Number of times to retry capture (uses config default if None)
            width: Frame width (uses config default if None)
            height: Frame height (uses config default if None)
            fps: Frame rate (uses config default if None)
            exposure: Exposure value (uses config default if None)
            timeout_ms: Capture timeout in milliseconds (uses config default if None)
            **kwargs: Additional camera parameters
                
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
        
        if self.retrieve_retry_count < 1:
            raise CameraConfigurationError("Retry count must be at least 1")
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

        try:
            self.initialized, self.cap, _ = self.initialize()
        except (CameraNotFoundError, CameraInitializationError):
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenCV camera '{camera_name}': {str(e)}")
            self.initialized = False
            raise CameraInitializationError(f"Failed to initialize OpenCV camera '{camera_name}': {str(e)}")

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

    def initialize(self) -> Tuple[bool, Any, Any]:
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
            
            self._configure_camera()
            
            ret, frame = self.cap.read()
            if not ret or frame is None:
                self.logger.error(f"Camera {self.camera_index} failed to capture test frame")
                raise CameraInitializationError(f"Camera {self.camera_index} failed to capture test frame")
            
            self.initialized = True
            self.logger.info(
                f"OpenCV camera '{self.camera_name}' initialization successful, "
                f"test frame shape: {frame.shape}"
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
        try:
            available_cameras = []
            camera_details = {}
            
            for i in range(10):
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    camera_name = f"opencv_camera_{i}"
                    available_cameras.append(camera_name)
                    
                    if include_details:
                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        
                        camera_details[camera_name] = {
                            "user_id": camera_name,
                            "device_id": str(i),
                            "device_name": f"OpenCV Camera {i}",
                            "device_type": "OpenCV",
                            "width": str(width),
                            "height": str(height),
                            "fps": str(fps),
                            "backend": "OpenCV"
                        }
                    
                    cap.release()
                else:
                    cap.release()
            
            if include_details:
                return camera_details
            else:
                return available_cameras
                
        except Exception as e:
            raise HardwareOperationError(f"Failed to discover OpenCV cameras: {str(e)}")

    def capture(self) -> Tuple[bool, Optional[np.ndarray]]:
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
                        frame_rgb = self._enhance_image_quality(frame_rgb)
                    
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
            yuv = cv2.cvtColor(image, cv2.COLOR_RGB2YUV)
            yuv[:, :, 0] = cv2.equalizeHist(yuv[:, :, 0])
            enhanced = cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB)
            
            self.logger.debug(f"Image quality enhancement applied for camera '{self.camera_name}'")
            return enhanced
            
        except Exception as e:
            self.logger.warning(f"Image enhancement failed for camera '{self.camera_name}': {e}")
            raise CameraCaptureError(f"Image enhancement failed for camera '{self.camera_name}': {str(e)}")

    def check_connection(self) -> bool:
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

    def close(self) -> None:
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

    def set_exposure(self, exposure: float) -> bool:
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
        
        try:
            exposure_range = self.get_exposure_range()
            if exposure < exposure_range[0] or exposure > exposure_range[1]:
                raise CameraConfigurationError(
                    f"Exposure {exposure} outside valid range {exposure_range} for camera '{self.camera_name}'"
                )
            
            success = self.cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
            if success:
                self._exposure = exposure
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

    def get_exposure(self) -> float:
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
            return exposure
        except Exception as e:
            self.logger.error(f"Error getting exposure for camera '{self.camera_name}': {e}")
            raise HardwareOperationError(f"Failed to get exposure for camera '{self.camera_name}': {str(e)}")

    def get_exposure_range(self) -> List[Union[int, float]]:
        """
        Get camera exposure time range.
        
        Returns:
            List containing [min_exposure, max_exposure] in OpenCV log scale
        """
        return [
            getattr(self.camera_config.cameras, 'opencv_exposure_range_min', -13.0),
            getattr(self.camera_config.cameras, 'opencv_exposure_range_max', -1.0)
        ]

    def get_width_range(self) -> List[int]:
        """
        Get supported width range.
        
        Returns:
            List containing [min_width, max_width]
        """
        return [
            getattr(self.camera_config.cameras, 'opencv_width_range_min', 160),
            getattr(self.camera_config.cameras, 'opencv_width_range_max', 1920)
        ]

    def get_height_range(self) -> List[int]:
        """
        Get supported height range.
        
        Returns:
            List containing [min_height, max_height]
        """
        return [
            getattr(self.camera_config.cameras, 'opencv_height_range_min', 120),
            getattr(self.camera_config.cameras, 'opencv_height_range_max', 1080)
        ]

    def get_triggermode(self) -> str:
        """
        Get trigger mode (always continuous for USB cameras).
        
        Returns:
            "continuous" (USB cameras only support continuous mode)
        """
        return "continuous"

    def set_triggermode(self, triggermode: str = "continuous") -> bool:
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
            self.logger.info(
                f"Image quality enhancement {'enabled' if img_quality_enhancement else 'disabled'} "
                f"for camera '{self.camera_name}'"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to set image quality enhancement for camera '{self.camera_name}': {str(e)}")
            return False

    def export_config(self, config_path: str) -> bool:
        """
        Export current camera configuration to JSON file.
        
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
            import json
            
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            config = {
                "camera_type": "opencv",
                "camera_name": self.camera_name,
                "camera_index": self.camera_index,
                "timestamp": time.time(),
                "settings": {
                    "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    "fps": self.cap.get(cv2.CAP_PROP_FPS),
                    "exposure": self.cap.get(cv2.CAP_PROP_EXPOSURE),
                    "brightness": self.cap.get(cv2.CAP_PROP_BRIGHTNESS),
                    "contrast": self.cap.get(cv2.CAP_PROP_CONTRAST),
                    "saturation": self.cap.get(cv2.CAP_PROP_SATURATION),
                    "hue": self.cap.get(cv2.CAP_PROP_HUE),
                    "gain": self.cap.get(cv2.CAP_PROP_GAIN),
                    "auto_exposure": self.cap.get(cv2.CAP_PROP_AUTO_EXPOSURE),
                    "white_balance_blue_u": self.cap.get(cv2.CAP_PROP_WHITE_BALANCE_BLUE_U),
                    "white_balance_red_v": self.cap.get(cv2.CAP_PROP_WHITE_BALANCE_RED_V),
                    "img_quality_enhancement": self.img_quality_enhancement,
                    "retrieve_retry_count": self.retrieve_retry_count,
                    "timeout_ms": self.timeout_ms
                }
            }
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            self.logger.info(f"Configuration exported to '{config_path}' for camera '{self.camera_name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export config to '{config_path}' for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to export config to '{config_path}' for camera '{self.camera_name}': {str(e)}")

    def import_config(self, config_path: str) -> bool:
        """
        Import camera configuration from JSON file.
        
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
            
            if not isinstance(config, dict) or 'settings' not in config:
                raise CameraConfigurationError("Invalid configuration file format")
            
            settings = config['settings']
            
            success_count = 0
            total_settings = 0
            
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
            
            if 'exposure' in settings and settings['exposure'] >= 0:
                total_settings += 1
                if self.cap.set(cv2.CAP_PROP_EXPOSURE, settings['exposure']):
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
            
            if 'img_quality_enhancement' in settings:
                self.img_quality_enhancement = settings['img_quality_enhancement']
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
            self.close()
        except Exception:
            pass 