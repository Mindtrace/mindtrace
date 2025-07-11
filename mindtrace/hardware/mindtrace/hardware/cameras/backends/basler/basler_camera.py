"""
Basler Camera Backend Implementation

This module provides a comprehensive implementation for Basler cameras using the pypylon SDK.
It supports advanced camera features including trigger modes, exposure control, ROI settings,
and image quality enhancement.

Features:
    - Full Basler camera support via pypylon SDK
    - Hardware trigger and continuous capture modes
    - ROI (Region of Interest) control
    - Automatic exposure and gain control
    - Image quality enhancement with CLAHE
    - Configuration import/export functionality
    - Robust error handling and connection management

Requirements:
    - pypylon SDK (Pylon SDK for Python)
    - OpenCV for image processing
    - Basler Pylon SDK installed on system

Installation:
    1. Install Basler Pylon SDK from manufacturer
    2. pip install pypylon
    3. Configure camera permissions (Linux may require udev rules)

Usage:
    from mindtrace.hardware.cameras.backends.basler import BaslerCamera
    
    # Get available cameras
    cameras = BaslerCamera.get_available_cameras()
    
    # Initialize camera
    camera = BaslerCamera("camera_name", img_quality_enhancement=True)
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
    - MINDTRACE_CAMERA_IMAGE_QUALITY_ENHANCEMENT: Enable CLAHE enhancement
    - MINDTRACE_CAMERA_RETRIEVE_RETRY_COUNT: Number of capture retry attempts
    - MINDTRACE_CAMERA_BUFFER_COUNT: Number of frame buffers for streaming
    - MINDTRACE_CAMERA_TIMEOUT_MS: Capture timeout in milliseconds

Supported Camera Models:
    - All Basler USB3 cameras (acA, daA series)
    - All Basler GigE cameras (acA, daA series)
    - Both monochrome and color variants
    - Various resolutions and frame rates

Error Handling:
    The module uses a comprehensive exception hierarchy for precise error reporting:
    - SDKNotAvailableError: pypylon SDK not installed
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
    from pypylon import pylon
    from pypylon import genicam
    PYPYLON_AVAILABLE = True
except ImportError:
    PYPYLON_AVAILABLE = False
    pylon = None
    genicam = None

from mindtrace.hardware.cameras.backends.base import BaseCamera
from mindtrace.hardware.core.exceptions import (
    SDKNotAvailableError, CameraInitializationError, CameraNotFoundError,
    CameraCaptureError, CameraConfigurationError, CameraConnectionError,
    CameraTimeoutError, HardwareOperationError, HardwareTimeoutError
)


class BaslerCamera(BaseCamera):
    """Interface for Basler cameras using pypylon SDK.

    This class provides a comprehensive interface to Basler cameras, supporting both USB and GigE models.
    It handles camera initialization, configuration, image acquisition, and parameter control with
    robust error handling and configuration management.

    Attributes:
        initialized: Whether camera was successfully initialized
        camera: Underlying pypylon camera object
        triggermode: Current trigger mode ("continuous" or "trigger")
        img_quality_enhancement: Current image enhancement setting
        timeout_ms: Capture timeout in milliseconds
        buffer_count: Number of frame buffers
        converter: Image format converter for pypylon
        retrieve_retry_count: Number of capture retry attempts
        default_pixel_format: Default pixel format for image conversion
        camera_config_path: Path to camera configuration file
        grabbing_mode: Pylon grabbing strategy
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
        Initialize Basler camera with configurable parameters.

        Args:
            camera_name: Camera identifier (serial number, IP, or user-defined name)
            camera_config: Path to Pylon Feature Stream (.pfs) file (optional)
            img_quality_enhancement: Enable CLAHE image enhancement (uses config default if None)
            retrieve_retry_count: Number of capture retry attempts (uses config default if None)
            **backend_kwargs: Backend-specific parameters:
                - pixel_format: Default pixel format (uses config default if None)
                - buffer_count: Number of frame buffers (uses config default if None)
                - timeout_ms: Capture timeout in milliseconds (uses config default if None)
            
        Raises:
            SDKNotAvailableError: If pypylon SDK is not available
            CameraConfigurationError: If configuration is invalid
            CameraInitializationError: If camera initialization fails
        """
        if not PYPYLON_AVAILABLE:
            raise SDKNotAvailableError(
                "pypylon",
                "Install pypylon to use Basler cameras:\n"
                "1. Download and install Basler pylon SDK from https://www.baslerweb.com/en/downloads/software-downloads/\n"
                "2. pip install pypylon\n"
                "3. Ensure camera drivers are properly installed"
            )
        
        super().__init__(camera_name, camera_config, img_quality_enhancement, retrieve_retry_count)
        
        # Get backend-specific configuration with fallbacks
        pixel_format = backend_kwargs.get('pixel_format')
        buffer_count = backend_kwargs.get('buffer_count')
        timeout_ms = backend_kwargs.get('timeout_ms')
        
        if pixel_format is None:
            pixel_format = getattr(self.camera_config, 'pixel_format', 'BGR8')
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
        self.default_pixel_format = pixel_format
        self.buffer_count = buffer_count
        self.timeout_ms = timeout_ms
        
        # Internal state
        self.converter = None
        self.grabbing_mode = pylon.GrabStrategy_LatestImageOnly
        self.triggermode = self.camera_config.cameras.trigger_mode
        self._available_exposure_property = None

        self.logger.info(f"Basler camera '{self.camera_name}' initialized successfully")



    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """
        Get available Basler cameras.
        
        Args:
            include_details: If True, return detailed information
            
        Returns:
            List of camera names (user-defined names preferred, serial numbers as fallback) or dict with details
            
        Raises:
            SDKNotAvailableError: If Basler SDK is not available
            HardwareOperationError: If camera discovery fails
        """
        if not PYPYLON_AVAILABLE:
            raise SDKNotAvailableError(
                "pypylon", 
                "Basler SDK (pypylon) is not available for camera discovery"
            )
        
        try:
            available_cameras = []
            camera_details = {}
            
            devices = pylon.TlFactory.GetInstance().EnumerateDevices()
            
            for device in devices:
                serial_number = device.GetSerialNumber()
                user_defined_name = device.GetUserDefinedName()
                
                camera_identifier = user_defined_name if user_defined_name else serial_number
                available_cameras.append(camera_identifier)
                
                if include_details:
                    camera_details[camera_identifier] = {
                        "serial_number": serial_number,
                        "model": device.GetModelName(),
                        "vendor": device.GetVendorName(),
                        "device_class": device.GetDeviceClass(),
                        "interface": device.GetInterfaceID(),
                        "friendly_name": device.GetFriendlyName(),
                        "user_defined_name": user_defined_name
                    }
            
            return camera_details if include_details else available_cameras
            
        except Exception as e:
            raise HardwareOperationError(f"Failed to discover Basler cameras: {str(e)}")

    async def initialize(self) -> Tuple[bool, Any, Any]:
        """
        Initialize the camera connection.
        
        This searches for the camera by name, serial number, or IP and establishes
        a connection if found.
        
        Returns:
            Tuple of (success status, camera object, None)
            
        Raises:
            CameraNotFoundError: If no cameras found or specified camera not found
            CameraInitializationError: If camera initialization fails
            CameraConnectionError: If camera connection fails
        """
        try:
            all_devices = await asyncio.to_thread(pylon.TlFactory.GetInstance().EnumerateDevices)
            if len(all_devices) == 0:
                raise CameraNotFoundError("No Basler cameras found")
            
            camera_found = False
            for device in all_devices:
                if (device.GetSerialNumber() == self.camera_name or 
                    device.GetUserDefinedName() == self.camera_name):
                    camera_found = True
                    try:
                        camera = await asyncio.to_thread(
                            lambda: pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateDevice(device))
                        )
                        await asyncio.to_thread(camera.Open)
                        
                        if device.GetSerialNumber() == self.camera_name and device.GetUserDefinedName():
                            self.camera_name = device.GetUserDefinedName()
                            self.logger.info(f"Camera found by serial number, using user-defined name: '{self.camera_name}'")
                        
                        # Configure the camera after opening
                        self.camera = camera
                        await self._configure_camera()
                        
                        # Load config if provided
                        if self.camera_config_path and os.path.exists(self.camera_config_path):
                            await self.import_config(self.camera_config_path)
                        
                        self.initialized = True
                        return True, camera, None
                        
                    except Exception as e:
                        self.logger.error(f"Failed to open Basler camera '{self.camera_name}': {str(e)}")
                        raise CameraConnectionError(f"Failed to open camera '{self.camera_name}': {str(e)}")
            
            if not camera_found:
                available_cameras = [f"{device.GetSerialNumber()} ({device.GetUserDefinedName()})" for device in all_devices]
                raise CameraNotFoundError(
                    f"Camera '{self.camera_name}' not found. Available cameras: {available_cameras}"
                )
                
        except (CameraNotFoundError, CameraConnectionError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error initializing Basler camera '{self.camera_name}': {str(e)}")
            raise CameraInitializationError(f"Unexpected error initializing camera '{self.camera_name}': {str(e)}")

    async def _configure_camera(self):
        """
        Configure initial camera settings.
        
        Raises:
            CameraConfigurationError: If camera configuration fails
        """
        try:
            self.converter = pylon.ImageFormatConverter()
            self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

            if not await asyncio.to_thread(self.camera.IsOpen):
                await asyncio.to_thread(self.camera.Open)
                
            await asyncio.to_thread(self.camera.MaxNumBuffer.SetValue, self.buffer_count)
            
            self.logger.info(f"Basler camera '{self.camera_name}' configured with buffer_count={self.buffer_count}")
                
        except Exception as e:
            self.logger.error(f"Failed to configure Basler camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to configure camera '{self.camera_name}': {str(e)}")

    def get_image_quality_enhancement(self) -> bool:
        """Get image quality enhancement setting."""
        return self.img_quality_enhancement

    def set_image_quality_enhancement(self, value: bool) -> bool:
        """Set image quality enhancement setting."""
        self.img_quality_enhancement = value
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
            if not await asyncio.to_thread(self.camera.IsOpen):
                await asyncio.to_thread(self.camera.Open)

            min_value = await asyncio.to_thread(self.camera.ExposureTime.GetMin)
            max_value = await asyncio.to_thread(self.camera.ExposureTime.GetMax)
                
            return [min_value, max_value]
        except Exception as e:
            self.logger.warning(f"Exposure range not available for camera '{self.camera_name}': {str(e)}")
            # Return reasonable defaults if exposure feature is not available
            return [1.0, 1000000.0]  # 1 μs to 1 second

    async def set_exposure(self, exposure: Union[int, float]) -> bool:
        """
        Set the camera exposure time in microseconds.

        Args:
            exposure: Exposure time in microseconds

        Returns:
            True if exposure was set successfully
            
        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If exposure setting fails
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
            if not await asyncio.to_thread(self.camera.IsOpen):
                await asyncio.to_thread(self.camera.Open)
                
            try:
                prop = getattr(self.camera, self._available_exposure_property, "ExposureTime")
                # Convert to int64 and ensure it's a valid integer
                exposure_int = int(exposure)
                await asyncio.to_thread(prop.SetValue, exposure_int)
                self.logger.info(f"Set {self._available_exposure_property} to {exposure_int} μs for camera '{self.camera_name}'")
                return True
            except Exception as e:
                self._available_exposure_property = "ExposureTimeRaw"
                self.logger.warning(f"ExposureTime property not available for camera '{self.camera_name}', using ExposureTimeRaw")
                prop = getattr(self.camera, "ExposureTimeRaw")
                
                # Get the increment value and adjust exposure to be valid
                try:
                    inc = await asyncio.to_thread(prop.GetInc)
                    min_val = await asyncio.to_thread(prop.GetMin)
                    # Adjust exposure to be valid according to increment
                    adjusted_exposure = int(round((exposure - min_val) / inc) * inc + min_val)
                    await asyncio.to_thread(prop.SetValue, adjusted_exposure)
                    self.logger.info(f"Set ExposureTimeRaw to {adjusted_exposure} μs (adjusted from {exposure}) for camera '{self.camera_name}'")
                    return True
                except Exception as e2:
                    # Fallback: try with original value as int
                    exposure_int = int(exposure)
                    await asyncio.to_thread(prop.SetValue, exposure_int)
                    self.logger.info(f"Set ExposureTimeRaw to {exposure_int} μs for camera '{self.camera_name}'")
                    return True
                
        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Exposure setting failed for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set exposure {exposure} on camera '{self.camera_name}': {str(e)}")

    async def get_exposure(self) -> float:
        """
        Get the camera exposure time in microseconds.
        Returns:
            Current exposure time
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
        try:
            if not await asyncio.to_thread(self.camera.IsOpen):
                await asyncio.to_thread(self.camera.Open)
            
            try:
                prop = getattr(self.camera, self._available_exposure_property, "ExposureTime")
                value = await asyncio.to_thread(prop.GetValue)
                return float(value)
            except Exception as e:
                self._available_exposure_property = "ExposureTimeRaw"
                self.logger.warning (f"ExposureTime property not available for camera '{self.camera_name}', using ExposureTimeRaw")
                prop = getattr(self.camera, "ExposureTimeRaw")
                value = await asyncio.to_thread(prop.GetValue)
                return float(value)
        except Exception as e:
            self.logger.error(f"Error getting exposure for camera '{self.camera_name}': {e}")
            return -1.0

    async def get_triggermode(self) -> str:
        """
        Get the camera's current trigger mode.

        Returns:
            Current trigger mode ("continuous" or "trigger")
            
        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            HardwareOperationError: If trigger mode retrieval fails
        """
        if not self.initialized or self.camera is None:
            return "continuous"
            
        try:
            if not await asyncio.to_thread(self.camera.IsOpen):
                await asyncio.to_thread(self.camera.Open)
                
            # Don't stop grabbing - just check the current state
            trigger_enabled = await asyncio.to_thread(self.camera.TriggerMode.GetValue) == "On"
            trigger_source = await asyncio.to_thread(self.camera.TriggerSource.GetValue) == "Software"

            self.triggermode = "trigger" if (trigger_enabled and trigger_source) else "continuous"
            return self.triggermode
            
        except Exception as e:
            self.logger.error(f"Error getting trigger mode for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get trigger mode: {str(e)}")

    async def set_triggermode(self, triggermode: str = "continuous") -> bool:
        """
        Set the camera's trigger mode for image acquisition.

        Args:
            triggermode: Trigger mode ("continuous" or "trigger")

        Returns:
            True if mode was set successfully
            
        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            CameraConfigurationError: If trigger mode is invalid
            HardwareOperationError: If trigger mode setting fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        if triggermode not in ["continuous", "trigger"]:
            raise CameraConfigurationError(
                f"Invalid trigger mode '{triggermode}' for camera '{self.camera_name}'. "
                "Must be 'continuous' or 'trigger'"
            )

        try:
            if not await asyncio.to_thread(self.camera.IsOpen):
                await asyncio.to_thread(self.camera.Open)

            if await asyncio.to_thread(self.camera.IsGrabbing):
                await asyncio.to_thread(self.camera.StopGrabbing)

            if triggermode == "continuous":
                # Check if TriggerMode is available before setting
                if hasattr(self.camera, 'TriggerMode'):
                    await asyncio.to_thread(self.camera.TriggerMode.SetValue, "Off")
                else:
                    self.logger.warning(f"TriggerMode not available for camera '{self.camera_name}', assuming continuous mode")
            else:
                # Check if trigger features are available
                if not hasattr(self.camera, 'TriggerMode'):
                    raise CameraConfigurationError(f"Trigger mode not supported by camera '{self.camera_name}'")
                
                if hasattr(self.camera, 'TriggerSelector'):
                    await asyncio.to_thread(self.camera.TriggerSelector.SetValue, "FrameStart")
                else:
                    self.logger.warning(f"TriggerSelector not available for camera '{self.camera_name}'")
                
                await asyncio.to_thread(self.camera.TriggerMode.SetValue, "On")
                
                if hasattr(self.camera, 'TriggerSource'):
                    await asyncio.to_thread(self.camera.TriggerSource.SetValue, "Software")
                else:
                    self.logger.warning(f"TriggerSource not available for camera '{self.camera_name}'")

            self.triggermode = triggermode
            await asyncio.to_thread(self.camera.StartGrabbing, self.grabbing_mode)
            
            self.logger.info(f"Trigger mode set to '{triggermode}' for camera '{self.camera_name}'")
            return True
            
        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Error setting trigger mode for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set trigger mode: {str(e)}")

    async def capture(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Capture a single image from the camera.

        In continuous mode, returns the latest available frame.
        In trigger mode, executes a software trigger and waits for the image.

        Returns:
            Tuple of (success, image_array) where image_array is BGR format
            
        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            CameraCaptureError: If image capture fails
            CameraTimeoutError: If capture times out
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            if not await asyncio.to_thread(self.camera.IsOpen):
                await asyncio.to_thread(self.camera.Open)

            if not await asyncio.to_thread(self.camera.IsGrabbing):
                await asyncio.to_thread(self.camera.StartGrabbing, self.grabbing_mode)
            
            for i in range(self.retrieve_retry_count):
                if i > 0:
                    self.logger.info(f"Retrying capture {i+1} of {self.retrieve_retry_count} for camera '{self.camera_name}'")
                    
                try:
                    if self.triggermode == "trigger":
                        await asyncio.to_thread(self.camera.TriggerSoftware.Execute)
                    
                    grab_result = await asyncio.to_thread(
                        self.camera.RetrieveResult,
                        self.timeout_ms, 
                        pylon.TimeoutHandling_ThrowException
                    )

                    if await asyncio.to_thread(grab_result.GrabSucceeded):
                        image_converted = await asyncio.to_thread(self.converter.Convert, grab_result)
                        image = await asyncio.to_thread(image_converted.GetArray)

                        if self.img_quality_enhancement and image is not None:
                            image = await self._enhance_image(image)

                        await asyncio.to_thread(grab_result.Release)
                        return True, image
                    else:
                        error_desc = await asyncio.to_thread(grab_result.ErrorDescription)
                        self.logger.warning(f"Grab failed for camera '{self.camera_name}': {error_desc}")
                        await asyncio.to_thread(grab_result.Release)
                        
                except Exception as e:
                    if "timeout" in str(e).lower():
                        if i == self.retrieve_retry_count - 1:
                            raise CameraTimeoutError(
                                f"Capture timeout after {self.retrieve_retry_count} attempts "
                                f"for camera '{self.camera_name}': {str(e)}"
                            )
                        continue
                    else:
                        raise CameraCaptureError(f"Capture failed for camera '{self.camera_name}': {str(e)}")
            
            raise CameraCaptureError(
                f"Failed to capture image after {self.retrieve_retry_count} attempts "
                f"for camera '{self.camera_name}'"
            )
            
        except (CameraConnectionError, CameraCaptureError, CameraTimeoutError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during capture for camera '{self.camera_name}': {str(e)}")
            raise CameraCaptureError(f"Unexpected capture error for camera '{self.camera_name}': {str(e)}")

    async def _enhance_image(self, image: np.ndarray) -> np.ndarray:
        """
        Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) enhancement.

        Args:
            image: Input BGR image

        Returns:
            Enhanced BGR image
            
        Raises:
            CameraCaptureError: If image enhancement fails
        """
        try:
            # Run image processing in thread to avoid blocking
            def enhance():
                lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
                l, a, b = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                cl = clahe.apply(l)
                enhanced_lab = cv2.merge((cl, a, b))
                enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
                return enhanced_img
            
            return await asyncio.to_thread(enhance)
        except Exception as e:
            self.logger.error(f"Image enhancement failed for camera '{self.camera_name}': {str(e)}")
            raise CameraCaptureError(f"Image enhancement failed: {str(e)}")

    async def check_connection(self) -> bool:
        """
        Check if camera is connected and operational.
        
        Returns:
            True if connected and operational, False otherwise
        """
        if not self.initialized:
            return False
            
        try:
            status, img = await self.capture()
            return status and img is not None and img.shape[0] > 0 and img.shape[1] > 0
        except Exception as e:
            self.logger.warning(f"Connection check failed for camera '{self.camera_name}': {str(e)}")
            return False

    async def import_config(self, config_path: str) -> bool:
        """
        Import camera configuration from common JSON format.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            True if successful
            
        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If configuration import fails
        """
        if self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        if config_path is None or not os.path.exists(config_path):
            raise CameraConfigurationError(f"Configuration file not found: {config_path}")

        try:
            import json
            
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            if not await asyncio.to_thread(self.camera.IsOpen):
                await asyncio.to_thread(self.camera.Open)
                
            was_grabbing = await asyncio.to_thread(self.camera.IsGrabbing)
            if was_grabbing:
                await asyncio.to_thread(self.camera.StopGrabbing)
            
            success_count = 0
            total_settings = 0
            
            # Set exposure time
            if 'exposure_time' in config_data:
                total_settings += 1
                try:
                    if hasattr(self.camera, 'ExposureTime') and \
                       self.camera.ExposureTime.GetAccessMode() in [genicam.RW, genicam.WO]:
                        exposure_value = float(config_data['exposure_time'])
                        await asyncio.to_thread(self.camera.ExposureTime.SetValue, exposure_value)
                        
                        # Verify the setting was applied
                        actual_exposure = await asyncio.to_thread(self.camera.ExposureTime.GetValue)
                        if abs(actual_exposure - exposure_value) < 0.01 * exposure_value:
                            success_count += 1
                            self.logger.info(f"Exposure time set to {exposure_value} μs for camera '{self.camera_name}'")
                        else:
                            self.logger.warning(f"Exposure setting verification failed for camera '{self.camera_name}': requested={exposure_value}, actual={actual_exposure}")
                except Exception as e:
                    self.logger.warning(f"Could not set exposure time for camera '{self.camera_name}': {e}")
            
            # Set gain
            if 'gain' in config_data:
                total_settings += 1
                try:
                    if hasattr(self.camera, 'Gain') and \
                       self.camera.Gain.GetAccessMode() in [genicam.RW, genicam.WO]:
                        gain_value = float(config_data['gain'])
                        await asyncio.to_thread(self.camera.Gain.SetValue, gain_value)
                        
                        # Verify the setting was applied
                        actual_gain = await asyncio.to_thread(self.camera.Gain.GetValue)
                        if abs(actual_gain - gain_value) < 0.01 * gain_value:
                            success_count += 1
                            self.logger.info(f"Gain set to {gain_value} for camera '{self.camera_name}'")
                        else:
                            self.logger.warning(f"Gain setting verification failed for camera '{self.camera_name}': requested={gain_value}, actual={actual_gain}")
                except Exception as e:
                    self.logger.warning(f"Could not set gain for camera '{self.camera_name}': {e}")
            
            # Set trigger mode
            if 'trigger_mode' in config_data:
                total_settings += 1
                try:
                    if hasattr(self.camera, 'TriggerMode') and \
                       self.camera.TriggerMode.GetAccessMode() in [genicam.RW, genicam.WO]:
                        if config_data['trigger_mode'] == "continuous":
                            await asyncio.to_thread(self.camera.TriggerMode.SetValue, "Off")
                        else:
                            if hasattr(self.camera, 'TriggerSelector'):
                                await asyncio.to_thread(self.camera.TriggerSelector.SetValue, "FrameStart")
                            await asyncio.to_thread(self.camera.TriggerMode.SetValue, "On")
                            if hasattr(self.camera, 'TriggerSource'):
                                await asyncio.to_thread(self.camera.TriggerSource.SetValue, "Software")
                        self.triggermode = config_data['trigger_mode']
                        success_count += 1
                except Exception as e:
                    self.logger.warning(f"Could not set trigger mode for camera '{self.camera_name}': {e}")
            
            # Set white balance
            if 'white_balance' in config_data:
                total_settings += 1
                try:
                    if hasattr(self.camera, 'BalanceWhiteAuto') and \
                       self.camera.BalanceWhiteAuto.GetAccessMode() in [genicam.RW, genicam.WO]:
                        wb_mode = config_data['white_balance']
                        if wb_mode == "off":
                            await asyncio.to_thread(self.camera.BalanceWhiteAuto.SetValue, "Off")
                        elif wb_mode == "once":
                            await asyncio.to_thread(self.camera.BalanceWhiteAuto.SetValue, "Once")
                        elif wb_mode == "continuous":
                            await asyncio.to_thread(self.camera.BalanceWhiteAuto.SetValue, "Continuous")
                        success_count += 1
                except Exception as e:
                    self.logger.warning(f"Could not set white balance for camera '{self.camera_name}': {e}")
            
            # Set ROI
            if 'roi' in config_data:
                roi = config_data['roi']
                roi_success = 0
                total_settings += 1
                
                try:
                    if hasattr(self.camera, 'Width') and \
                       self.camera.Width.GetAccessMode() in [genicam.RW, genicam.WO]:
                        await asyncio.to_thread(self.camera.Width.SetValue, int(roi.get('width', 1920)))
                        roi_success += 1
                except Exception as e:
                    self.logger.warning(f"Could not set ROI Width for camera '{self.camera_name}': {e}")
                
                try:
                    if hasattr(self.camera, 'Height') and \
                       self.camera.Height.GetAccessMode() in [genicam.RW, genicam.WO]:
                        await asyncio.to_thread(self.camera.Height.SetValue, int(roi.get('height', 1080)))
                        roi_success += 1
                except Exception as e:
                    self.logger.warning(f"Could not set ROI Height for camera '{self.camera_name}': {e}")
                
                try:
                    if hasattr(self.camera, 'OffsetX') and \
                       self.camera.OffsetX.GetAccessMode() in [genicam.RW, genicam.WO]:
                        await asyncio.to_thread(self.camera.OffsetX.SetValue, int(roi.get('x', 0)))
                        roi_success += 1
                except Exception as e:
                    self.logger.warning(f"Could not set ROI OffsetX for camera '{self.camera_name}': {e}")
                
                try:
                    if hasattr(self.camera, 'OffsetY') and \
                       self.camera.OffsetY.GetAccessMode() in [genicam.RW, genicam.WO]:
                        await asyncio.to_thread(self.camera.OffsetY.SetValue, int(roi.get('y', 0)))
                        roi_success += 1
                except Exception as e:
                    self.logger.warning(f"Could not set ROI OffsetY for camera '{self.camera_name}': {e}")
                
                if roi_success > 0:
                    success_count += 1
            
            # Set pixel format
            if 'pixel_format' in config_data:
                total_settings += 1
                try:
                    if hasattr(self.camera, 'PixelFormat') and \
                       self.camera.PixelFormat.GetAccessMode() in [genicam.RW, genicam.WO]:
                        available_formats = self.get_pixel_format_range()
                        pixel_format = config_data['pixel_format']
                        if pixel_format in available_formats:
                            await asyncio.to_thread(self.camera.PixelFormat.SetValue, pixel_format)
                            success_count += 1
                except Exception as e:
                    self.logger.warning(f"Could not set pixel format for camera '{self.camera_name}': {e}")
            
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
            
            if was_grabbing:
                await asyncio.to_thread(self.camera.StartGrabbing, self.grabbing_mode)
            
            self.logger.info(
                f"Configuration imported from '{config_path}' for camera '{self.camera_name}': "
                f"{success_count}/{total_settings} settings applied successfully"
            )
            return True
                
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Error importing configuration for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to import configuration: {str(e)}")
            
    async def export_config(self, config_path: str) -> bool:
        """
        Export current camera configuration to common JSON format.
        
        Args:
            config_path: Path where to save configuration file
            
        Returns:
            True if successful
            
        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If configuration export fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            import json
            
            # Ensure directory exists if there is a directory part
            dir_name = os.path.dirname(config_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            
            if not await asyncio.to_thread(self.camera.IsOpen):
                await asyncio.to_thread(self.camera.Open)
            
            # Default configuration values for Basler cameras
            defaults = {
                "exposure_time": 20000.0,
                "gain": 1.0,
                "trigger_mode": "continuous",
                "white_balance": "off",
                "width": 1920,
                "height": 1080,
                "roi_x": 0,
                "roi_y": 0,
                "pixel_format": "BayerRG8"
            }
            
            # Get current camera settings with fallbacks
            exposure_time = defaults["exposure_time"]
            try:
                exposure_time = await asyncio.to_thread(self.camera.ExposureTime.GetValue)
            except Exception as e:
                self.logger.warning(f"Could not get exposure time for camera '{self.camera_name}': {e}")
            
            gain = defaults["gain"]
            try:
                if hasattr(self.camera, 'Gain'):
                    gain = await asyncio.to_thread(self.camera.Gain.GetValue)
            except Exception as e:
                self.logger.warning(f"Could not get gain for camera '{self.camera_name}': {e}")
            
            trigger_mode = defaults["trigger_mode"]
            try:
                trigger_enabled = await asyncio.to_thread(self.camera.TriggerMode.GetValue) == "On"
                trigger_source = await asyncio.to_thread(self.camera.TriggerSource.GetValue) == "Software"
                trigger_mode = "trigger" if (trigger_enabled and trigger_source) else "continuous"
            except Exception as e:
                self.logger.warning(f"Could not get trigger mode for camera '{self.camera_name}': {e}")
            
            white_balance = defaults["white_balance"]
            try:
                if self.camera.BalanceWhiteAuto.GetAccessMode() == genicam.RO or \
                   self.camera.BalanceWhiteAuto.GetAccessMode() == genicam.RW:
                    wb_auto = await asyncio.to_thread(self.camera.BalanceWhiteAuto.GetValue)
                    white_balance = wb_auto.lower()
            except Exception as e:
                self.logger.warning(f"Could not get white balance for camera '{self.camera_name}': {e}")
            
            # Get image dimensions and ROI
            width = defaults["width"]
            height = defaults["height"]
            try:
                width = int(await asyncio.to_thread(self.camera.Width.GetValue))
                height = int(await asyncio.to_thread(self.camera.Height.GetValue))
            except Exception as e:
                self.logger.warning(f"Could not get image dimensions for camera '{self.camera_name}': {e}")
            
            roi_x = defaults["roi_x"]
            roi_y = defaults["roi_y"]
            try:
                roi_x = int(await asyncio.to_thread(self.camera.OffsetX.GetValue))
                roi_y = int(await asyncio.to_thread(self.camera.OffsetY.GetValue))
            except Exception as e:
                self.logger.warning(f"Could not get ROI offsets for camera '{self.camera_name}': {e}")
            
            pixel_format = defaults["pixel_format"]
            try:
                pixel_format = await asyncio.to_thread(self.camera.PixelFormat.GetValue)
            except Exception as e:
                self.logger.warning(f"Could not get pixel format for camera '{self.camera_name}': {e}")
            
            # Create common format configuration
            config_data = {
                "camera_type": "basler",
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
                "buffer_count": getattr(self, 'buffer_count', 25)
            }
            
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            self.logger.info(f"Configuration exported to '{config_path}' for camera '{self.camera_name}' using common JSON format")
            return True
                
        except Exception as e:
            self.logger.error(f"Error exporting configuration for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to export configuration: {str(e)}")

    def set_ROI(self, x: int, y: int, width: int, height: int) -> bool:
        """
        Set the Region of Interest (ROI) for image acquisition.

        Args:
            x: X offset from sensor top-left
            y: Y offset from sensor top-left
            width: ROI width
            height: ROI height

        Returns:
            True if ROI was set successfully
            
        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If ROI parameters are invalid
            HardwareOperationError: If ROI setting fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
            
        if width <= 0 or height <= 0:
            raise CameraConfigurationError(f"Invalid ROI dimensions: {width}x{height}")
        if x < 0 or y < 0:
            raise CameraConfigurationError(f"Invalid ROI offsets: ({x}, {y})")
            
        try:
            was_open = self.camera.IsOpen()
            if not was_open:
                self.camera.Open()
            
            if self.camera.IsGrabbing():
                self.camera.StopGrabbing()
            
            x_inc = self.camera.OffsetX.GetInc()
            y_inc = self.camera.OffsetY.GetInc()
            width_inc = self.camera.Width.GetInc()
            height_inc = self.camera.Height.GetInc()
            
            x = (x // x_inc) * x_inc
            y = (y // y_inc) * y_inc
            width = (width // width_inc) * width_inc
            height = (height // height_inc) * height_inc
            
            self.camera.Width.SetValue(width)
            self.camera.Height.SetValue(height)
            self.camera.OffsetX.SetValue(x)
            self.camera.OffsetY.SetValue(y)
            
            self.camera.StartGrabbing(self.grabbing_mode)
            
            self.logger.info(f"ROI set to ({x}, {y}, {width}, {height}) for camera '{self.camera_name}'")
            return True
            
        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Error setting ROI for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set ROI: {str(e)}")
                
    def get_ROI(self) -> Dict[str, int]:
        """
        Get current Region of Interest settings.
        
        Returns:
            Dictionary with x, y, width, height
            
        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If ROI retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
            
        try:
            was_open = self.camera.IsOpen()
            if not was_open:
                self.camera.Open()
            
            roi = {
                "x": self.camera.OffsetX.GetValue(),
                "y": self.camera.OffsetY.GetValue(),
                "width": self.camera.Width.GetValue(),
                "height": self.camera.Height.GetValue()
            }
                                
            return roi
   
        except Exception as e:
            self.logger.error(f"Error getting ROI for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get ROI: {str(e)}")

    def reset_ROI(self) -> bool:
        """
        Reset ROI to maximum sensor area.
        
        Returns:
            True if successful
            
        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If ROI reset fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
            
        try:
            if not self.camera.IsOpen():
                self.camera.Open()
            
            if self.camera.IsGrabbing():
                self.camera.StopGrabbing()
                
            self.camera.OffsetX.SetValue(0)
            self.camera.OffsetY.SetValue(0)
            
            max_width = self.camera.Width.GetMax()
            max_height = self.camera.Height.GetMax()
            
            width_inc = self.camera.Width.GetInc()
            height_inc = self.camera.Height.GetInc()
            max_width = (max_width // width_inc) * width_inc
            max_height = (max_height // height_inc) * height_inc
            
            self.camera.Width.SetValue(max_width)
            self.camera.Height.SetValue(max_height)
                
            self.camera.StartGrabbing(self.grabbing_mode)
            
            self.logger.info(f"ROI reset to maximum for camera '{self.camera_name}'")
            return True
                
        except Exception as e:
            self.logger.error(f"Error resetting ROI for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to reset ROI: {str(e)}")

    def set_gain(self, gain: float) -> bool:
        """
        Set the camera's gain value.

        Args:
            gain: Gain value (camera-specific range)

        Returns:
            True if gain was set successfully
            
        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If gain setting fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
            
        try:
            was_open = self.camera.IsOpen()
            if not was_open:
                self.camera.Open()
            
            self.camera.Gain.SetValue(gain)
            self.logger.info(f"Gain set to {gain} for camera '{self.camera_name}'")
            return True
                
        except Exception as e:
            self.logger.warning(f"Gain setting not available for camera '{self.camera_name}': {str(e)}")
            # Return True if gain feature is not available (graceful degradation)
            return True

    def get_gain(self) -> float:
        """
        Get current camera gain.
        
        Returns:
            Current gain value
            
        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If gain retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
            
        try:
            was_open = self.camera.IsOpen()
            if not was_open:
                self.camera.Open()

            gain = self.camera.Gain.GetValue()
            return gain
                
        except Exception as e:
            self.logger.warning(f"Gain not available for camera '{self.camera_name}': {str(e)}")
            # Return reasonable default if gain feature is not available
            return 1.0  # Unity gain default

    def get_gain_range(self) -> List[Union[int, float]]:
        """
        Get camera gain range.
        
        Returns:
            List containing [min_gain, max_gain]
            
        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If gain range retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
            
        try:
            was_open = self.camera.IsOpen()
            if not was_open:
                self.camera.Open()

            min_gain = self.camera.Gain.GetMin()
            max_gain = self.camera.Gain.GetMax()
            return [min_gain, max_gain]
                
        except Exception as e:
            self.logger.warning(f"Gain range not available for camera '{self.camera_name}': {str(e)}")
            # Return reasonable defaults if gain feature is not available
            return [1.0, 16.0]  # Common gain range

    def get_wb_range(self) -> List[str]:
        """
        Get available white balance modes.
        
        Returns:
            List of available white balance modes
        """
        return ["off", "once", "continuous"]

    async def get_width_range(self) -> List[int]:
        """
        Get camera width range.
        
        Returns:
            List containing [min_width, max_width]
            
        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If width range retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
            
        try:
            was_open = self.camera.IsOpen()
            if not was_open:
                self.camera.Open()

            min_width = self.camera.Width.GetMin()
            max_width = self.camera.Width.GetMax()
            return [min_width, max_width]
                
        except Exception as e:
            self.logger.error(f"Error getting width range for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get width range: {str(e)}")

    async def get_height_range(self) -> List[int]:
        """
        Get camera height range.
        
        Returns:
            List containing [min_height, max_height]
            
        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If height range retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
            
        try:
            was_open = self.camera.IsOpen()
            if not was_open:
                self.camera.Open()

            min_height = self.camera.Height.GetMin()
            max_height = self.camera.Height.GetMax()
            return [min_height, max_height]
                
        except Exception as e:
            self.logger.error(f"Error getting height range for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get height range: {str(e)}")

    def get_pixel_format_range(self) -> List[str]:
        """
        Get available pixel formats.
        
        Returns:
            List of available pixel formats
            
        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If pixel format range retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
            
        try:
            was_open = self.camera.IsOpen()
            if not was_open:
                self.camera.Open()

            # Get available pixel formats from camera
            available_formats = []
            pixel_format_entries = self.camera.PixelFormat.GetEntries()
            for entry in pixel_format_entries:
                if entry.GetAccessMode() == genicam.RW or entry.GetAccessMode() == genicam.RO:
                    available_formats.append(entry.GetSymbolic())
            
            return available_formats if available_formats else ["BGR8", "RGB8", "Mono8"]
                
        except Exception as e:
            self.logger.error(f"Error getting pixel format range for camera '{self.camera_name}': {str(e)}")
            return ["BGR8", "RGB8", "Mono8", "BayerRG8", "BayerGB8", "BayerGR8", "BayerBG8"]

    def get_current_pixel_format(self) -> str:
        """
        Get current pixel format.
        
        Returns:
            Current pixel format
            
        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If pixel format retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
            
        try:
            was_open = self.camera.IsOpen()
            if not was_open:
                self.camera.Open()

            pixel_format = self.camera.PixelFormat.GetValue()
            return pixel_format
                
        except Exception as e:
            self.logger.error(f"Error getting current pixel format for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get current pixel format: {str(e)}")

    def set_pixel_format(self, pixel_format: str) -> bool:
        """
        Set pixel format.
        
        Args:
            pixel_format: Pixel format to set
            
        Returns:
            True if pixel format was set successfully, False otherwise
            
        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If pixel format is invalid
            HardwareOperationError: If pixel format setting fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            was_open = self.camera.IsOpen()
            if not was_open:
                self.camera.Open()

            # Check if pixel format is available
            available_formats = self.get_pixel_format_range()
            if pixel_format not in available_formats:
                raise CameraConfigurationError(
                    f"Pixel format '{pixel_format}' not supported. "
                    f"Available formats: {available_formats}"
                )

            # Stop grabbing temporarily for pixel format change
            was_grabbing = self.camera.IsGrabbing()
            if was_grabbing:
                self.camera.StopGrabbing()

            self.camera.PixelFormat.SetValue(pixel_format)
            
            # Restart grabbing if it was running
            if was_grabbing:
                self.camera.StartGrabbing(self.grabbing_mode)

            self.logger.info(f"Pixel format set to '{pixel_format}' for camera '{self.camera_name}'")
            return True
                
        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Error setting pixel format for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set pixel format: {str(e)}")

    async def get_wb(self) -> str:
        """
        Get the current white balance auto setting.

        Returns:
            White balance auto setting ("off", "once", "continuous")
            
        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If white balance retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
            
        try:
            was_open = self.camera.IsOpen()
            if not was_open:
                self.camera.Open()

            if self.camera.BalanceWhiteAuto.GetAccessMode() == genicam.RO or \
               self.camera.BalanceWhiteAuto.GetAccessMode() == genicam.RW:
                
                wb_auto = self.camera.BalanceWhiteAuto.GetValue()
                return wb_auto.lower()
            else:
                self.logger.warning(f"BalanceWhiteAuto feature not available on camera '{self.camera_name}'")
                return "off"
                
        except Exception as e:
            self.logger.error(f"Error getting white balance for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get white balance: {str(e)}")

    async def set_auto_wb_once(self, value: str) -> bool:
        """
        Set the white balance auto mode.

        Args:
            value: White balance mode ("off", "once", "continuous")

        Returns:
            True if white balance mode was set successfully
            
        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If white balance mode is invalid
            HardwareOperationError: If white balance setting fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        if value not in ["off", "once", "continuous"]:
            raise CameraConfigurationError(
                f"Invalid white balance mode '{value}' for camera '{self.camera_name}'. "
                "Must be 'off', 'once', or 'continuous'"
            )
            
        try:
            was_open = self.camera.IsOpen()
            if not was_open:
                self.camera.Open()

            if self.camera.BalanceWhiteAuto.GetAccessMode() != genicam.RW:
                self.logger.warning(f"BalanceWhiteAuto feature not writable on camera '{self.camera_name}'")
                return False

            if value == "off":
                self.camera.BalanceWhiteAuto.SetValue("Off")
                target_mode = "Off"
            elif value == "once":
                self.camera.BalanceWhiteAuto.SetValue("Once")
                target_mode = "Once"
            elif value == "continuous":
                self.camera.BalanceWhiteAuto.SetValue("Continuous")
                target_mode = "Continuous"
                
            actual_mode = self.camera.BalanceWhiteAuto.GetValue()
            success = (actual_mode == target_mode)
            
            if success:
                self.logger.info(f"White balance mode set to '{actual_mode}' for camera '{self.camera_name}'")
            else:
                self.logger.warning(
                    f"Failed to set white balance mode for camera '{self.camera_name}'. "
                    f"Target: {target_mode}, Actual: {actual_mode}"
                )

            return success
                
        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Error setting white balance for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set white balance: {str(e)}")

    async def close(self):
        """
        Close the camera and release resources.
        
        Raises:
            CameraConnectionError: If camera closure fails
        """
        if self.camera is not None:
            try:
                camera = self.camera
                self.camera = None
                self.initialized = False
                
                try:
                    if await asyncio.to_thread(camera.IsGrabbing):
                        await asyncio.to_thread(camera.StopGrabbing)
                except Exception as e:
                    self.logger.warning(f"Error stopping grab for camera '{self.camera_name}': {str(e)}")
                    
                try:
                    if await asyncio.to_thread(camera.IsOpen):
                        await asyncio.to_thread(camera.Close)
                except Exception as e:
                    self.logger.warning(f"Error closing camera '{self.camera_name}': {str(e)}")
                    
                self.logger.info(f"Basler camera '{self.camera_name}' closed")
                    
            except Exception as e:
                self.logger.error(f"Error in camera cleanup for '{self.camera_name}': {str(e)}")
                raise CameraConnectionError(f"Failed to close camera '{self.camera_name}': {str(e)}")