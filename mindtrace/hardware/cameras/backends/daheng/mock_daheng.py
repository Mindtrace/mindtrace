"""
Mock Daheng Camera Implementation

This module provides a mock implementation of Daheng cameras for testing and development
without requiring actual hardware or the gxipy SDK.

Features:
    - Complete simulation of Daheng camera functionality
    - Realistic test pattern generation with exposure effects
    - Configurable number of mock devices
    - Error simulation capabilities for testing
    - Configuration import/export testing
    - No hardware dependencies

Components:
    - MockDeviceManager: Simulates Daheng device manager
    - MockDahengCamera: Mock camera implementation

Usage:
    from mindtrace.hardware.cameras.backends.daheng import MockDahengCamera
    
    # Get available mock cameras
    cameras = MockDahengCamera.get_available_cameras()
    
    # Initialize mock camera
    camera = MockDahengCamera("mock_cam_0", img_quality_enhancement=True)
    
    # Use exactly like real camera
    camera.set_exposure(5000)
    success, image = camera.capture()
    camera.close()

Configuration:
    All parameters are configurable via the hardware configuration system:
    - MINDTRACE_CAMERA_EXPOSURE_TIME: Default exposure time
    - MINDTRACE_CAMERA_TRIGGER_MODE: Default trigger mode
    - MINDTRACE_CAMERA_WHITE_BALANCE: White balance mode
    - MINDTRACE_CAMERA_IMAGE_QUALITY_ENHANCEMENT: Enable image enhancement
    - MINDTRACE_CAMERA_RETRIEVE_RETRY_COUNT: Capture retry attempts

Testing Features:
    - Configurable number of mock cameras
    - Realistic test pattern generation
    - Exposure-based capture delays
    - Error simulation capabilities
    - Configuration import/export simulation

Error Handling:
    The module uses the same exception hierarchy as the real implementation:
    - CameraConfigurationError: Invalid configuration parameters
    - CameraInitializationError: Failed to initialize camera
    - CameraNotFoundError: Camera not detected or accessible
    - CameraConnectionError: Connection issues
    - CameraCaptureError: Image acquisition failures
    - CameraTimeoutError: Operation timeout
    - HardwareOperationError: General hardware operation failures
"""

import os
import time
import numpy as np
from typing import List, Tuple, Optional, Union, Dict
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from mindtrace.hardware.cameras.backends.base import BaseCamera
from mindtrace.hardware.core.exceptions import (
    SDKNotAvailableError, CameraInitializationError, CameraNotFoundError,
    CameraCaptureError, CameraConfigurationError, CameraConnectionError,
    CameraTimeoutError, HardwareOperationError, HardwareTimeoutError
)


class MockDeviceManager:
    """
    Mock class to simulate Daheng Camera Manager.
    
    This class simulates the device discovery and management functionality
    of the real Daheng SDK for testing purposes.
    """
    
    def __init__(self, num_cameras: Optional[int] = None):
        """
        Initialize mock device manager.
        
        Args:
            num_cameras: Number of mock cameras to simulate (uses config default if None)
            
        Raises:
            CameraConfigurationError: If configuration is invalid
        """
        try:
            if num_cameras is None:
                self.num_cameras = int(os.getenv("MINDTRACE_MOCK_DAHENG_CAMERAS", "25"))
            else:
                self.num_cameras = num_cameras
                
            if self.num_cameras < 0:
                raise CameraConfigurationError("Number of mock cameras cannot be negative")
                
        except ValueError as e:
            raise CameraConfigurationError(f"Invalid mock camera count configuration: {str(e)}")

    def get_device_list(self) -> List[str]:
        """
        Get the list of mock Daheng cameras.
        
        Returns:
            List of mock camera identifiers
            
        Raises:
            HardwareOperationError: If device list generation fails
        """
        try:
            return [f"mock_cam_{i}" for i in range(self.num_cameras)]
        except Exception as e:
            raise HardwareOperationError(f"Failed to generate mock device list: {str(e)}")

    def get_device_info(self, device_id: str) -> Dict[str, str]:
        """
        Get the information of a mock Daheng camera.
        
        Args:
            device_id: Camera device identifier
            
        Returns:
            Dictionary with camera information
            
        Raises:
            CameraNotFoundError: If device_id is invalid
            HardwareOperationError: If device info generation fails
        """
        try:
            if not device_id.startswith("mock_cam_"):
                raise CameraNotFoundError(f"Invalid mock camera ID: {device_id}")
                
            return {
                "user_id": device_id,
                "device_id": device_id,
                "device_name": f"Mock Daheng Camera {device_id}",
                "device_type": "Mock Daheng",
                "device_status": "connected",
                "serial_number": f"MOCK{device_id.upper()}",
                "model": "Mock-DH-GC2450C",
                "vendor": "Mock Daheng Imaging"
            }
        except CameraNotFoundError:
            raise
        except Exception as e:
            raise HardwareOperationError(f"Failed to get device info for {device_id}: {str(e)}")

    def update_device_list(self) -> Tuple[int, List[Dict[str, str]]]:
        """
        Update and return the list of mock Daheng cameras.
        
        Returns:
            Tuple of (camera_count, camera_info_list)
            
        Raises:
            HardwareOperationError: If device list update fails
        """
        try:
            device_list = [
                self.get_device_info(f"mock_cam_{i}") 
                for i in range(self.num_cameras)
            ]
            return self.num_cameras, device_list
        except Exception as e:
            raise HardwareOperationError(f"Failed to update mock device list: {str(e)}")


class MockDahengCamera(BaseCamera):
    """
    Mock implementation of Daheng camera for testing and development.
    
    This class provides a complete simulation of the Daheng camera API without
    requiring actual hardware. It's designed for testing, development, and
    continuous integration environments.
    
    Attributes:
        camera_name: User-defined camera identifier
        camera_config: Path to camera configuration file
        img_quality_enhancement: Enable image quality enhancement
        retrieve_retry_count: Number of capture retry attempts
        device_manager: Mock device manager instance
        triggermode: Current trigger mode
        exposure_time: Current exposure time in microseconds
        width: Image width in pixels
        height: Image height in pixels
        lower_exposure_limit: Minimum exposure time
        upper_exposure_limit: Maximum exposure time
        _wb_mode: Current white balance mode
        _is_connected: Connection status simulation
    """
    
    def __init__(
        self,
        camera_name: str,
        camera_config: Optional[str] = None,
        img_quality_enhancement: Optional[bool] = None,
        retrieve_retry_count: Optional[int] = None,
        trigger_mode: Optional[str] = None,
        exposure_time: Optional[int] = None,
        wb_mode: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        lower_exposure_limit: Optional[int] = None,
        upper_exposure_limit: Optional[int] = None,
    ):
        """
        Initialize mock Daheng camera with configurable parameters.

        Args:
            camera_name: User ID of mock camera
            camera_config: Path to camera config file (optional)
            img_quality_enhancement: Enable image enhancement (uses config default if None)
            retrieve_retry_count: Number of capture retry attempts (uses config default if None)
            trigger_mode: Initial trigger mode (uses config default if None)
            exposure_time: Initial exposure time in microseconds (uses config default if None)
            wb_mode: Initial white balance mode (uses config default if None)
            width: Image width in pixels (uses config default if None)
            height: Image height in pixels (uses config default if None)
            lower_exposure_limit: Minimum exposure time (default: 100)
            upper_exposure_limit: Maximum exposure time (default: 1000000)
            
        Raises:
            CameraConfigurationError: If configuration is invalid
            CameraInitializationError: If camera initialization fails
            CameraNotFoundError: If camera is not found in mock device list
        """
        super().__init__(camera_name, camera_config, img_quality_enhancement, retrieve_retry_count)
        
        if trigger_mode is None:
            trigger_mode = self.camera_config.cameras.trigger_mode
        if exposure_time is None:
            exposure_time = self.camera_config.cameras.exposure_time
        if wb_mode is None:
            wb_mode = self.camera_config.cameras.white_balance
        if width is None:
            width = getattr(self.camera_config.cameras, 'opencv_default_width', 640)
        if height is None:
            height = getattr(self.camera_config.cameras, 'opencv_default_height', 480)
        
        if exposure_time < 0:
            raise CameraConfigurationError("Exposure time cannot be negative")
        if width <= 0 or height <= 0:
            raise CameraConfigurationError("Image dimensions must be positive")
        if retrieve_retry_count is not None and retrieve_retry_count < 1:
            raise CameraConfigurationError("Retry count must be at least 1")
        
        try:
            self.device_manager = MockDeviceManager()
        except Exception as e:
            raise CameraInitializationError(f"Failed to initialize mock device manager: {str(e)}")
            
        self.remote_device_feature = None
        self.triggermode = trigger_mode
        self.exposure_time = exposure_time
        self._wb_mode = wb_mode
        self.width = width
        self.height = height
        self.lower_exposure_limit = lower_exposure_limit or 100
        self.upper_exposure_limit = upper_exposure_limit or 1000000
        self._is_connected = True
        
        if self.lower_exposure_limit >= self.upper_exposure_limit:
            raise CameraConfigurationError("Lower exposure limit must be less than upper exposure limit")
        
        # Initialize camera state (actual initialization happens in async initialize method)
        self.initialized = False
        self.camera = None
        self.remote_device_feature = None
        
        self.logger.info(
            f"Mock Daheng camera '{self.camera_name}' initialized: "
            f"width={width}, height={height}, exposure={exposure_time}"
        )

    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """
        Get the available mock Daheng cameras.
        
        Args:
            include_details: If True, return detailed camera information
            
        Returns:
            List of camera names or dictionary with detailed camera information
            
        Raises:
            HardwareOperationError: If camera discovery fails
        """
        try:
            device_manager = MockDeviceManager()
            dev_cnt, dev_info_list = device_manager.update_device_list()
            
            if include_details:
                return {
                    dev_info.get("user_id", f"camera_{i}"): dev_info 
                    for i, dev_info in enumerate(dev_info_list)
                }
            else:
                return [
                    dev_info.get("user_id", f"camera_{i}") 
                    for i, dev_info in enumerate(dev_info_list)
                ]
        except Exception as e:
            raise HardwareOperationError(f"Failed to discover mock cameras: {str(e)}")

    async def initialize(self) -> Tuple[bool, None, None]:
        """
        Mock initialization that always succeeds.

        Returns:
            Tuple of (True, None, None) to simulate successful initialization

        Raises:
            CameraNotFoundError: If camera name is not in available mock cameras
            CameraInitializationError: If initialization fails
        """
        try:
            # For testing flexibility, accept any camera name
            # In production, you might want to check against available_cameras
            available_cameras = self.device_manager.get_device_list()
            
            # Allow any camera name for testing, but log if it's not in the standard list
            if self.camera_name not in available_cameras:
                self.logger.debug(f"Mock camera '{self.camera_name}' not in standard list {available_cameras}, but allowing for testing")
            
            self.initialized = True
            self._is_connected = True
            self.logger.info(f"Mock Daheng camera '{self.camera_name}' initialized successfully")
            return True, None, None
            
        except Exception as e:
            raise CameraInitializationError(f"Failed to initialize mock camera '{self.camera_name}': {str(e)}")

    def set_config(self, config: str) -> bool:
        """
        Mock configuration setter.
        
        Args:
            config: Path to configuration file
            
        Returns:
            True (always successful for mock)
            
        Raises:
            CameraConfigurationError: If configuration file doesn't exist
        """
        if not os.path.exists(config):
            raise CameraConfigurationError(f"Configuration file not found: {config}")
        
        self.logger.info(f"Mock configuration set for camera '{self.camera_name}': {config}")
        return True

    def get_image_quality_enhancement(self) -> bool:
        """Get the current image quality enhancement status."""
        return self.img_quality_enhancement

    def set_image_quality_enhancement(self, img_quality_enhancement: bool) -> bool:
        """
        Set image quality enhancement status.
        
        Args:
            img_quality_enhancement: Enable image quality enhancement
            
        Returns:
            True (always successful for mock)
        """
        self.img_quality_enhancement = img_quality_enhancement
        self.logger.info(f"Image quality enhancement set to {img_quality_enhancement} for camera '{self.camera_name}'")
        return True

    def set_triggermode(self, triggermode: str = "continuous") -> bool:
        """
        Set the trigger mode of the mock camera.
        
        Args:
            triggermode: Trigger mode ("continuous" or "trigger")
            
        Returns:
            True if valid mode, False otherwise
            
        Raises:
            CameraConfigurationError: If trigger mode is invalid
        """
        if triggermode not in ["continuous", "trigger"]:
            raise CameraConfigurationError(f"Invalid trigger mode '{triggermode}'. Must be 'continuous' or 'trigger'")
        
        self.triggermode = triggermode
        self.logger.info(f"Trigger mode set to '{triggermode}' for camera '{self.camera_name}'")
        return True

    def get_triggermode(self) -> str:
        """Get the current trigger mode."""
        return self.triggermode

    async def get_exposure_range(self) -> List[Union[int, float]]:
        """Get the mock exposure range in microseconds."""
        return [self.lower_exposure_limit, self.upper_exposure_limit]

    async def get_width_range(self) -> List[int]:
        """Get the mock width range in pixels."""
        return [320, self.width * 2]

    async def get_height_range(self) -> List[int]:
        """Get the mock height range in pixels."""
        return [240, self.height * 2]

    async def get_wb(self) -> str:
        """Get the current white balance mode."""
        return self._wb_mode

    async def set_auto_wb_once(self, value: str) -> bool:
        """
        Set the white balance mode.
        
        Args:
            value: White balance mode ("off", "once", "auto")
            
        Returns:
            True if valid mode, False otherwise
            
        Raises:
            CameraConfigurationError: If white balance mode is invalid
        """
        if value not in ["off", "once", "auto"]:
            raise CameraConfigurationError(f"Invalid white balance mode '{value}'. Must be 'off', 'once', or 'auto'")
        
        self._wb_mode = value
        return True

    async def set_exposure(self, exposure_value: Union[int, float]) -> bool:
        """
        Set the exposure time of the mock camera.
        
        Args:
            exposure_value: Exposure time in microseconds
            
        Returns:
            True if within valid range, False otherwise
            
        Raises:
            CameraConfigurationError: If exposure value is out of range
        """
        if not (self.lower_exposure_limit <= exposure_value <= self.upper_exposure_limit):
            raise CameraConfigurationError(
                f"Exposure value {exposure_value} out of range "
                f"[{self.lower_exposure_limit}, {self.upper_exposure_limit}] "
                f"for camera '{self.camera_name}'"
            )
        
        self.exposure_time = float(exposure_value)
        return True

    async def get_exposure(self) -> float:
        """Get the current exposure time in microseconds."""
        return self.exposure_time

    async def close(self):
        """
        Close the mock camera connection.
        
        Raises:
            CameraConnectionError: If camera cannot be closed properly
        """
        try:
            self._is_connected = False
            self.initialized = False
            self.logger.info(f"Mock camera '{self.camera_name}' closed")
        except Exception as e:
            raise CameraConnectionError(f"Error closing mock camera '{self.camera_name}': {str(e)}")

    async def capture(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Simulate camera capture with realistic behavior.

        This method simulates a realistic camera capture by:
        1. Checking connection status
        2. Adding a realistic delay based on exposure time
        3. Generating a test pattern image with some variation

        Returns:
            Tuple of (success, image_array) where image_array is BGR format
            
        Raises:
            CameraConnectionError: If camera is not connected
            CameraCaptureError: If capture simulation fails
            CameraTimeoutError: If capture simulation times out
        """
        if not self._is_connected or not self.initialized:
            raise CameraConnectionError(f"Mock camera '{self.camera_name}' is not connected")

        try:
            import asyncio
            delay = min(0.4, max(0.01, self.exposure_time / 100000.0))
            await asyncio.sleep(delay)

            test_image = self._generate_test_pattern()
            
            if self.img_quality_enhancement:
                test_image = self._apply_mock_enhancement(test_image)
            
            self.logger.debug(f"Mock image captured from camera '{self.camera_name}', shape: {test_image.shape}")
            return True, test_image
            
        except Exception as e:
            self.logger.error(f"Mock capture failed for camera '{self.camera_name}': {str(e)}")
            raise CameraCaptureError(f"Mock capture failed for camera '{self.camera_name}': {str(e)}")

    def _generate_test_pattern(self) -> np.ndarray:
        """
        Generate a realistic test pattern image for mock capture.
        
        Returns:
            BGR image array with test pattern
            
        Raises:
            CameraCaptureError: If test pattern generation fails
        """
        try:
            image = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            
            exposure_factor = min(1.0, self.exposure_time / 50000.0)
            
            for i in range(self.height):
                for j in range(self.width):
                    image[i, j, 0] = int((i / self.height) * 255 * exposure_factor)
                    image[i, j, 1] = int((j / self.width) * 255 * exposure_factor)
                    image[i, j, 2] = int(128 * exposure_factor)
            
            noise_level = max(5, int(20 * (1.0 - exposure_factor)))
            noise = np.random.randint(-noise_level, noise_level, (self.height, self.width, 3), dtype=np.int16)
            image = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            
            if CV2_AVAILABLE:
                timestamp = int(time.time() * 1000) % 10000
                cv2.putText(
                    image, 
                    f"Mock:{self.camera_name}:{timestamp}", 
                    (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, 
                    (255, 255, 255), 
                    1
                )
                
                cv2.putText(
                    image, 
                    f"Exp:{int(self.exposure_time)}us", 
                    (10, self.height - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 
                    0.4, 
                    (255, 255, 255), 
                    1
                )
            
            return image
            
        except Exception as e:
            raise CameraCaptureError(f"Failed to generate test pattern for camera '{self.camera_name}': {str(e)}")

    def _apply_mock_enhancement(self, image: np.ndarray) -> np.ndarray:
        """
        Apply mock image quality enhancement.
        
        Args:
            image: Input image array
            
        Returns:
            Enhanced image array
            
        Raises:
            CameraCaptureError: If enhancement fails
        """
        try:
            enhanced = np.clip(image.astype(np.float32) * 1.1 + 10, 0, 255).astype(np.uint8)
            return enhanced
        except Exception as e:
            raise CameraCaptureError(f"Failed to apply mock enhancement for camera '{self.camera_name}': {str(e)}")

    async def check_connection(self) -> bool:
        """
        Check if mock camera connection is active.
        
        Returns:
            True if connected, False otherwise
            
        Raises:
            CameraConnectionError: If connection check fails
        """
        try:
            return self._is_connected and self.initialized
        except Exception as e:
            raise CameraConnectionError(f"Connection check failed for mock camera '{self.camera_name}': {str(e)}")

    def import_config(self, config_path: str) -> bool:
        """
        Mock configuration import.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            True if file exists, False otherwise
            
        Raises:
            CameraConfigurationError: If configuration import fails
        """
        try:
            if os.path.exists(config_path):
                self.logger.info(f"Mock configuration imported from '{config_path}' for camera '{self.camera_name}'")
                return True
            else:
                raise CameraConfigurationError(f"Mock configuration file not found: '{config_path}' for camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            raise CameraConfigurationError(f"Failed to import mock configuration from '{config_path}': {str(e)}")

    def export_config(self, config_path: str) -> bool:
        """
        Mock configuration export.
        
        Args:
            config_path: Path to save configuration file
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            CameraConfigurationError: If configuration export fails
        """
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            config_data = {
                "camera_name": self.camera_name,
                "camera_type": "Mock Daheng",
                "width": self.width,
                "height": self.height,
                "exposure_time": self.exposure_time,
                "trigger_mode": self.triggermode,
                "white_balance": self._wb_mode,
                "image_quality_enhancement": self.img_quality_enhancement,
                "exposure_range": [self.lower_exposure_limit, self.upper_exposure_limit],
                "timestamp": time.time()
            }
            
            with open(config_path, "w") as f:
                f.write("# Mock Daheng Camera Configuration\n")
                for key, value in config_data.items():
                    f.write(f"{key}: {value}\n")
            
            self.logger.info(f"Mock configuration exported to '{config_path}' for camera '{self.camera_name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export mock config to '{config_path}' for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to export mock config to '{config_path}' for camera '{self.camera_name}': {str(e)}")
