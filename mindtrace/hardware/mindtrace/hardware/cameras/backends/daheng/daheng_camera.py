"""
Daheng Camera Backend Implementation

This module provides a comprehensive implementation for Daheng cameras using the gxipy SDK.
It supports advanced camera features including trigger modes, exposure control, ROI settings,
and image quality enhancement.

Features:
    - Full Daheng camera support via gxipy SDK
    - Hardware trigger and continuous capture modes
    - ROI (Region of Interest) control
    - Automatic exposure and gain control
    - Image quality enhancement with gamma, contrast, and color correction
    - Configuration import/export functionality
    - Robust error handling and connection management

Requirements:
    - gxipy SDK (Galaxy SDK for Python)
    - OpenCV for image processing
    - Daheng Galaxy SDK installed on system

Installation:
    1. Install Daheng Galaxy SDK from manufacturer
    2. pip install git+https://github.com/Mindtrace/gxipy.git@gxipy_deploy
    3. Configure camera permissions (Linux may require udev rules)

Usage:
    from mindtrace.hardware.cameras.backends.daheng import DahengCamera
    
    # Get available cameras
    cameras = DahengCamera.get_available_cameras()
    
    # Initialize camera
    camera = DahengCamera("camera_name", img_quality_enhancement=True)
    success, cam_obj, remote_obj = await camera.initialize()  # Initialize first
    
    if success:
        # Configure and capture
        await camera.set_exposure(20000)
        await camera.set_triggermode("continuous")
        success, image = await camera.capture()
        await camera.close()

Configuration:
    All parameters are configurable via the hardware configuration system:
    - MINDTRACE_CAMERA_EXPOSURE_TIME: Default exposure time in microseconds
    - MINDTRACE_CAMERA_TRIGGER_MODE: Default trigger mode ("continuous" or "trigger")
    - MINDTRACE_CAMERA_IMAGE_QUALITY_ENHANCEMENT: Enable image enhancement
    - MINDTRACE_CAMERA_RETRIEVE_RETRY_COUNT: Number of capture retry attempts
    - MINDTRACE_CAMERA_BUFFER_COUNT: Number of frame buffers for streaming
    - MINDTRACE_CAMERA_TIMEOUT_MS: Capture timeout in milliseconds

Supported Camera Models:
    - All Daheng USB3 cameras (MER, ME series)
    - All Daheng GigE cameras (MER, ME series)
    - Both monochrome and color variants
    - Various resolutions and frame rates

Error Handling:
    The module uses a comprehensive exception hierarchy for precise error reporting:
    - SDKNotAvailableError: gxipy SDK not installed
    - CameraNotFoundError: Camera not detected or accessible
    - CameraInitializationError: Failed to initialize camera
    - CameraConfigurationError: Invalid configuration parameters
    - CameraConnectionError: Connection issues
    - CameraCaptureError: Image acquisition failures
    - CameraTimeoutError: Operation timeout
    - HardwareOperationError: General hardware operation failures
"""

import os
import time
import asyncio
import numpy as np
import cv2
from typing import Optional, List, Tuple, Dict, Any, Union

try:
    import gxipy as gx
    GXIPY_AVAILABLE = True
except ImportError:
    GXIPY_AVAILABLE = False
    gx = None

from mindtrace.hardware.cameras.backends.base import BaseCamera
from mindtrace.hardware.core.exceptions import (
    SDKNotAvailableError, CameraInitializationError, CameraNotFoundError,
    CameraCaptureError, CameraConfigurationError, CameraConnectionError,
    CameraTimeoutError, HardwareOperationError, HardwareTimeoutError
)


class DahengCamera(BaseCamera):
    """Interface for Daheng cameras using gxipy SDK.

    This class provides a comprehensive interface to Daheng cameras, supporting both USB and GigE models.
    It handles camera initialization, configuration, image acquisition, and parameter control with
    robust error handling and configuration management.

    Attributes:
        initialized: Whether camera was successfully initialized
        camera: Underlying gxipy camera object
        remote_device_feature: Camera remote control interface
        triggermode: Current trigger mode ("continuous" or "trigger")
        img_quality_enhancement: Current image enhancement setting
        timeout_ms: Capture timeout in milliseconds
        buffer_count: Number of frame buffers
        retrieve_retry_count: Number of capture retry attempts
        camera_config_path: Path to camera configuration file
        device_manager: Daheng device manager instance
        gamma_lut: Gamma correction lookup table
        contrast_lut: Contrast enhancement lookup table
        color_correction_param: Color correction matrix
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
        Initialize Daheng camera with configurable parameters.

        Args:
            camera_name: Camera identifier (user ID, serial number, or index)
            camera_config: Path to Galaxy configuration (.gxf) file (optional)
            img_quality_enhancement: Enable image enhancement (uses config default if None)
            retrieve_retry_count: Number of capture retry attempts (uses config default if None)
            **backend_kwargs: Backend-specific parameters:
                - buffer_count: Number of frame buffers (uses config default if None)
                - timeout_ms: Capture timeout in milliseconds (uses config default if None)
            
        Raises:
            SDKNotAvailableError: If gxipy SDK is not available
            CameraConfigurationError: If configuration is invalid
            CameraInitializationError: If camera initialization fails
        """
        if not GXIPY_AVAILABLE:
            raise SDKNotAvailableError(
                "gxipy",
                "Install gxipy to use Daheng cameras:\n"
                "1. Download and install Daheng Galaxy SDK from https://www.daheng-imaging.com/\n"
                "2. pip install git+https://github.com/Mindtrace/gxipy.git@gxipy_deploy\n"
                "3. Ensure camera drivers are properly installed"
            )
        
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
        
        # Internal state
        self.device_manager = gx.DeviceManager()
        self.remote_device_feature = None
        self.triggermode = self.camera_config.cameras.trigger_mode
        
        # Image enhancement parameters
        self.gamma_lut = None
        self.contrast_lut = None
        self.color_correction_param = None

        self.logger.info(f"Daheng camera '{self.camera_name}' initialized successfully")

    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """
        Get available Daheng cameras.
        
        Args:
            include_details: If True, return detailed information
            
        Returns:
            List of camera names (user IDs preferred, indices as fallback) or dict with details
            
        Raises:
            SDKNotAvailableError: If Daheng SDK is not available
            HardwareOperationError: If camera discovery fails
        """
        if not GXIPY_AVAILABLE:
            raise SDKNotAvailableError(
                "gxipy", 
                "gxipy SDK not available for camera discovery"
            )
            
        try:
            device_manager = gx.DeviceManager()
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
            raise HardwareOperationError(f"Failed to discover Daheng cameras: {str(e)}")
    
    async def initialize(self) -> Tuple[bool, Any, Any]:
        """
        Initialize the camera connection.
        
        This searches for the camera by name, user ID, or index and establishes
        a connection if found.
        
        Returns:
            Tuple of (success status, camera object, remote_control object)
            
        Raises:
            CameraNotFoundError: If no cameras found or specified camera not found
            CameraInitializationError: If camera initialization fails
            CameraConnectionError: If camera connection fails
        """
        try:
            dev_cnt, dev_info_list = self.device_manager.update_device_list()
            if dev_cnt == 0:
                raise CameraNotFoundError("No Daheng cameras found")
            
            camera_found = False
            for index, dev_info in enumerate(dev_info_list):
                if (dev_info.get("user_id") == self.camera_name or 
                    dev_info.get("serial_number") == self.camera_name or
                    str(index) == self.camera_name):
                    camera_found = True
                    try:
                        camera = await asyncio.to_thread(
                            self.device_manager.open_device_by_index, index + 1
                        )
                        remote_control = await asyncio.to_thread(
                            camera.get_remote_device_feature_control
                        )
                        
                        # Configure the camera after opening
                        self.camera = camera
                        self.remote_device_feature = remote_control
                        await self._configure_camera()
                        
                        # Load config if provided
                        if self.camera_config_path and os.path.exists(self.camera_config_path):
                            await self.import_config(self.camera_config_path)
                        
                        # Start streaming
                        await asyncio.to_thread(camera.stream_on)
                        
                        self.initialized = True
                        return True, camera, remote_control
                        
                    except Exception as e:
                        self.logger.error(f"Failed to open Daheng camera '{self.camera_name}': {str(e)}")
                        if camera:
                            try:
                                await asyncio.to_thread(camera.close_device)
                            except Exception as e:
                                self.logger.warning(f"Could not close failed camera device: {e}")
                        raise CameraConnectionError(f"Failed to open camera '{self.camera_name}': {str(e)}")
            
            if not camera_found:
                available_cameras = [
                    f"{dev_info.get('user_id', f'camera_{i}')} ({dev_info.get('serial_number', 'unknown')})" 
                    for i, dev_info in enumerate(dev_info_list)
                ]
                raise CameraNotFoundError(
                    f"Camera '{self.camera_name}' not found. Available cameras: {available_cameras}"
                )
                
        except (CameraNotFoundError, CameraConnectionError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error initializing Daheng camera '{self.camera_name}': {str(e)}")
            raise CameraInitializationError(f"Unexpected error initializing camera '{self.camera_name}': {str(e)}")

    async def _configure_camera(self):
        """
        Configure initial camera settings.
        
        Raises:
            CameraConfigurationError: If camera configuration fails
        """
        try:
            # Configure stream buffer handling
            await self._configure_stream_buffer()
            
            # Initialize image enhancement if enabled
            if self.img_quality_enhancement:
                self.gamma_lut, self.contrast_lut, self.color_correction_param = self._initialize_image_enhancement()
            
            self.logger.info(f"Daheng camera '{self.camera_name}' configured with buffer_count={self.buffer_count}")
                
        except Exception as e:
            self.logger.error(f"Failed to configure Daheng camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to configure camera '{self.camera_name}': {str(e)}")

    async def _configure_stream_buffer(self):
        """
        Configure stream buffer handling mode.
        
        Raises:
            CameraConfigurationError: If stream buffer configuration fails
        """
        try:
            stream = await asyncio.to_thread(self.camera.get_stream, 1)
            
            if hasattr(stream, "get_feature_control"):
                stream_control = await asyncio.to_thread(stream.get_feature_control)
            elif hasattr(stream, "get_featrue_control"):  # Handle typo in some SDK versions
                stream_control = await asyncio.to_thread(stream.get_featrue_control)
            else:
                raise CameraConfigurationError("Camera stream does not support feature control")

            stream_buffer_handling_mode = await asyncio.to_thread(
                stream_control.get_enum_feature, "StreamBufferHandlingMode"
            )
            await asyncio.to_thread(stream_buffer_handling_mode.set, 3)
            
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.warning(f"Failed to configure stream buffer for camera '{self.camera_name}': {str(e)}")
            # Don't raise here as this is not critical for basic operation

    def _initialize_image_enhancement(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Initialize image quality enhancement parameters.
        
        Returns:
            Tuple of (gamma_lut, contrast_lut, color_correction_param)
            
        Raises:
            CameraConfigurationError: If image enhancement initialization fails
        """
        try:
            # Gamma correction lookup table
            gamma_value = 2.2
            gamma_lut = np.array([
                ((i / 255.0) ** (1.0 / gamma_value)) * 255 
                for i in np.arange(0, 256)
            ]).astype("uint8")
            
            # Contrast enhancement lookup table
            contrast_factor = 1.2
            contrast_lut = np.array([
                np.clip((i - 127) * contrast_factor + 127, 0, 255) 
                for i in np.arange(0, 256)
            ]).astype("uint8")
            
            # Color correction matrix
            color_correction_param = np.array([
                [1.2, 0.0, 0.0],
                [0.0, 1.1, 0.0],
                [0.0, 0.0, 1.3]
            ], dtype=np.float32)
            
            self.logger.debug(f"Image enhancement initialized for camera '{self.camera_name}'")
            return gamma_lut, contrast_lut, color_correction_param
            
        except Exception as e:
            self.logger.error(f"Failed to initialize image enhancement for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to initialize image enhancement for camera '{self.camera_name}': {str(e)}")

    def get_image_quality_enhancement(self) -> bool:
        """Get image quality enhancement setting."""
        return self.img_quality_enhancement

    def set_image_quality_enhancement(self, value: bool) -> bool:
        """Set image quality enhancement setting."""
        self.img_quality_enhancement = value
        if value and not all([self.gamma_lut is not None, self.contrast_lut is not None, self.color_correction_param is not None]):
            self.gamma_lut, self.contrast_lut, self.color_correction_param = self._initialize_image_enhancement()
        self.logger.info(f"Image quality enhancement set to {value} for camera '{self.camera_name}'")
        return True

    async def get_exposure_range(self) -> List[Union[int, float]]:
        """
        Get the supported exposure time range in microseconds.

        Returns:
            List with [min_exposure, max_exposure] in microseconds
            
        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            HardwareOperationError: If exposure range retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
            
        try:
            exposure_dict = await asyncio.to_thread(self.camera.ExposureTime.get_range)
            return [exposure_dict["min"], exposure_dict["max"]]
        except Exception as e:
            self.logger.error(f"Error getting exposure range for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get exposure range: {str(e)}")

    async def get_exposure(self) -> float:
        """
        Get current exposure time in microseconds.
        
        Returns:
            Current exposure time
            
        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            HardwareOperationError: If exposure retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
            
        try:
            exposure = await asyncio.to_thread(self.camera.ExposureTime.get)
            return exposure
        except Exception as e:
            self.logger.error(f"Error getting exposure for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get exposure: {str(e)}")

    async def set_exposure(self, exposure: Union[int, float]) -> bool:
        """
        Set the camera exposure time in microseconds.

        Args:
            exposure: Exposure time in microseconds

        Returns:
            True if exposure was set successfully
            
        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            CameraConfigurationError: If exposure value is out of range
            HardwareOperationError: If exposure setting fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
            
        try:
            min_exp, max_exp = await self.get_exposure_range()
            
            if exposure < min_exp or exposure > max_exp:
                raise CameraConfigurationError(
                    f"Exposure {exposure} outside valid range [{min_exp}, {max_exp}] "
                    f"for camera '{self.camera_name}'"
                )

            await asyncio.to_thread(self.camera.ExposureTime.set, exposure)
            
            # Verify the setting
            actual_exposure = await asyncio.to_thread(self.camera.ExposureTime.get)
            success = abs(actual_exposure - exposure) < 0.01 * exposure

            if not success:
                self.logger.warning(f"Exposure setting verification failed for camera '{self.camera_name}'")

            return success
            
        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Error setting exposure for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set exposure: {str(e)}")

    async def get_triggermode(self) -> str:
        """
        Get current trigger mode.
        
        Returns:
            "continuous" or "trigger"
            
        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            HardwareOperationError: If trigger mode retrieval fails
        """
        if not self.initialized or self.camera is None:
            return self.triggermode
            
        try:
            trigger_mode_value = await asyncio.to_thread(self.camera.TriggerMode.get)
            return "continuous" if trigger_mode_value and trigger_mode_value[0] == 0 else "trigger"
        except Exception as e:
            self.logger.error(f"Error getting trigger mode for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get trigger mode: {str(e)}")

    async def set_triggermode(self, triggermode: str = "continuous") -> bool:
        """
        Set the camera trigger mode.

        Args:
            triggermode: "continuous" for free-running, "trigger" for hardware trigger

        Returns:
            True if trigger mode was set successfully
            
        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            CameraConfigurationError: If trigger mode is invalid
            HardwareOperationError: If trigger mode setting fails
        """
        if triggermode not in ["continuous", "trigger"]:
            raise CameraConfigurationError(f"Invalid trigger mode '{triggermode}'. Must be 'continuous' or 'trigger'")
            
        if not self.initialized or self.camera is None:
            self.triggermode = triggermode
            return True
            
        try:
            if triggermode == "continuous":
                await asyncio.to_thread(self.camera.TriggerMode.set, gx.GxSwitchEntry.OFF)
            else:
                await asyncio.to_thread(self.camera.TriggerMode.set, gx.GxSwitchEntry.ON)
                
            self.triggermode = triggermode
            self.logger.info(f"Trigger mode set to '{triggermode}' for camera '{self.camera_name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Error setting trigger mode for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set trigger mode: {str(e)}")

    async def capture(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Capture an image from the camera.
        
        Returns:
            Tuple of (success, image_array) where image_array is BGR format
            
        Raises:
            CameraConnectionError: If camera is not connected
            CameraCaptureError: If image capture fails
            CameraTimeoutError: If capture times out
        """
        if not self.initialized or not self.camera:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not connected")
            
        for attempt in range(self.retrieve_retry_count):
            try:
                if self.triggermode == "trigger":
                    self.camera.TriggerSoftware.send_command()
                
                raw_image = self.camera.data_stream[0].get_image()
                if raw_image is None:
                    if attempt == self.retrieve_retry_count - 1:
                        raise CameraTimeoutError(f"No image received from camera '{self.camera_name}' after {self.retrieve_retry_count} attempts")
                    # Use debug for first attempt, warning for subsequent attempts
                    if attempt == 0:
                        self.logger.debug(f"No image received from camera '{self.camera_name}', attempt {attempt + 1} (normal for first capture)")
                    else:
                        self.logger.warning(f"No image received from camera '{self.camera_name}', attempt {attempt + 1}")
                    continue
                
                numpy_image = raw_image.get_numpy_array()
                if numpy_image is None:
                    if attempt == self.retrieve_retry_count - 1:
                        raise CameraCaptureError(f"Failed to convert image to numpy array for camera '{self.camera_name}' after {self.retrieve_retry_count} attempts")
                    self.logger.warning(f"Failed to convert image to numpy array for camera '{self.camera_name}', attempt {attempt + 1}")
                    continue
                
                if len(numpy_image.shape) == 3:
                    bgr_image = cv2.cvtColor(numpy_image, cv2.COLOR_RGB2BGR)
                else:
                    bgr_image = cv2.cvtColor(numpy_image, cv2.COLOR_BAYER_RG2BGR)
                
                if self.img_quality_enhancement and all([
                    self.gamma_lut is not None,
                    self.contrast_lut is not None,
                    self.color_correction_param is not None
                ]):
                    try:
                        bgr_image = cv2.LUT(bgr_image, self.gamma_lut)
                        bgr_image = cv2.LUT(bgr_image, self.contrast_lut)
                        bgr_image = cv2.transform(bgr_image, self.color_correction_param)
                    except Exception as e:
                        self.logger.warning(f"Image enhancement failed for camera '{self.camera_name}': {str(e)}")
                
                self.logger.debug(f"Image captured successfully from camera '{self.camera_name}', shape: {bgr_image.shape}")
                return True, bgr_image
                
            except (CameraConnectionError, CameraCaptureError, CameraTimeoutError):
                raise
            except Exception as e:
                self.logger.warning(
                    f"Capture attempt {attempt + 1} failed for camera '{self.camera_name}': {str(e)}"
                )
                if attempt == self.retrieve_retry_count - 1:
                    self.logger.error(f"All capture attempts failed for camera '{self.camera_name}': {str(e)}")
                    raise CameraCaptureError(f"All capture attempts failed for camera '{self.camera_name}': {str(e)}")
        
        raise CameraCaptureError(f"Unexpected capture failure for camera '{self.camera_name}'")

    async def check_connection(self) -> bool:
        """
        Check if camera connection is active.
        
        Returns:
            True if connected, False otherwise
            
        Raises:
            CameraConnectionError: If connection check fails
        """
        if not self.initialized or not self.camera:
            return False
        try:
            _ = self.camera.ExposureTime.get()
            return True
        except Exception as e:
            self.logger.warning(f"Connection check failed for camera '{self.camera_name}': {str(e)}")
            raise CameraConnectionError(f"Connection check failed for camera '{self.camera_name}': {str(e)}")

    async def import_config(self, config_path: str) -> bool:
        """
        Import camera configuration from common JSON format.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            CameraConfigurationError: If configuration import fails
        """
        if not os.path.exists(config_path):
            raise CameraConfigurationError(f"Configuration file not found: {config_path}")
        
        try:
            import json
            
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            # Stop streaming for configuration
            was_streaming = False
            try:
                if hasattr(self.camera, 'is_streaming') and self.camera.is_streaming():
                    was_streaming = True
                    self.camera.stream_off()
            except Exception as e:
                self.logger.warning(f"Could not check/stop streaming for camera '{self.camera_name}': {e}")
            
            # Apply settings
            success_count = 0
            total_settings = 0
            
            # Set exposure time
            if 'exposure_time' in config_data:
                total_settings += 1
                try:
                    await asyncio.to_thread(self.camera.ExposureTime.set, float(config_data['exposure_time']))
                    success_count += 1
                except Exception as e:
                    self.logger.warning(f"Could not set exposure time for camera '{self.camera_name}': {e}")
            
            # Set gain
            if 'gain' in config_data and hasattr(self.camera, 'Gain'):
                total_settings += 1
                try:
                    await asyncio.to_thread(self.camera.Gain.set, float(config_data['gain']))
                    success_count += 1
                except Exception as e:
                    self.logger.warning(f"Could not set gain for camera '{self.camera_name}': {e}")
            
            # Set trigger mode
            if 'trigger_mode' in config_data and hasattr(self.camera, 'TriggerMode'):
                total_settings += 1
                try:
                    if config_data['trigger_mode'] == 'trigger':
                        await asyncio.to_thread(self.camera.TriggerMode.set, gx.GxSwitchEntry.ON)
                    else:
                        await asyncio.to_thread(self.camera.TriggerMode.set, gx.GxSwitchEntry.OFF)
                    success_count += 1
                except Exception as e:
                    self.logger.warning(f"Could not set trigger mode for camera '{self.camera_name}': {e}")
            
            # Set white balance
            if 'white_balance' in config_data and hasattr(self.camera, 'BalanceWhiteAuto'):
                total_settings += 1
                try:
                    wb_mode = config_data['white_balance']
                    if wb_mode == 'continuous':
                        await asyncio.to_thread(self.camera.BalanceWhiteAuto.set, gx.GxAutoEntry.CONTINUOUS)
                    elif wb_mode == 'once':
                        await asyncio.to_thread(self.camera.BalanceWhiteAuto.set, gx.GxAutoEntry.ONCE)
                    else:
                        await asyncio.to_thread(self.camera.BalanceWhiteAuto.set, gx.GxAutoEntry.OFF)
                    success_count += 1
                except Exception as e:
                    self.logger.warning(f"Could not set white balance for camera '{self.camera_name}': {e}")
            
            # Set ROI
            if 'roi' in config_data:
                roi = config_data['roi']
                roi_success = 0
                
                try:
                    if hasattr(self.camera, 'OffsetX'):
                        await asyncio.to_thread(self.camera.OffsetX.set, int(roi.get('x', 0)))
                        roi_success += 1
                except Exception as e:
                    self.logger.warning(f"Could not set ROI OffsetX for camera '{self.camera_name}': {e}")
                
                try:
                    if hasattr(self.camera, 'OffsetY'):
                        await asyncio.to_thread(self.camera.OffsetY.set, int(roi.get('y', 0)))
                        roi_success += 1
                except Exception as e:
                    self.logger.warning(f"Could not set ROI OffsetY for camera '{self.camera_name}': {e}")
                
                try:
                    if hasattr(self.camera, 'Width'):
                        await asyncio.to_thread(self.camera.Width.set, int(roi.get('width', 4024)))
                        roi_success += 1
                except Exception as e:
                    self.logger.warning(f"Could not set ROI Width for camera '{self.camera_name}': {e}")
                
                try:
                    if hasattr(self.camera, 'Height'):
                        await asyncio.to_thread(self.camera.Height.set, int(roi.get('height', 3036)))
                        roi_success += 1
                except Exception as e:
                    self.logger.warning(f"Could not set ROI Height for camera '{self.camera_name}': {e}")
                
                if roi_success > 0:
                    success_count += 1
                total_settings += 1
            
            # Apply other settings
            if 'image_enhancement' in config_data:
                self.img_quality_enhancement = config_data['image_enhancement']
                success_count += 1
                total_settings += 1
            
            if 'retrieve_retry_count' in config_data:
                self.retrieve_retry_count = config_data['retrieve_retry_count']
                success_count += 1
                total_settings += 1
            
            if 'timeout_ms' in config_data:
                self.timeout_ms = config_data['timeout_ms']
                success_count += 1
                total_settings += 1
            
            # Restart streaming if it was running
            if was_streaming:
                try:
                    self.camera.stream_on()
                except Exception as e:
                    self.logger.warning(f"Could not restart streaming: {e}")
            
            self.logger.info(
                f"Configuration imported from '{config_path}' for camera '{self.camera_name}': "
                f"{success_count}/{total_settings} settings applied successfully"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to import config from '{config_path}': {str(e)}")
            raise CameraConfigurationError(f"Failed to import config: {str(e)}")

    async def export_config(self, config_path: str) -> bool:
        """
        Export camera configuration to common JSON format.
        
        Args:
            config_path: Path to save configuration file
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            CameraConnectionError: If camera is not connected
            CameraConfigurationError: If configuration export fails
        """
        if not self.initialized or not self.camera:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not connected")
        
        try:
            import json
            
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            # Default configuration values for Daheng cameras
            defaults = {
                "exposure_time": 75000.0,
                "gain": 0.0,
                "trigger_mode": "continuous",
                "white_balance": "off",
                "width": 4024,
                "height": 3036,
                "roi_x": 0,
                "roi_y": 0,
                "pixel_format": "BayerRG12"
            }
            
            # Get current camera settings with fallbacks
            exposure_time = defaults["exposure_time"]
            try:
                exposure_time = await asyncio.to_thread(self.camera.ExposureTime.get)
            except Exception as e:
                self.logger.warning(f"Could not get exposure time for camera '{self.camera_name}': {e}")
            
            gain = defaults["gain"]
            try:
                if hasattr(self.camera, 'Gain'):
                    gain = await asyncio.to_thread(self.camera.Gain.get)
            except Exception as e:
                self.logger.warning(f"Could not get gain for camera '{self.camera_name}': {e}")
            
            trigger_mode = defaults["trigger_mode"]
            try:
                if hasattr(self.camera, 'TriggerMode'):
                    trigger_mode_value = await asyncio.to_thread(self.camera.TriggerMode.get)
                    trigger_mode = "trigger" if trigger_mode_value == gx.GxSwitchEntry.ON else "continuous"
            except Exception as e:
                self.logger.warning(f"Could not get trigger mode for camera '{self.camera_name}': {e}")
            
            white_balance = defaults["white_balance"]
            try:
                if hasattr(self.camera, 'BalanceWhiteAuto'):
                    wb_mode = await asyncio.to_thread(self.camera.BalanceWhiteAuto.get)
                    if wb_mode == gx.GxAutoEntry.CONTINUOUS:
                        white_balance = "continuous"
                    elif wb_mode == gx.GxAutoEntry.ONCE:
                        white_balance = "once"
                    else:
                        white_balance = "off"
            except Exception as e:
                self.logger.warning(f"Could not get white balance for camera '{self.camera_name}': {e}")
            
            # Get image dimensions
            width = defaults["width"]
            height = defaults["height"]
            try:
                if hasattr(self.camera, 'Width'):
                    width = int(await asyncio.to_thread(self.camera.Width.get))
                if hasattr(self.camera, 'Height'):
                    height = int(await asyncio.to_thread(self.camera.Height.get))
            except Exception as e:
                self.logger.warning(f"Could not get image dimensions for camera '{self.camera_name}': {e}")
            
            # Get ROI
            roi_x = defaults["roi_x"]
            roi_y = defaults["roi_y"]
            try:
                if hasattr(self.camera, 'OffsetX'):
                    roi_x = int(await asyncio.to_thread(self.camera.OffsetX.get))
                if hasattr(self.camera, 'OffsetY'):
                    roi_y = int(await asyncio.to_thread(self.camera.OffsetY.get))
            except Exception as e:
                self.logger.warning(f"Could not get ROI offsets for camera '{self.camera_name}': {e}")
            
            # Get pixel format
            pixel_format = defaults["pixel_format"]
            try:
                if hasattr(self.camera, 'PixelFormat'):
                    pf = await asyncio.to_thread(self.camera.PixelFormat.get)
                    # Map Daheng pixel formats to common names
                    if pf == gx.GxPixelFormatEntry.BGR8:
                        pixel_format = "BGR8"
                    elif pf == gx.GxPixelFormatEntry.RGB8:
                        pixel_format = "RGB8"
                    elif pf == gx.GxPixelFormatEntry.MONO8:
                        pixel_format = "Mono8"
            except Exception as e:
                self.logger.warning(f"Could not get pixel format for camera '{self.camera_name}': {e}")
            
            # Create common format configuration
            config_data = {
                "camera_type": "daheng",
                "camera_name": self.camera_name,
                "timestamp": time.time(),
                "exposure_time": exposure_time,
                "gain": gain,
                "trigger_mode": trigger_mode,
                "white_balance": white_balance,
                "width": width,
                "height": height,
                "roi": {"x": roi_x, "y": roi_y, "width": width, "height": height},
                "pixel_format": pixel_format,
                "image_enhancement": self.img_quality_enhancement,
                "retrieve_retry_count": self.retrieve_retry_count,
                "timeout_ms": self.timeout_ms,
                "buffer_count": getattr(self, 'buffer_count', 5)
            }
            
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            self.logger.info(f"Configuration exported to '{config_path}' for camera '{self.camera_name}' using common JSON format")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export config to '{config_path}' for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to export config to '{config_path}' for camera '{self.camera_name}': {str(e)}")

    async def set_config(self, config: str) -> bool:
        """
        Set the camera configuration from file.
        
        Args:
            config: Path to configuration file
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            CameraConnectionError: If camera is not connected
            CameraConfigurationError: If configuration cannot be applied
        """
        if not self.initialized or not self.camera:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not connected")
        
        if not os.path.exists(config):
            raise CameraConfigurationError(f"Configuration file not found: {config}")
        
        try:
            self.camera.stream_off()
            self.camera.import_config_file(config)
            self.camera.stream_on()
            self.logger.info(f"Configuration loaded from '{config}' for camera '{self.camera_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to set config from '{config}' for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set config from '{config}' for camera '{self.camera_name}': {str(e)}")

    async def close(self):
        """
        Close camera connection and cleanup resources.
        
        Raises:
            CameraConnectionError: If camera closure fails
        """
        try:
            if self.camera is not None:
                if self.initialized:
                    self.camera.stream_off()
                self.camera.close_device()
                self.logger.info(f"Camera '{self.camera_name}' closed successfully")
        except Exception as e:
            self.logger.warning(f"Error closing camera '{self.camera_name}': {str(e)}")
            raise CameraConnectionError(f"Error closing camera '{self.camera_name}': {str(e)}")
        finally:
            self.camera = None
            self.remote_device_feature = None
            self.initialized = False

    # Additional methods for compatibility and completeness
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
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not available for gain setting")
        
        try:
            # Validate gain range
            gain_range = self.get_gain_range()
            if gain < gain_range[0] or gain > gain_range[1]:
                raise CameraConfigurationError(f"Gain {gain} out of range [{gain_range[0]}, {gain_range[1]}]")
            
            self.camera.Gain.set(float(gain))
            self.logger.info(f"Gain set to {gain} for camera '{self.camera_name}'")
            return True
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
        if not self.initialized or self.camera is None:
            return 1.0
        
        try:
            gain = self.camera.Gain.get()
            return float(gain)
        except Exception as e:
            self.logger.error(f"Failed to get gain for camera '{self.camera_name}': {str(e)}")
            return 1.0

    def get_gain_range(self) -> List[Union[int, float]]:
        """
        Get camera gain range.
        
        Returns:
            List containing [min_gain, max_gain]
        """
        if not self.initialized or self.camera is None:
            return [1.0, 16.0]
        
        try:
            gain_range = self.camera.Gain.get_range()
            return [gain_range["min"], gain_range["max"]]
        except Exception as e:
            self.logger.error(f"Failed to get gain range for camera '{self.camera_name}': {str(e)}")
            return [1.0, 16.0]

    def get_wb_range(self) -> List[str]:
        """
        Get available white balance modes.
        
        Returns:
            List of available white balance modes
        """
        return ["off", "auto", "continuous", "once"]

    async def get_width_range(self) -> List[int]:
        """
        Get camera width range.
        
        Returns:
            List containing [min_width, max_width]
        """
        if not self.initialized or self.camera is None:
            return [640, 1920]
        
        try:
            width_range = self.camera.Width.get_range()
            return [width_range["min"], width_range["max"]]
        except Exception as e:
            self.logger.error(f"Failed to get width range for camera '{self.camera_name}': {str(e)}")
            return [640, 1920]

    async def get_height_range(self) -> List[int]:
        """
        Get camera height range.
        
        Returns:
            List containing [min_height, max_height]
        """
        if not self.initialized or self.camera is None:
            return [480, 1080]
        
        try:
            height_range = self.camera.Height.get_range()
            return [height_range["min"], height_range["max"]]
        except Exception as e:
            self.logger.error(f"Failed to get height range for camera '{self.camera_name}': {str(e)}")
            return [480, 1080]

    async def get_wb(self) -> str:
        """
        Get current white balance mode.
        
        Returns:
            Current white balance mode
        """
        if not self.initialized or self.camera is None:
            return "off"
        
        try:
            if hasattr(self.camera, 'BalanceWhiteAuto'):
                wb_mode = await asyncio.to_thread(self.camera.BalanceWhiteAuto.get)
                if wb_mode == gx.GxAutoEntry.CONTINUOUS:
                    return "continuous"
                elif wb_mode == gx.GxAutoEntry.ONCE:
                    return "once"
                else:
                    return "off"
            return "off"
        except Exception as e:
            self.logger.error(f"Failed to get white balance for camera '{self.camera_name}': {str(e)}")
            return "off"

    async def set_auto_wb_once(self, value: str) -> bool:
        """
        Set white balance mode.
        
        Args:
            value: White balance mode ("off", "once", "continuous")
            
        Returns:
            True if white balance was set successfully
        """
        if not self.initialized or self.camera is None:
            self.logger.error(f"Camera '{self.camera_name}' not available for white balance setting")
            return False
        
        try:
            if not hasattr(self.camera, 'BalanceWhiteAuto'):
                self.logger.warning(f"White balance not supported by camera '{self.camera_name}'")
                return False
            
            if value.lower() == "continuous":
                await asyncio.to_thread(self.camera.BalanceWhiteAuto.set, gx.GxAutoEntry.CONTINUOUS)
            elif value.lower() == "once":
                await asyncio.to_thread(self.camera.BalanceWhiteAuto.set, gx.GxAutoEntry.ONCE)
            else:  # "off" or any other value
                await asyncio.to_thread(self.camera.BalanceWhiteAuto.set, gx.GxAutoEntry.OFF)
            
            self.logger.info(f"White balance set to '{value}' for camera '{self.camera_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to set white balance for camera '{self.camera_name}': {str(e)}")
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
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If ROI parameters are invalid or setting fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not available for ROI setting")
        
        try:
            if width <= 0 or height <= 0:
                raise CameraConfigurationError(f"Invalid ROI dimensions: {width}x{height}")
            
            if x < 0 or y < 0:
                raise CameraConfigurationError(f"Invalid ROI offset: ({x}, {y})")
            
            # Check against camera limits before setting
            try:
                offset_x_range = self.camera.OffsetX.get_range()
                offset_y_range = self.camera.OffsetY.get_range()
                width_range = self.camera.Width.get_range()
                height_range = self.camera.Height.get_range()
                
                if x < offset_x_range["min"] or x > offset_x_range["max"]:
                    raise CameraConfigurationError(
                        f"OffsetX {x} out of range [{offset_x_range['min']}, {offset_x_range['max']}]"
                    )
                
                if y < offset_y_range["min"] or y > offset_y_range["max"]:
                    raise CameraConfigurationError(
                        f"OffsetY {y} out of range [{offset_y_range['min']}, {offset_y_range['max']}]"
                    )
                
                if width < width_range["min"] or width > width_range["max"]:
                    raise CameraConfigurationError(
                        f"Width {width} out of range [{width_range['min']}, {width_range['max']}]"
                    )
                
                if height < height_range["min"] or height > height_range["max"]:
                    raise CameraConfigurationError(
                        f"Height {height} out of range [{height_range['min']}, {height_range['max']}]"
                    )
                    
            except CameraConfigurationError:
                raise
            except Exception as e:
                self.logger.warning(f"Could not validate ROI ranges: {e}")
            
            # Stop grabbing temporarily for ROI change
            was_grabbing = False
            try:
                # Always try to stop streaming first to make ROI parameters writable
                self.camera.stream_off()
                was_grabbing = True
            except Exception as e:
                # If stream_off fails, camera might not be streaming
                self.logger.warning(f"Could not stop streaming for ROI change on camera '{self.camera_name}': {e}")
                was_grabbing = False
            
            # Set ROI parameters
            self.camera.OffsetX.set(x)
            self.camera.OffsetY.set(y)
            self.camera.Width.set(width)
            self.camera.Height.set(height)
            
            # Restart grabbing if it was running
            if was_grabbing:
                self.camera.stream_on()
            
            self.logger.info(f"ROI set to ({x}, {y}, {width}, {height}) for camera '{self.camera_name}'")
            return True
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set ROI for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set ROI for camera '{self.camera_name}': {str(e)}")

    def get_ROI(self) -> Dict[str, int]:
        """
        Get current Region of Interest (ROI).
        
        Returns:
            Dictionary with ROI parameters
        """
        if not self.initialized or self.camera is None:
            return {"x": 0, "y": 0, "width": 4024, "height": 3036}
        
        try:
            roi = {
                "x": self.camera.OffsetX.get(),
                "y": self.camera.OffsetY.get(),
                "width": self.camera.Width.get(),
                "height": self.camera.Height.get()
            }
            return roi
        except Exception as e:
            self.logger.error(f"Failed to get ROI for camera '{self.camera_name}': {str(e)}")
            return {"x": 0, "y": 0, "width": 4024, "height": 3036}

    def reset_ROI(self) -> bool:
        """
        Reset ROI to full sensor size.
        
        Returns:
            True if ROI was reset successfully, False otherwise
        """
        if not self.initialized or self.camera is None:
            self.logger.error(f"Camera '{self.camera_name}' not available for ROI reset")
            return False
        
        try:
            # Stop grabbing temporarily for ROI change
            was_grabbing = self.camera.is_streaming()
            if was_grabbing:
                self.camera.stream_off()
            
            # Reset to maximum sensor size
            self.camera.OffsetX.set(0)
            self.camera.OffsetY.set(0)
            
            width_range = self.camera.Width.get_range()
            height_range = self.camera.Height.get_range()
            
            self.camera.Width.set(width_range["max"])
            self.camera.Height.set(height_range["max"])
            
            # Restart grabbing if it was running
            if was_grabbing:
                self.camera.stream_on()
            
            self.logger.info(f"ROI reset to full size for camera '{self.camera_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to reset ROI for camera '{self.camera_name}': {str(e)}")
            return False

    def get_pixel_format_range(self) -> List[str]:
        """
        Get available pixel formats.
        
        Returns:
            List of available pixel formats
        """
        if not self.initialized or self.camera is None:
            return ["BGR8", "RGB8", "Mono8", "BayerRG8", "BayerGB8", "BayerGR8", "BayerBG8"]
        
        try:
            # Get available pixel formats from camera
            formats = self.camera.PixelFormat.get_range()
            return list(formats) if formats else ["BGR8", "RGB8", "Mono8"]
        except Exception as e:
            self.logger.error(f"Failed to get pixel format range for camera '{self.camera_name}': {str(e)}")
            return ["BGR8", "RGB8", "Mono8", "BayerRG8", "BayerGB8", "BayerGR8", "BayerBG8"]

    def get_current_pixel_format(self) -> str:
        """
        Get current pixel format.
        
        Returns:
            Current pixel format (string name only)
        """
        if not self.initialized or self.camera is None:
            return "RGB8"
        
        try:
            pixel_format = self.camera.PixelFormat.get()
            # If pixel_format is a tuple like (17301513, 'BayerRG8'), extract the string part
            if isinstance(pixel_format, tuple) and len(pixel_format) >= 2:
                return pixel_format[1]  # Return the string part
            elif isinstance(pixel_format, str):
                return pixel_format
            else:
                # If it's an enum value, try to map it back to string
                return str(pixel_format)
        except Exception as e:
            self.logger.error(f"Failed to get current pixel format for camera '{self.camera_name}': {str(e)}")
            return "RGB8"

    def set_pixel_format(self, pixel_format: str) -> bool:
        """
        Set pixel format.
        
        Args:
            pixel_format: Pixel format to set
            
        Returns:
            True if pixel format was set successfully
            
        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If pixel format is invalid or setting fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not available for pixel format setting")
        
        try:
            available_formats = self.get_pixel_format_range()
            if pixel_format not in available_formats:
                raise CameraConfigurationError(
                    f"Pixel format '{pixel_format}' not supported. "
                    f"Available formats: {available_formats}"
                )
            
            # Stop grabbing temporarily for pixel format change
            was_grabbing = False
            try:
                # Always try to stop streaming first to make pixel format parameters writable
                self.camera.stream_off()
                was_grabbing = True
            except Exception as e:
                # If stream_off fails, camera might not be streaming
                self.logger.warning(f"Could not stop streaming for pixel format change on camera '{self.camera_name}': {e}")
                was_grabbing = False
            
            # Map string pixel format to Daheng enum value
            pixel_format_map = {
                "BGR8": gx.GxPixelFormatEntry.BGR8,
                "RGB8": gx.GxPixelFormatEntry.RGB8,
                "Mono8": gx.GxPixelFormatEntry.MONO8,
                "BayerRG8": gx.GxPixelFormatEntry.BAYER_RG8,
                "BayerGB8": gx.GxPixelFormatEntry.BAYER_GB8,
                "BayerGR8": gx.GxPixelFormatEntry.BAYER_GR8,
                "BayerBG8": gx.GxPixelFormatEntry.BAYER_BG8,
                "BayerRG12": gx.GxPixelFormatEntry.BAYER_RG12,
                "BayerGB12": gx.GxPixelFormatEntry.BAYER_GB12,
                "BayerGR12": gx.GxPixelFormatEntry.BAYER_GR12,
                "BayerBG12": gx.GxPixelFormatEntry.BAYER_BG12,
            }
            
            if pixel_format in pixel_format_map:
                self.camera.PixelFormat.set(pixel_format_map[pixel_format])
            else:
                # Try setting as string if not in map (fallback)
                self.camera.PixelFormat.set(pixel_format)
            
            # Restart grabbing if it was running
            if was_grabbing:
                try:
                    self.camera.stream_on()
                except Exception as e:
                    self.logger.warning(f"Could not restart streaming after pixel format change on camera '{self.camera_name}': {e}")
            
            self.logger.info(f"Pixel format set to '{pixel_format}' for camera '{self.camera_name}'")
            return True
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set pixel format for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set pixel format for camera '{self.camera_name}': {str(e)}")
