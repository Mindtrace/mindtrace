"""
Mock Basler Camera Backend Implementation

This module provides a mock implementation of the Basler camera backend for testing
and development purposes. It simulates all Basler camera functionality without
requiring actual hardware.

Features:
    - Complete simulation of Basler camera API
    - Configurable image generation with realistic patterns
    - Error simulation for testing error handling
    - Configuration import/export simulation
    - All camera control features (exposure, ROI, trigger modes, etc.)
    - Realistic timing and behavior simulation

Components:
    - MockBaslerCamera: Main mock camera class
    - Synthetic image generation with various patterns
    - Configurable error injection for testing
    - State persistence for configuration management

Usage:
    from mindtrace.hardware.cameras.backends.basler import MockBaslerCamera
    
    # Create mock camera
    camera = MockBaslerCamera("mock_camera_1")
    
    # Use exactly like real Basler camera
    camera.set_exposure(20000)
    success, image = camera.capture()
    camera.close()

Error Simulation:
    The mock camera can simulate various error conditions:
    - Connection failures
    - Capture timeouts
    - Configuration errors
    - Hardware operation failures
    
    Enable error simulation by setting environment variables:
    - MOCK_BASLER_FAIL_INIT: Simulate initialization failure
    - MOCK_BASLER_FAIL_CAPTURE: Simulate capture failure
    - MOCK_BASLER_TIMEOUT: Simulate timeout errors
"""

import os
import time
import json
import numpy as np
import cv2
from typing import Optional, List, Tuple, Dict, Any, Union

from mindtrace.hardware.cameras.backends.base import BaseCamera
from mindtrace.hardware.core.exceptions import (
    CameraInitializationError, CameraNotFoundError, CameraCaptureError,
    CameraConfigurationError, CameraConnectionError, CameraTimeoutError,
    HardwareOperationError
)


class MockBaslerCamera(BaseCamera):
    """Mock implementation of Basler camera for testing purposes.

    This class simulates all functionality of a real Basler camera without requiring
    actual hardware. It generates synthetic images and maintains realistic state
    behavior for comprehensive testing.

    Attributes:
        initialized: Whether camera was successfully initialized
        camera_name: Name/identifier of the mock camera
        triggermode: Current trigger mode ("continuous" or "trigger")
        img_quality_enhancement: Current image enhancement setting
        timeout_ms: Capture timeout in milliseconds
        retrieve_retry_count: Number of capture retry attempts
        exposure_time: Current exposure time in microseconds
        gain: Current gain value
        roi: Current region of interest settings
        white_balance_mode: Current white balance mode
        image_counter: Counter for generating unique images
        fail_init: Whether to simulate initialization failure
        fail_capture: Whether to simulate capture failure
        simulate_timeout: Whether to simulate timeout errors
    """

    def __init__(
        self,
        camera_name: str,
        camera_config: Optional[str] = None,
        img_quality_enhancement: Optional[bool] = None,
        retrieve_retry_count: Optional[int] = None,
        pixel_format: Optional[str] = None,
        buffer_count: Optional[int] = None,
        timeout_ms: Optional[int] = None,
    ):
        """
        Initialize mock Basler camera.

        Args:
            camera_name: Camera identifier
            camera_config: Path to configuration file (simulated)
            img_quality_enhancement: Enable image enhancement simulation
            retrieve_retry_count: Number of capture retry attempts
            pixel_format: Pixel format (simulated)
            buffer_count: Buffer count (simulated)
            timeout_ms: Timeout in milliseconds
            
        Raises:
            CameraInitializationError: If initialization fails (when simulated)
        """
        super().__init__(camera_name=camera_name)
        
        # Get configuration values with fallbacks
        if img_quality_enhancement is None:
            img_quality_enhancement = self.camera_config.cameras.image_quality_enhancement
        if retrieve_retry_count is None:
            retrieve_retry_count = self.camera_config.cameras.retrieve_retry_count
        if pixel_format is None:
            pixel_format = getattr(self.camera_config.cameras, 'pixel_format', 'BGR8')
        if buffer_count is None:
            buffer_count = getattr(self.camera_config.cameras, 'buffer_count', 25)
        if timeout_ms is None:
            timeout_ms = getattr(self.camera_config.cameras, 'timeout_ms', 5000)
        
        # Store configuration
        self.camera_config_path = camera_config
        self.img_quality_enhancement = img_quality_enhancement
        self.retrieve_retry_count = retrieve_retry_count
        self.default_pixel_format = pixel_format
        self.buffer_count = buffer_count
        self.timeout_ms = timeout_ms
        
        # Mock camera state
        self.exposure_time = 20000.0
        self.gain = 1.0
        self.roi = {"x": 0, "y": 0, "width": 1920, "height": 1080}
        self.white_balance_mode = "off"
        self.triggermode = self.camera_config.cameras.trigger_mode
        self.image_counter = 0
        
        # Error simulation flags
        self.fail_init = os.getenv('MOCK_BASLER_FAIL_INIT', 'false').lower() == 'true'
        self.fail_capture = os.getenv('MOCK_BASLER_FAIL_CAPTURE', 'false').lower() == 'true'
        self.simulate_timeout = os.getenv('MOCK_BASLER_TIMEOUT', 'false').lower() == 'true'
        
        # Initialize camera state (actual initialization happens in async initialize method)
        self.initialized = False
        self.camera = None
        self.device_manager = None

        self.logger.info(f"Mock Basler camera '{self.camera_name}' initialized successfully")

    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """
        Get available mock Basler cameras.
        
        Args:
            include_details: If True, return detailed information
            
        Returns:
            List of mock camera names or dict with details
        """
        mock_cameras = [f"mock_basler_{i}" for i in range(1, 6)]
        
        if include_details:
            camera_details = {}
            for i, camera_name in enumerate(mock_cameras, 1):
                camera_details[camera_name] = {
                    "serial_number": f"12345{i:03d}",
                    "model": "acA1920-40uc",
                    "vendor": "Basler AG",
                    "device_class": "BaslerUsb",
                    "interface": f"USB{i}",
                    "friendly_name": f"Basler acA1920-40uc ({camera_name})",
                    "user_defined_name": camera_name
                }
            return camera_details
        
        return mock_cameras

    async def initialize(self) -> Tuple[bool, Any, Any]:
        """
        Initialize the mock camera connection.
        
        Returns:
            Tuple of (success status, mock camera object, mock remote control object)
            
        Raises:
            CameraInitializationError: If initialization fails (when simulated)
        """
        if self.fail_init:
            raise CameraInitializationError(f"Simulated initialization failure for mock camera '{self.camera_name}'")
        
        mock_camera_object = {
            "name": self.camera_name,
            "model": "acA1920-40uc",
            "serial": "12345001",
            "connected": True
        }
        
        mock_remote_control = {
            "type": "mock_remote_control",
            "connected": True
        }
        
        # Set initialized flag
        self.initialized = True
        
        return True, mock_camera_object, mock_remote_control

    def get_image_quality_enhancement(self) -> bool:
        """Get image quality enhancement setting."""
        return self.img_quality_enhancement

    def set_image_quality_enhancement(self, value: bool) -> bool:
        """Set image quality enhancement setting."""
        self.img_quality_enhancement = value
        self.logger.info(f"Image quality enhancement set to {value} for mock camera '{self.camera_name}'")
        return True

    async def get_exposure_range(self) -> List[float]:
        """
        Get the supported exposure time range in microseconds.

        Returns:
            List with [min_exposure, max_exposure] in microseconds
        """
        return [20.0, 1000000.0]

    async def get_exposure(self) -> float:
        """
        Get current exposure time in microseconds.
        
        Returns:
            Current exposure time
        """
        return self.exposure_time

    async def set_exposure(self, exposure_value: float) -> bool:
        """
        Set the camera exposure time in microseconds.

        Args:
            exposure_value: Exposure time in microseconds

        Returns:
            True if exposure was set successfully
            
        Raises:
            CameraConfigurationError: If exposure value is out of range
        """
        min_exp, max_exp = await self.get_exposure_range()
        
        if exposure_value < min_exp or exposure_value > max_exp:
            raise CameraConfigurationError(
                f"Exposure {exposure_value} outside valid range [{min_exp}, {max_exp}] "
                f"for mock camera '{self.camera_name}'"
            )
        
        self.exposure_time = exposure_value
        self.logger.info(f"Exposure set to {exposure_value} µs for mock camera '{self.camera_name}'")
        return True

    def get_triggermode(self) -> List[int]:
        """
        Get current trigger mode.
        
        Returns:
            [0] for continuous mode, [1] for trigger mode
        """
        return [1] if self.triggermode == "trigger" else [0]

    def set_triggermode(self, triggermode: str = "continuous") -> bool:
        """
        Set the camera's trigger mode.

        Args:
            triggermode: Trigger mode ("continuous" or "trigger")

        Returns:
            True if mode was set successfully
            
        Raises:
            CameraConfigurationError: If trigger mode is invalid
        """
        if triggermode not in ["continuous", "trigger"]:
            raise CameraConfigurationError(
                f"Invalid trigger mode '{triggermode}' for mock camera '{self.camera_name}'. "
                "Must be 'continuous' or 'trigger'"
            )

        self.triggermode = triggermode
        self.logger.info(f"Trigger mode set to '{triggermode}' for mock camera '{self.camera_name}'")
        return True

    async def capture(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Capture a synthetic image.

        Returns:
            Tuple of (success, image_array) where image_array is BGR format
            
        Raises:
            CameraCaptureError: If capture fails (when simulated)
            CameraTimeoutError: If capture times out (when simulated)
        """
        if self.fail_capture:
            raise CameraCaptureError(f"Simulated capture failure for mock camera '{self.camera_name}'")
        
        if self.simulate_timeout:
            raise CameraTimeoutError(f"Simulated timeout for mock camera '{self.camera_name}'")
        
        # Simulate capture delay based on exposure time
        import asyncio
        capture_delay = min(self.exposure_time / 1000000.0, 0.1)
        await asyncio.sleep(capture_delay)
        
        # Generate synthetic image
        image = self._generate_synthetic_image()
        
        if self.img_quality_enhancement and image is not None:
            image = self._enhance_image(image)
        
        self.image_counter += 1
        return True, image

    def _generate_synthetic_image(self) -> np.ndarray:
        """
        Generate a synthetic test image with realistic patterns.
        
        Returns:
            BGR image array
        """
        width = self.roi["width"]
        height = self.roi["height"]
        
        # Create base image with gradient
        image = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Add gradient background
        for y in range(height):
            for x in range(width):
                image[y, x] = [
                    int(128 + 127 * np.sin(2 * np.pi * x / width)),
                    int(128 + 127 * np.cos(2 * np.pi * y / height)),
                    int(128 + 127 * np.sin(2 * np.pi * (x + y) / (width + height)))
                ]
        
        # Add some geometric patterns
        center_x, center_y = width // 2, height // 2
        cv2.circle(image, (center_x, center_y), min(width, height) // 4, (255, 255, 255), 2)
        cv2.rectangle(image, (width // 4, height // 4), (3 * width // 4, 3 * height // 4), (0, 255, 0), 2)
        
        # Add frame counter text
        cv2.putText(image, f"Frame: {self.image_counter}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Add exposure info
        cv2.putText(image, f"Exp: {self.exposure_time:.0f}us", (10, 70), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return image

    def _enhance_image(self, image: np.ndarray) -> np.ndarray:
        """
        Apply CLAHE enhancement to simulate image quality enhancement.

        Args:
            image: Input BGR image

        Returns:
            Enhanced BGR image
        """
        try:
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            enhanced_lab = cv2.merge((cl, a, b))
            enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
            return enhanced_img
        except Exception as e:
            self.logger.error(f"Image enhancement failed for mock camera '{self.camera_name}': {str(e)}")
            return image

    async def check_connection(self) -> bool:
        """
        Check if mock camera is connected and operational.
        
        Returns:
            True if connected and operational, False otherwise
        """
        if not self.initialized:
            return False
        
        try:
            status, img = await self.capture()
            return status and img is not None and img.shape[0] > 0 and img.shape[1] > 0
        except Exception:
            return False

    def import_config(self, config_path: str) -> bool:
        """
        Import camera configuration from a JSON file (simulated).
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            True if successful
            
        Raises:
            CameraConfigurationError: If configuration import fails
        """
        if not os.path.exists(config_path):
            raise CameraConfigurationError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Apply configuration settings
            if 'exposure_time' in config:
                self.exposure_time = config['exposure_time']
            if 'gain' in config:
                self.gain = config['gain']
            if 'roi' in config:
                self.roi.update(config['roi'])
            if 'trigger_mode' in config:
                self.triggermode = config['trigger_mode']
            if 'white_balance_mode' in config:
                self.white_balance_mode = config['white_balance_mode']
            
            self.logger.info(f"Configuration imported from '{config_path}' for mock camera '{self.camera_name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Error importing configuration for mock camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to import configuration: {str(e)}")

    def export_config(self, config_path: str) -> bool:
        """
        Export current camera configuration to a JSON file (simulated).
        
        Args:
            config_path: Path where to save configuration file
            
        Returns:
            True if successful
            
        Raises:
            CameraConfigurationError: If configuration export fails
        """
        try:
            os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
            
            config = {
                "camera_name": self.camera_name,
                "model": "acA1920-40uc (Mock)",
                "exposure_time": self.exposure_time,
                "gain": self.gain,
                "roi": self.roi,
                "trigger_mode": self.triggermode,
                "white_balance_mode": self.white_balance_mode,
                "image_quality_enhancement": self.img_quality_enhancement,
                "timestamp": time.time()
            }
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            self.logger.info(f"Configuration exported to '{config_path}' for mock camera '{self.camera_name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Error exporting configuration for mock camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to export configuration: {str(e)}")

    def set_ROI(self, x: int, y: int, width: int, height: int) -> bool:
        """
        Set the Region of Interest for image acquisition.

        Args:
            x: X offset from sensor top-left
            y: Y offset from sensor top-left
            width: ROI width
            height: ROI height

        Returns:
            True if ROI was set successfully
            
        Raises:
            CameraConfigurationError: If ROI parameters are invalid
        """
        if width <= 0 or height <= 0:
            raise CameraConfigurationError(f"Invalid ROI dimensions: {width}x{height}")
        if x < 0 or y < 0:
            raise CameraConfigurationError(f"Invalid ROI offsets: ({x}, {y})")
        
        # Simulate increment alignment (typical for Basler cameras)
        x = (x // 4) * 4
        y = (y // 2) * 2
        width = (width // 4) * 4
        height = (height // 2) * 2
        
        self.roi = {"x": x, "y": y, "width": width, "height": height}
        self.logger.info(f"ROI set to ({x}, {y}, {width}, {height}) for mock camera '{self.camera_name}'")
        return True

    def get_ROI(self) -> Dict[str, int]:
        """
        Get current Region of Interest settings.
        
        Returns:
            Dictionary with x, y, width, height
        """
        return self.roi.copy()

    def reset_ROI(self) -> bool:
        """
        Reset ROI to maximum sensor area.
        
        Returns:
            True if successful
        """
        self.roi = {"x": 0, "y": 0, "width": 1920, "height": 1080}
        self.logger.info(f"ROI reset to maximum for mock camera '{self.camera_name}'")
        return True

    def set_gain(self, gain: float) -> bool:
        """
        Set the camera's gain value.

        Args:
            gain: Gain value

        Returns:
            True if gain was set successfully
        """
        self.gain = max(0.0, min(gain, 20.0))  # Clamp to realistic range
        self.logger.info(f"Gain set to {self.gain} for mock camera '{self.camera_name}'")
        return True

    def get_gain(self) -> float:
        """
        Get current camera gain.
        
        Returns:
            Current gain value
        """
        return self.gain

    async def get_wb(self) -> str:
        """
        Get the current white balance auto setting.

        Returns:
            White balance auto setting ("off", "once", "continuous")
        """
        return self.white_balance_mode

    async def set_auto_wb_once(self, value: str) -> bool:
        """
        Set the white balance auto mode.

        Args:
            value: White balance mode ("off", "once", "continuous")

        Returns:
            True if white balance mode was set successfully
            
        Raises:
            CameraConfigurationError: If white balance mode is invalid
        """
        if value not in ["off", "once", "continuous"]:
            raise CameraConfigurationError(
                f"Invalid white balance mode '{value}' for mock camera '{self.camera_name}'. "
                "Must be 'off', 'once', or 'continuous'"
            )
        
        self.white_balance_mode = value
        self.logger.info(f"White balance mode set to '{value}' for mock camera '{self.camera_name}'")
        return True

    async def close(self):
        """
        Close the mock camera and release resources.
        """
        if self.initialized:
            self.initialized = False
            self.camera = None
            self.logger.info(f"Mock Basler camera '{self.camera_name}' closed")
