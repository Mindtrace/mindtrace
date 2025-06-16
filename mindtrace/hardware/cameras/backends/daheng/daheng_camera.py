"""
Daheng Camera Backend Implementation

This module provides a comprehensive implementation for Daheng cameras using the gxipy SDK.
It supports advanced camera features including trigger modes, exposure control, white balance,
and image quality enhancement.

Features:
    - Full Daheng camera support via gxipy SDK
    - Hardware trigger and continuous capture modes
    - Automatic exposure and white balance control
    - Image quality enhancement with gamma, contrast, and color correction
    - Configuration import/export functionality
    - Robust error handling and connection management

Requirements:
    - gxipy SDK (Galaxy SDK for Python)
    - OpenCV for image processing
    - Daheng Galaxy SDK installed on system

Installation:
    1. Install Daheng Galaxy SDK from manufacturer
    2. Install gxipy: pip install git+https://github.com/Mindtrace/gxipy.git
    3. Restart development environment for environment variable updates

Usage:
    from mindtrace.hardware.cameras.backends.daheng import DahengCamera
    
    # Get available cameras
    cameras = DahengCamera.get_available_cameras()
    
    # Initialize camera
    camera = DahengCamera("Camera_001", img_quality_enhancement=True)
    
    # Configure and capture
    camera.set_exposure(10000)
    camera.set_triggermode("continuous")
    success, image = camera.capture()
    camera.close()

Configuration:
    All camera parameters are configurable via the hardware configuration system:
    - MINDTRACE_CAMERA_EXPOSURE_TIME: Default exposure time
    - MINDTRACE_CAMERA_GAIN: Camera gain setting
    - MINDTRACE_CAMERA_BUFFER_SIZE: Image buffer size
    - MINDTRACE_CAMERA_TRIGGER_MODE: Default trigger mode
    - MINDTRACE_CAMERA_WHITE_BALANCE: White balance mode
    - MINDTRACE_CAMERA_IMAGE_QUALITY_ENHANCEMENT: Enable image enhancement
    - MINDTRACE_CAMERA_RETRIEVE_RETRY_COUNT: Capture retry attempts

Supported Camera Models:
    - All Daheng USB3 cameras (MER, MV series)
    - All Daheng GigE cameras (MER, MV series)
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
from typing import Optional, List, Tuple, Union, Dict, Any
import numpy as np
import cv2

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
    """
    Daheng camera implementation using gxipy SDK.
    
    This class provides a complete interface for Daheng cameras with support for
    advanced features like trigger modes, exposure control, white balance, and
    image quality enhancement.
    
    Attributes:
        camera_name: User-defined camera identifier
        camera_config_file: Path to camera configuration file
        img_quality_enhancement: Enable image quality enhancement
        retrieve_retry_count: Number of capture retry attempts
        device_manager: Daheng device manager instance
        camera: Active camera device instance
        remote_device_feature: Camera remote control interface
        triggermode: Current trigger mode ("continuous" or "trigger")
        gamma_lut: Gamma correction lookup table
        contrast_lut: Contrast enhancement lookup table
        color_correction_param: Color correction matrix
    """
    
    def __init__(
        self,
        camera_name: str,
        camera_config_file: Optional[str] = None,
        img_quality_enhancement: Optional[bool] = None,
        retrieve_retry_count: Optional[int] = None,
    ):
        """
        Initialize Daheng camera with configurable parameters.

        Args:
            camera_name: User ID of Daheng camera
            camera_config_file: Path to camera config file (optional)
            img_quality_enhancement: Enable image quality enhancement (uses config default if None)
            retrieve_retry_count: Number of capture retry attempts (uses config default if None)
            
        Raises:
            SDKNotAvailableError: If gxipy SDK is not available
            CameraInitializationError: If camera initialization fails
            CameraNotFoundError: If specified camera is not found
            CameraConfigurationError: If configuration is invalid
        """
        if not GXIPY_AVAILABLE:
            raise SDKNotAvailableError(
                "gxipy",
                "Install gxipy to use Daheng cameras:\n"
                "1. Install Daheng Galaxy SDK from manufacturer\n"
                "2. Install gxipy: pip install git+https://github.com/Mindtrace/gxipy.git\n"
                "3. Restart development environment for environment variable updates"
            )
        
        super().__init__(camera_name, camera_config_file, img_quality_enhancement, retrieve_retry_count)
        
        self.device_manager = gx.DeviceManager()
        self.remote_device_feature = None
        self.triggermode = self.camera_config.cameras.trigger_mode
        
        self.gamma_lut = None
        self.contrast_lut = None
        self.color_correction_param = None
        
        try:
            self.initialized, self.camera, self.remote_device_feature = self.initialize()
            
            if self.camera is not None:
                self._configure_trigger_mode()
                
                if self.camera_config_file is not None and not os.path.exists(self.camera_config_file):
                    self.set_auto_wb_once(self.camera_config.cameras.white_balance)
                
                if img_quality_enhancement:
                    self.gamma_lut, self.contrast_lut, self.color_correction_param = self._initialize_image_enhancement()
                    
        except (SDKNotAvailableError, CameraNotFoundError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Daheng camera '{camera_name}': {str(e)}")
            self.initialized = False
            raise CameraInitializationError(f"Failed to initialize Daheng camera '{camera_name}': {str(e)}")

    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """
        Get the available Daheng cameras.
        
        Args:
            include_details: If True, return detailed camera information
            
        Returns:
            List of camera names or dictionary with detailed camera information
            
        Raises:
            SDKNotAvailableError: If gxipy SDK is not available
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
    
    def initialize(self) -> Tuple[bool, Any, Any]:
        """
        Initialize Daheng camera and import configuration if available.
        
        Returns:
            Tuple of (success_status, camera_instance, remote_control_instance)
            
        Raises:
            CameraNotFoundError: If no cameras found or specified camera not found
            CameraInitializationError: If camera initialization fails
            CameraConnectionError: If camera connection fails
            CameraConfigurationError: If configuration import fails
        """
        status = False
        camera = None
        remote_control = None
        
        try:
            dev_cnt, dev_info_list = self.device_manager.update_device_list()
            if dev_cnt == 0:
                raise CameraNotFoundError("No Daheng cameras found")
            
            camera_found = False
            for index, dev_info in enumerate(dev_info_list):
                if dev_info.get("user_id") == self.camera_name:
                    camera_found = True
                    try:
                        camera = self.device_manager.open_device_by_index(index + 1)
                        remote_control = camera.get_remote_device_feature_control()
                        
                        self._configure_stream_buffer(camera)
                        
                        if self.camera_config_file is not None and os.path.exists(self.camera_config_file):
                            try:
                                camera.import_config_file(self.camera_config_file)
                                self.logger.info(f"Imported configuration from: {self.camera_config_file}")
                            except Exception as e:
                                self.logger.warning(f"Failed to import configuration: {str(e)}")
                                raise CameraConfigurationError(f"Failed to import configuration from '{self.camera_config_file}': {str(e)}")
                        
                        camera.stream_on()
                        status = True
                        self.logger.info(f"Daheng camera '{self.camera_name}' initialized successfully")
                        break
                        
                    except CameraConfigurationError:
                        raise
                    except Exception as e:
                        self.logger.error(f"Failed to open camera '{self.camera_name}': {str(e)}")
                        if camera:
                            try:
                                camera.close_device()
                            except:
                                pass
                        raise CameraConnectionError(f"Failed to connect to camera '{self.camera_name}': {str(e)}")
            
            if not camera_found:
                raise CameraNotFoundError(f"Camera '{self.camera_name}' not found")
                
        except (CameraNotFoundError, CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error initializing camera '{self.camera_name}': {str(e)}")
            raise CameraInitializationError(f"Unexpected error initializing camera '{self.camera_name}': {str(e)}")

        return status, camera, remote_control

    def _configure_stream_buffer(self, camera) -> None:
        """
        Configure stream buffer handling mode.
        
        Raises:
            CameraConfigurationError: If stream buffer configuration fails
        """
        try:
            stream = camera.get_stream(1)
            
            if hasattr(stream, "get_feature_control"):
                stream_control = stream.get_feature_control()
            elif hasattr(stream, "get_featrue_control"):
                stream_control = stream.get_featrue_control()
            else:
                raise CameraConfigurationError("Camera stream does not support feature control")

            stream_buffer_handling_mode = stream_control.get_enum_feature("StreamBufferHandlingMode")
            stream_buffer_handling_mode.set(3)
            
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.warning(f"Failed to configure stream buffer for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to configure stream buffer for camera '{self.camera_name}': {str(e)}")

    def _configure_trigger_mode(self) -> None:
        """
        Configure trigger mode based on camera settings.
        
        Raises:
            CameraConfigurationError: If trigger mode configuration fails
        """
        try:
            trigger_mode_value = self.camera.TriggerMode.get()
            if trigger_mode_value and trigger_mode_value[0] == 0:
                self.triggermode = "continuous"
            else:
                self.triggermode = "trigger"
            self.logger.debug(f"Camera '{self.camera_name}' trigger mode: {self.triggermode}")
        except Exception as e:
            self.logger.warning(f"Failed to read trigger mode for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to configure trigger mode for camera '{self.camera_name}': {str(e)}")

    def _initialize_image_enhancement(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Initialize image quality enhancement parameters.
        
        Returns:
            Tuple of (gamma_lut, contrast_lut, color_correction_param)
            
        Raises:
            CameraConfigurationError: If image enhancement initialization fails
        """
        try:
            gamma_value = 2.2
            gamma_lut = np.array([
                ((i / 255.0) ** (1.0 / gamma_value)) * 255 
                for i in np.arange(0, 256)
            ]).astype("uint8")
            
            contrast_factor = 1.2
            contrast_lut = np.array([
                np.clip((i - 127) * contrast_factor + 127, 0, 255) 
                for i in np.arange(0, 256)
            ]).astype("uint8")
            
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
        """Get the current image quality enhancement status."""
        return self.img_quality_enhancement

    def get_triggermode(self) -> str:
        """
        Get the current trigger mode.
        
        Raises:
            CameraConnectionError: If camera is not connected
            HardwareOperationError: If trigger mode cannot be read
        """
        if not self.initialized or not self.camera:
            return self.triggermode
        try:
            trigger_mode_value = self.camera.TriggerMode.get()
            return "continuous" if trigger_mode_value and trigger_mode_value[0] == 0 else "trigger"
        except Exception as e:
            self.logger.warning(f"Failed to get trigger mode for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get trigger mode for camera '{self.camera_name}': {str(e)}")

    def get_exposure_range(self) -> List[Union[int, float]]:
        """
        Get camera exposure time range in microseconds.
        
        Raises:
            CameraConnectionError: If camera is not connected
            HardwareOperationError: If exposure range cannot be read
        """
        if not self.initialized or not self.camera:
            return [100, 1000000]
        try:
            exposure_dict = self.camera.ExposureTime.get_range()
            return [exposure_dict["min"], exposure_dict["max"]]
        except Exception as e:
            self.logger.warning(f"Failed to get exposure range for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get exposure range for camera '{self.camera_name}': {str(e)}")

    def get_width_range(self) -> List[int]:
        """
        Get camera width range in pixels.
        
        Raises:
            CameraConnectionError: If camera is not connected
            HardwareOperationError: If width range cannot be read
        """
        if not self.initialized or not self.camera:
            return [640, 1920]
        try:
            width_dict = self.camera.Width.get_range()
            return [width_dict["min"], width_dict["max"]]
        except Exception as e:
            self.logger.warning(f"Failed to get width range for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get width range for camera '{self.camera_name}': {str(e)}")

    def get_height_range(self) -> List[int]:
        """
        Get camera height range in pixels.
        
        Raises:
            CameraConnectionError: If camera is not connected
            HardwareOperationError: If height range cannot be read
        """
        if not self.initialized or not self.camera:
            return [480, 1080]
        try:
            height_dict = self.camera.Height.get_range()
            return [height_dict["min"], height_dict["max"]]
        except Exception as e:
            self.logger.warning(f"Failed to get height range for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get height range for camera '{self.camera_name}': {str(e)}")

    def get_wb(self) -> str:
        """
        Get the current white balance mode.
        
        Raises:
            CameraConnectionError: If camera is not connected
            HardwareOperationError: If white balance cannot be read
        """
        if not self.initialized or not self.camera:
            return "off"
        try:
            wb = self.camera.BalanceWhiteAuto.get()[0]
            return "off" if wb == 0 else "once"
        except Exception as e:
            self.logger.warning(f"Failed to get white balance for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get white balance for camera '{self.camera_name}': {str(e)}")

    def get_exposure(self) -> float:
        """
        Get the current camera exposure time in microseconds.
        
        Raises:
            CameraConnectionError: If camera is not connected
            HardwareOperationError: If exposure cannot be read
        """
        if not self.initialized or not self.camera:
            return float(self.camera_config.cameras.exposure_time)
        try:
            return self.camera.ExposureTime.get()
        except Exception as e:
            self.logger.warning(f"Failed to get exposure for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get exposure for camera '{self.camera_name}': {str(e)}")

    def set_auto_wb_once(self, value: str) -> bool:
        """
        Set the white balance mode.
        
        Args:
            value: White balance mode ("off", "once", "auto")
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            CameraConnectionError: If camera is not connected
            CameraConfigurationError: If white balance configuration fails
        """
        if not self.initialized or not self.camera:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not connected")
        
        if value not in ["off", "once", "auto"]:
            raise CameraConfigurationError(f"Invalid white balance mode '{value}'. Must be 'off', 'once', or 'auto'")
        
        try:
            if value == "off":
                self.camera.BalanceWhiteAuto.set(0)
                new_wb = self.camera.BalanceWhiteAuto.get()[0]
                success = new_wb == 0
            elif value in ["once", "auto"]:
                self.camera.BalanceWhiteAuto.set(2)
                new_wb = self.camera.BalanceWhiteAuto.get()[0]
                success = new_wb == 2
            else:
                return False
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to set white balance to '{value}' for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set white balance to '{value}' for camera '{self.camera_name}': {str(e)}")

    def set_config(self, config: str) -> bool:
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

    def set_image_quality_enhancement(self, img_quality_enhancement: bool) -> bool:
        """
        Enable or disable image quality enhancement.
        
        Args:
            img_quality_enhancement: Enable image quality enhancement
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            CameraConfigurationError: If image enhancement configuration fails
        """
        self.img_quality_enhancement = img_quality_enhancement
        if self.img_quality_enhancement and self.initialized:
            try:
                self.gamma_lut, self.contrast_lut, self.color_correction_param = self._initialize_image_enhancement()
                self.logger.info(f"Image quality enhancement enabled for camera '{self.camera_name}'")
            except CameraConfigurationError:
                raise
            except Exception as e:
                self.logger.warning(f"Failed to initialize image enhancement for camera '{self.camera_name}': {str(e)}")
                raise CameraConfigurationError(f"Failed to initialize image enhancement for camera '{self.camera_name}': {str(e)}")
        else:
            self.logger.info(f"Image quality enhancement disabled for camera '{self.camera_name}'")
        return True

    def set_triggermode(self, triggermode: str = "continuous") -> bool:
        """
        Set the trigger mode of the camera.
        
        Args:
            triggermode: Trigger mode ("continuous" or "trigger")
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            CameraConnectionError: If camera is not connected
            CameraConfigurationError: If trigger mode configuration fails
        """
        if not self.initialized or not self.camera:
            self.triggermode = triggermode
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not connected")
        
        if triggermode not in ["continuous", "trigger"]:
            raise CameraConfigurationError(f"Invalid trigger mode '{triggermode}'. Must be 'continuous' or 'trigger'")
        
        try:
            if triggermode == "trigger":
                self.triggermode = "trigger"
                self.camera.TriggerMode.set(gx.GxSwitchEntry.ON)
                self.camera.TriggerSource.set(gx.GxTriggerSourceEntry.SOFTWARE)
            elif triggermode == "continuous":
                self.triggermode = "continuous"
                self.camera.TriggerMode.set(gx.GxSwitchEntry.OFF)
            
            self.logger.info(f"Trigger mode set to '{triggermode}' for camera '{self.camera_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to set trigger mode to '{triggermode}' for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set trigger mode to '{triggermode}' for camera '{self.camera_name}': {str(e)}")

    def set_exposure(self, exposure_value: Union[int, float]) -> bool:
        """
        Set the exposure time of the camera.
        
        Args:
            exposure_value: Exposure time in microseconds
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            CameraConnectionError: If camera is not connected
            CameraConfigurationError: If exposure configuration fails
        """
        if not self.initialized or not self.camera:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not connected")
        
        try:
            exposure_range = self.get_exposure_range()
            if exposure_value < exposure_range[0] or exposure_value > exposure_range[1]:
                raise CameraConfigurationError(
                    f"Exposure value {exposure_value} out of range {exposure_range} "
                    f"for camera '{self.camera_name}'"
                )
            
            self.camera.ExposureTime.set(exposure_value)
            actual_exposure = self.camera.ExposureTime.get()
            self.logger.info(
                f"Exposure set for camera '{self.camera_name}': "
                f"requested={exposure_value}, actual={actual_exposure}"
            )
            return True
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set exposure to {exposure_value} for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set exposure to {exposure_value} for camera '{self.camera_name}': {str(e)}")

    def close(self):
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

    def capture(self) -> Tuple[bool, Optional[np.ndarray]]:
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

    def check_connection(self) -> bool:
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

    def import_config(self, config_path: str) -> bool:
        """
        Import camera configuration from file.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            CameraConfigurationError: If configuration import fails
        """
        try:
            return self.set_config(config_path)
        except CameraConfigurationError:
            raise
        except Exception as e:
            raise CameraConfigurationError(f"Failed to import configuration from '{config_path}': {str(e)}")

    def export_config(self, config_path: str) -> bool:
        """
        Export camera configuration to file.
        
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
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            was_streaming = False
            try:
                if hasattr(self.camera, 'is_streaming') and self.camera.is_streaming():
                    was_streaming = True
                    self.camera.stream_off()
                    self.logger.debug(f"Temporarily stopped streaming for config export on camera '{self.camera_name}'")
                elif hasattr(self.camera, 'data_stream') and self.camera.data_stream:
                    was_streaming = True
                    self.camera.stream_off()
                    self.logger.debug(f"Temporarily stopped streaming for config export on camera '{self.camera_name}'")
            except Exception as e:
                self.logger.debug(f"Could not stop streaming for camera '{self.camera_name}': {str(e)}")
            
            self.camera.export_config_file(config_path)
            self.logger.info(f"Configuration exported to '{config_path}' for camera '{self.camera_name}'")
            
            if was_streaming:
                try:
                    self.camera.stream_on()
                    self.logger.debug(f"Restarted streaming after config export on camera '{self.camera_name}'")
                except Exception as e:
                    self.logger.warning(f"Could not restart streaming after config export for camera '{self.camera_name}': {str(e)}")
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to export config to '{config_path}' for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to export config to '{config_path}' for camera '{self.camera_name}': {str(e)}")
