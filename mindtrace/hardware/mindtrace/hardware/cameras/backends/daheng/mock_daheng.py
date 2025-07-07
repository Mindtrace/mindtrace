"""
Mock Daheng Camera Backend Implementation

This module provides a mock implementation of the Daheng camera backend for testing
and development purposes. It simulates all Daheng camera functionality without
requiring actual hardware.

Features:
    - Complete simulation of Daheng camera API
    - Configurable image generation with realistic patterns
    - Error simulation for testing error handling
    - Configuration import/export simulation
    - All camera control features (exposure, ROI, trigger modes, etc.)
    - Realistic timing and behavior simulation

Components:
    - MockDahengCamera: Main mock camera class
    - Synthetic image generation with various patterns
    - Configurable error injection for testing
    - State persistence for configuration management

Usage:
    from mindtrace.hardware.mindtrace.hardware.cameras.backends.daheng import MockDahengCamera
    
    # Create mock camera
    camera = MockDahengCamera("mock_camera_1")
    
    # Use exactly like real Daheng camera
    await camera.set_exposure(20000)
    success, image = await camera.capture()
    await camera.close()

Error Simulation:
    The mock camera can simulate various error conditions:
    - Connection failures
    - Capture timeouts
    - Configuration errors
    - Hardware operation failures
    
    Enable error simulation by setting environment variables:
    - MOCK_DAHENG_FAIL_INIT: Simulate initialization failure
    - MOCK_DAHENG_FAIL_CAPTURE: Simulate capture failure
    - MOCK_DAHENG_TIMEOUT: Simulate timeout errors
"""

import os
import time
import json
import asyncio
import numpy as np
import cv2
from typing import Optional, List, Tuple, Dict, Any, Union

from mindtrace.hardware.mindtrace.hardware.cameras.backends.base import BaseCamera
from mindtrace.hardware.mindtrace.hardware.core.exceptions import (
    SDKNotAvailableError, CameraInitializationError, CameraNotFoundError,
    CameraCaptureError, CameraConfigurationError, CameraConnectionError,
    CameraTimeoutError, HardwareOperationError
)



class MockDahengCamera(BaseCamera):
    """Mock implementation of Daheng camera for testing purposes.

    This class simulates all functionality of a real Daheng camera without requiring
    actual hardware. It generates synthetic images and maintains realistic state
    behavior for comprehensive testing.

    Attributes:
        initialized: Whether camera was successfully initialized
        camera_name: Name/identifier of the mock camera
        triggermode: Current trigger mode ("continuous" or "trigger")
        img_quality_enhancement: Current image enhancement setting
        timeout_ms: Capture timeout in milliseconds
        buffer_count: Number of frame buffers
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
        **backend_kwargs
    ):
        """
        Initialize mock Daheng camera.

        Args:
            camera_name: Camera identifier
            camera_config: Path to configuration file (simulated)
            img_quality_enhancement: Enable image enhancement simulation (uses config default if None)
            retrieve_retry_count: Number of capture retry attempts (uses config default if None)
            **backend_kwargs: Backend-specific parameters:
                - buffer_count: Buffer count (simulated)
                - timeout_ms: Timeout in milliseconds
            
        Raises:
            CameraConfigurationError: If configuration is invalid
            CameraInitializationError: If initialization fails (when simulated)
        """
        super().__init__(camera_name, camera_config, img_quality_enhancement, retrieve_retry_count)
        
        # Get backend-specific configuration with fallbacks
        buffer_count = backend_kwargs.get('buffer_count')
        timeout_ms = backend_kwargs.get('timeout_ms')
        
        if buffer_count is None:
            buffer_count = getattr(self.camera_config, 'buffer_count', 25)
        if timeout_ms is None:
            timeout_ms = getattr(self.camera_config, 'timeout_ms', 5000)
        
        # Validate parameters
        if buffer_count < 1:
            raise CameraConfigurationError("Buffer count must be at least 1")
        if timeout_ms < 100:
            raise CameraConfigurationError("Timeout must be at least 100ms")
        
        # Store configuration
        self.camera_config_path = camera_config
        self.buffer_count = buffer_count
        self.timeout_ms = timeout_ms
        
        # Mock camera state
        self.exposure_time = 20000.0
        self.gain = 1.0
        self.roi = {"x": 0, "y": 0, "width": 4024, "height": 3036}
        self.white_balance_mode = "off"
        self.triggermode = self.camera_config.cameras.trigger_mode
        self.image_counter = 0
        
        # Internal state
        self.device_manager = None
        self.remote_device_feature = None
        
        # Image enhancement parameters
        self.gamma_lut = None
        self.contrast_lut = None
        self.color_correction_param = None
        
        # Error simulation flags
        self.fail_init = os.getenv('MOCK_DAHENG_FAIL_INIT', 'false').lower() == 'true'
        self.fail_capture = os.getenv('MOCK_DAHENG_FAIL_CAPTURE', 'false').lower() == 'true'
        self.simulate_timeout = os.getenv('MOCK_DAHENG_TIMEOUT', 'false').lower() == 'true'
        
        # Initialize camera state (actual initialization happens in async initialize method)
        self.initialized = False
        self.camera = None
        
        self.logger.info(f"Mock Daheng camera '{self.camera_name}' initialized successfully")

    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """
        Get available mock Daheng cameras.
        
        Args:
            include_details: If True, return detailed information
            
        Returns:
            List of mock camera names or dict with details
        """
        mock_cameras = [f"mock_daheng_{i}" for i in range(1, 6)]
        
        if include_details:
            camera_details = {}
            for i, camera_name in enumerate(mock_cameras, 1):
                camera_details[camera_name] = {
                    "user_id": camera_name,
                    "serial_number": f"MOCK{i:05d}",
                    "model": "ME2C-2000-6GC",
                    "vendor": "Daheng Imaging",
                    "device_class": "DahengUsb",
                    "interface": f"USB{i}",
                    "friendly_name": f"Daheng ME2C-2000-6GC ({camera_name})",
                    "device_status": "connected"
                }
            return camera_details
        
        return mock_cameras

    async def initialize(self) -> Tuple[bool, Any, Any]:
        """
        Initialize the mock camera connection.
        
        Returns:
            Tuple of (success status, mock camera object, mock remote control object)
            
        Raises:
            CameraNotFoundError: If no cameras found or specified camera not found
            CameraInitializationError: If initialization fails (when simulated)
            CameraConnectionError: If camera connection fails
        """
        if self.fail_init:
            raise CameraInitializationError(f"Simulated initialization failure for mock camera '{self.camera_name}'")
        
        try:
            # Check if camera name exists in available cameras
            available_cameras = self.get_available_cameras()
            if self.camera_name not in available_cameras:
                # Allow any camera name for testing flexibility
                self.logger.debug(f"Mock camera '{self.camera_name}' not in standard list, but allowing for testing")
            
            mock_camera_object = {
                "name": self.camera_name,
                "model": "ME2C-2000-6GC",
                "serial": "MOCK00001",
                "connected": True
            }
            
            mock_remote_control = {
                "type": "mock_remote_control",
                "features": ["exposure", "gain", "trigger", "white_balance"]
            }
            
            # Load config if provided
            if self.camera_config_path and os.path.exists(self.camera_config_path):
                await self.import_config(self.camera_config_path)
            
            # Set initialized flag
            self.initialized = True
            self.logger.info(f"Mock Daheng camera '{self.camera_name}' initialized successfully")
            
            return True, mock_camera_object, mock_remote_control
            
        except (CameraNotFoundError, CameraConnectionError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error initializing mock Daheng camera '{self.camera_name}': {str(e)}")
            raise CameraInitializationError(f"Unexpected error initializing mock camera '{self.camera_name}': {str(e)}")

    async def set_config(self, config: str) -> bool:
        """
        Set camera configuration.
        
        Args:
            config: Configuration string or path
            
        Returns:
            True if configuration was set successfully
        """
        try:
            if os.path.exists(config):
                await self.import_config(config)
                self.logger.info(f"Configuration loaded from '{config}' for camera '{self.camera_name}'")
            else:
                # Simulate setting configuration string
                self.logger.info(f"Configuration string applied for camera '{self.camera_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to set config for camera '{self.camera_name}': {str(e)}")
            return False

    def get_image_quality_enhancement(self) -> bool:
        """Get image quality enhancement setting."""
        return self.img_quality_enhancement

    def set_image_quality_enhancement(self, img_quality_enhancement: bool) -> bool:
        """Set image quality enhancement setting."""
        self.img_quality_enhancement = img_quality_enhancement
        self.logger.info(f"Image quality enhancement {'enabled' if img_quality_enhancement else 'disabled'} for camera '{self.camera_name}'")
        return True

    async def get_triggermode(self) -> str:
        """Get current trigger mode."""
        return self.triggermode

    async def set_triggermode(self, triggermode: str = "continuous") -> bool:
        """
        Set trigger mode.
        
        Args:
            triggermode: Trigger mode ("continuous" or "trigger")
            
        Returns:
            True if trigger mode was set successfully
            
        Raises:
            CameraConfigurationError: If trigger mode is invalid
        """
        if triggermode not in ["continuous", "trigger"]:
            raise CameraConfigurationError(f"Invalid trigger mode: {triggermode}")
        
        self.triggermode = triggermode
        self.logger.info(f"Trigger mode set to '{triggermode}' for camera '{self.camera_name}'")
        return True

    async def get_exposure_range(self) -> List[Union[int, float]]:
        """
        Get the supported exposure time range in microseconds.

        Returns:
            List with [min_exposure, max_exposure] in microseconds
        """
        return [23.0, 1000000.0]

    async def get_exposure(self) -> float:
        """
        Get current exposure time in microseconds.
        
        Returns:
            Current exposure time
        """
        return self.exposure_time

    async def set_exposure(self, exposure: Union[int, float]) -> bool:
        """
        Set the camera exposure time in microseconds.

        Args:
            exposure: Exposure time in microseconds

        Returns:
            True if exposure was set successfully
            
        Raises:
            CameraConfigurationError: If exposure value is out of range
        """
        try:
            exposure_range = await self.get_exposure_range()
            if exposure < exposure_range[0] or exposure > exposure_range[1]:
                raise CameraConfigurationError(
                    f"Exposure {exposure} out of range [{exposure_range[0]}, {exposure_range[1]}]"
                )
            
            self.exposure_time = float(exposure)
            self.logger.info(f"Exposure set to {exposure} for mock camera '{self.camera_name}'")
            return True
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set exposure for mock camera '{self.camera_name}': {str(e)}")
            return False

    async def get_wb(self) -> str:
        """
        Get current white balance mode.
        
        Returns:
            Current white balance mode
        """
        return self.white_balance_mode

    async def set_auto_wb_once(self, value: str) -> bool:
        """
        Set white balance mode.
        
        Args:
            value: White balance mode
            
        Returns:
            True if white balance was set successfully
        """
        try:
            self.white_balance_mode = value
            self.logger.info(f"White balance set to '{value}' for mock camera '{self.camera_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to set white balance for mock camera '{self.camera_name}': {str(e)}")
            return False

    async def capture(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Capture a single image from the mock camera.

        Returns:
            Tuple of (success, image_array) where image_array is BGR format
            
        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            CameraCaptureError: If image capture fails
            CameraTimeoutError: If capture times out
        """
        if not self.initialized:
            raise CameraConnectionError(f"Mock camera '{self.camera_name}' is not initialized")

        if self.fail_capture:
            raise CameraCaptureError(f"Simulated capture failure for mock camera '{self.camera_name}'")
        
        if self.simulate_timeout:
            raise CameraTimeoutError(f"Simulated timeout for mock camera '{self.camera_name}'")

        try:
            # Minimal delay for testing performance - simulate realistic timing
            capture_delay = max(0.001, self.exposure_time / 10000000.0)  # Much faster for testing
            await asyncio.sleep(min(capture_delay, 0.01))  # Cap at 10ms for testing
            
            # Generate synthetic image
            image = self._generate_synthetic_image()
            
            # Apply image enhancement if enabled
            if self.img_quality_enhancement:
                image = self._enhance_image(image)
            
            self.image_counter += 1
            return True, image
            
        except (CameraConnectionError, CameraCaptureError, CameraTimeoutError):
            raise
        except Exception as e:
            self.logger.error(f"Mock capture failed for camera '{self.camera_name}': {str(e)}")
            raise CameraCaptureError(f"Failed to capture image from mock camera '{self.camera_name}': {str(e)}")

    async def close(self):
        """
        Close the mock camera and release resources.
        """
        try:
            self.initialized = False
            self.camera = None
            self.device_manager = None
            self.remote_device_feature = None
            self.logger.info(f"Mock Daheng camera '{self.camera_name}' closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing mock camera '{self.camera_name}': {str(e)}")

    def _generate_synthetic_image(self) -> np.ndarray:
        """
        Generate synthetic test image using vectorized operations for performance.
        
        Returns:
            BGR image array
        """
        try:
            width = self.roi["width"]
            height = self.roi["height"]
            
            # Use vectorized operations for much better performance
            x_coords = np.arange(width)
            y_coords = np.arange(height)
            X, Y = np.meshgrid(x_coords, y_coords)
            
            # Create RGB channels using vectorized operations
            r_channel = (128 + 127 * np.sin(2 * np.pi * X / width)).astype(np.uint8)
            g_channel = (128 + 127 * np.cos(2 * np.pi * Y / height)).astype(np.uint8)
            b_channel = (64 + 64 * np.sin(2 * np.pi * (X + Y) / (width + height))).astype(np.uint8)
            
            # Stack channels (OpenCV uses BGR format)
            image = np.stack([b_channel, g_channel, r_channel], axis=-1)
            
            # Apply exposure effect
            exposure_factor = min(1.0, self.exposure_time / 20000.0)  # Normalize to 20ms
            image = (image * exposure_factor).astype(np.uint8)
            
            # Add gain effect
            if self.gain > 1.0:
                image = np.clip(image * self.gain, 0, 255).astype(np.uint8)
            
            # Add text overlay
            timestamp = time.strftime("%H:%M:%S")
            cv2.putText(image, f"Mock Daheng {timestamp}", (50, 50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(image, f"Frame: {self.image_counter}", (50, 90), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(image, f"Exp: {self.exposure_time:.0f}us", (50, 130), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(image, f"Gain: {self.gain:.1f}", (50, 170), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            return image
            
        except Exception as e:
            self.logger.error(f"Failed to generate synthetic image: {str(e)}")
            # Return simple pattern as fallback
            return np.full((height, width, 3), 128, dtype=np.uint8)

    def _enhance_image(self, image: np.ndarray) -> np.ndarray:
        """
        Apply image enhancement using gamma, contrast, and color correction.

        Args:
            image: Input BGR image

        Returns:
            Enhanced BGR image
        """
        try:
            enhanced_img = image.copy()
            
            # Apply gamma correction if available
            if self.gamma_lut is not None:
                enhanced_img = cv2.LUT(enhanced_img, self.gamma_lut)
            
            # Apply contrast enhancement if available
            if self.contrast_lut is not None:
                enhanced_img = cv2.LUT(enhanced_img, self.contrast_lut)
            
            # Apply color correction if available
            if self.color_correction_param is not None:
                # Convert to float for matrix multiplication
                enhanced_img = enhanced_img.astype(np.float32) / 255.0
                # Apply color correction matrix
                enhanced_img = np.dot(enhanced_img, self.color_correction_param.T)
                # Clip and convert back to uint8
                enhanced_img = np.clip(enhanced_img * 255.0, 0, 255).astype(np.uint8)
            
            return enhanced_img
        except Exception as e:
            self.logger.error(f"Image enhancement failed for mock camera '{self.camera_name}': {str(e)}")
            return image

    async def check_connection(self) -> bool:
        """
        Check if mock camera is connected and operational.
        
        Returns:
            True if connected and operational
        """
        if not self.initialized:
            return False
        
        try:
            # Simulate connection check with test capture
            status, img = await self.capture()
            return status and img is not None and img.shape[0] > 0 and img.shape[1] > 0
        except Exception as e:
            self.logger.warning(f"Mock connection check failed for camera '{self.camera_name}': {str(e)}")
            return False

    async def import_config(self, config_path: str) -> bool:
        """
        Import camera configuration from common JSON format.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            True if configuration was imported successfully
            
        Raises:
            CameraConfigurationError: If configuration file is not found or invalid
        """
        try:
            if not os.path.exists(config_path):
                raise CameraConfigurationError(f"Configuration file not found: {config_path}")
            
            # Simulate configuration import
            await asyncio.sleep(0.01)  # Simulate processing time
            
            # Load JSON configuration
            try:
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                
                # Apply configuration settings using common format
                if 'exposure_time' in config_data:
                    self.exposure_time = float(config_data['exposure_time'])
                if 'gain' in config_data:
                    self.gain = float(config_data['gain'])
                if 'trigger_mode' in config_data:
                    self.triggermode = config_data['trigger_mode']
                if 'white_balance' in config_data:
                    self.white_balance_mode = config_data['white_balance']
                if 'image_enhancement' in config_data:
                    self.img_quality_enhancement = config_data['image_enhancement']
                if 'roi' in config_data:
                    self.roi = config_data['roi']
                if 'retrieve_retry_count' in config_data:
                    self.retrieve_retry_count = config_data['retrieve_retry_count']
                if 'timeout_ms' in config_data:
                    self.timeout_ms = config_data['timeout_ms']
                    
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                raise CameraConfigurationError(f"Invalid JSON configuration format: {e}")
            
            self.logger.info(f"Configuration imported from '{config_path}' for mock camera '{self.camera_name}'")
            return True
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to import config from '{config_path}': {str(e)}")
            raise CameraConfigurationError(f"Failed to import config from '{config_path}': {str(e)}")

    async def export_config(self, config_path: str) -> bool:
        """
        Export camera configuration to common JSON format.
        
        Args:
            config_path: Path to save configuration file
            
        Returns:
            True if configuration was exported successfully, False otherwise
        """
        try:
            # Create common format configuration data
            config_data = {
                "camera_type": "mock_daheng",
                "camera_name": self.camera_name,
                "timestamp": time.time(),
                "exposure_time": self.exposure_time,
                "gain": self.gain,
                "trigger_mode": self.triggermode,
                "white_balance": self.white_balance_mode,
                "width": self.roi["width"],
                "height": self.roi["height"],
                "roi": self.roi,
                "pixel_format": "BGR8",
                "image_enhancement": self.img_quality_enhancement,
                "retrieve_retry_count": self.retrieve_retry_count,
                "timeout_ms": self.timeout_ms,
                "buffer_count": getattr(self, 'buffer_count', 5)
            }
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            # Write configuration as JSON
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            self.logger.info(f"Configuration exported to '{config_path}' for mock camera '{self.camera_name}' using common JSON format")
            return True
        except Exception as e:
            self.logger.error(f"Failed to export config to '{config_path}': {str(e)}")
            return False

    def set_ROI(self, x: int, y: int, width: int, height: int) -> bool:
        """
        Set Region of Interest (ROI).
        
        Args:
            x: ROI x offset
            y: ROI y offset  
            width: ROI width
            height: ROI height
            
        Returns:
            True if ROI was set successfully
            
        Raises:
            CameraConfigurationError: If ROI parameters are invalid
        """
        try:
            if width <= 0 or height <= 0:
                raise CameraConfigurationError(f"Invalid ROI dimensions: {width}x{height}")
            
            if x < 0 or y < 0:
                raise CameraConfigurationError(f"Invalid ROI offset: ({x}, {y})")
            
            self.roi = {"x": x, "y": y, "width": width, "height": height}
            self.logger.info(f"ROI set to ({x}, {y}, {width}, {height}) for mock camera '{self.camera_name}'")
            return True
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set ROI for mock camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set ROI for mock camera '{self.camera_name}': {str(e)}")

    def get_ROI(self) -> Dict[str, int]:
        """
        Get current Region of Interest (ROI).
        
        Returns:
            Dictionary with ROI parameters
        """
        return self.roi.copy()

    def reset_ROI(self) -> bool:
        """
        Reset ROI to full sensor size.
        
        Returns:
            True if ROI was reset successfully
        """
        try:
            self.roi = {"x": 0, "y": 0, "width": 4024, "height": 3036}
            self.logger.info(f"ROI reset to full size for mock camera '{self.camera_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to reset ROI for mock camera '{self.camera_name}': {str(e)}")
            return False

    def set_gain(self, gain: float) -> bool:
        """
        Set camera gain.
        
        Args:
            gain: Gain value
            
        Returns:
            True if gain was set successfully
            
        Raises:
            CameraConfigurationError: If gain value is out of range
        """
        try:
            if gain < 1.0 or gain > 16.0:
                raise CameraConfigurationError(f"Gain {gain} out of range [1.0, 16.0]")
            
            self.gain = gain
            self.logger.info(f"Gain set to {gain} for mock camera '{self.camera_name}'")
            return True
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set gain for mock camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set gain for mock camera '{self.camera_name}': {str(e)}")

    def get_gain(self) -> float:
        """
        Get current camera gain.
        
        Returns:
            Current gain value
        """
        return self.gain

    def get_gain_range(self) -> List[Union[int, float]]:
        """
        Get camera gain range.
        
        Returns:
            List containing [min_gain, max_gain]
        """
        return [1.0, 16.0]

    def get_wb_range(self) -> List[str]:
        """
        Get available white balance modes.
        
        Returns:
            List of available white balance modes
        """
        return ["off", "auto", "continuous", "once"]

    def get_pixel_format_range(self) -> List[str]:
        """
        Get available pixel formats.
        
        Returns:
            List of available pixel formats
        """
        return ["BGR8", "RGB8", "Mono8", "BayerRG8", "BayerGB8", "BayerGR8", "BayerBG8"]

    def get_current_pixel_format(self) -> str:
        """
        Get current pixel format.
        
        Returns:
            Current pixel format
        """
        return "BGR8"  # Mock cameras always output BGR

    def set_pixel_format(self, pixel_format: str) -> bool:
        """
        Set pixel format.
        
        Args:
            pixel_format: Pixel format to set
            
        Returns:
            True if pixel format was set successfully
            
        Raises:
            CameraConfigurationError: If pixel format is not supported
        """
        try:
            available_formats = self.get_pixel_format_range()
            if pixel_format not in available_formats:
                raise CameraConfigurationError(f"Unsupported pixel format: {pixel_format}")
            
            # Mock implementation - just log the change
            self.logger.info(f"Pixel format set to '{pixel_format}' for mock camera '{self.camera_name}'")
            return True
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set pixel format for mock camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set pixel format for mock camera '{self.camera_name}': {str(e)}")

    # Additional methods for compatibility with real Daheng camera

    async def get_width_range(self) -> List[int]:
        """
        Get camera width range in pixels.
        
        Returns:
            List with [min_width, max_width] in pixels
        """
        return [4, self.roi["width"]]

    async def get_height_range(self) -> List[int]:
        """
        Get camera height range in pixels.
        
        Returns:
            List with [min_height, max_height] in pixels
        """
        return [2, self.roi["height"]]
