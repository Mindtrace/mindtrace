#!/usr/bin/env python3
"""
Abstract base classes for camera implementations.

This module defines the interface that all camera backends must implement,
providing a consistent API for camera operations across different manufacturers
and camera types.

Features:
    - Abstract base class with comprehensive async camera interface
    - Consistent async pattern with PLC backends
    - Type-safe method signatures with full type hints
    - Configuration system integration
    - Resource management and cleanup
    - Default implementations for optional features
    - Standardized constructor signature across all backends

Usage:
    This is an abstract base class and cannot be instantiated directly.
    Camera backends should inherit from BaseCamera and implement all
    abstract methods.

Example:
    class MyCameraBackend(BaseCamera):
        async def initialize(self) -> Tuple[bool, Any, Any]:
            # Implementation here
            pass

        async def capture(self) -> Tuple[bool, Optional[np.ndarray]]:
            # Implementation here
            pass

        # ... implement other abstract methods
"""

from __future__ import annotations

import uuid
from abc import abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from mindtrace.core.base.mindtrace_base import MindtraceABC
from mindtrace.hardware.core.config import get_camera_config
from mindtrace.hardware.core.exceptions import CameraConnectionError, CameraInitializationError, CameraNotFoundError


class BaseCamera(MindtraceABC):
    """
    Abstract base class for all camera implementations.

    This class defines the async interface that all camera backends must implement
    to ensure consistent behavior across different camera types and manufacturers.
    Uses async-first design consistent with PLC backends.

    Attributes:
        camera_name: Unique identifier for the camera
        camera_config_file: Path to camera configuration file
        img_quality_enhancement: Whether image quality enhancement is enabled
        retrieve_retry_count: Number of retries for image retrieval
        camera: The initialized camera object (implementation-specific)
        device_manager: Device manager object (implementation-specific)
        initialized: Camera initialization status
    """

    def __init__(
        self,
        camera_name: Optional[str] = None,
        camera_config: Optional[str] = None,
        img_quality_enhancement: Optional[bool] = None,
        retrieve_retry_count: Optional[int] = None,
    ):
        """
        Initialize base camera with configuration integration.

        Args:
            camera_name: Unique identifier for the camera (auto-generated if None)
            camera_config: Path to camera configuration file
            img_quality_enhancement: Whether to apply image quality enhancement (uses config default if None)
            retrieve_retry_count: Number of retries for image retrieval (uses config default if None)
        """
        super().__init__()

        self.camera_config = get_camera_config().get_config()

        self._setup_camera_logger_formatting()

        self.camera_name = camera_name or str(uuid.uuid4())
        self.camera_config_file = camera_config

        if img_quality_enhancement is None:
            self.img_quality_enhancement = self.camera_config.cameras.image_quality_enhancement
        else:
            self.img_quality_enhancement = img_quality_enhancement

        if retrieve_retry_count is None:
            self.retrieve_retry_count = self.camera_config.cameras.retrieve_retry_count
        else:
            self.retrieve_retry_count = retrieve_retry_count

        self.camera: Optional[Any] = None
        self.device_manager: Optional[Any] = None
        self.initialized: bool = False

        self.logger.info(
            f"Camera base initialized: camera_name={self.camera_name}, "
            f"img_quality_enhancement={self.img_quality_enhancement}, "
            f"retrieve_retry_count={self.retrieve_retry_count}"
        )

    def _setup_camera_logger_formatting(self):
        """
        Setup camera-specific logger formatting.

        Provides consistent formatting for all camera-related log messages.
        This method ensures uniform logging across all camera implementations.
        """
        import logging

        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)

            formatter = logging.Formatter(
                "%(asctime)s | %(name)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
            console_handler.setFormatter(formatter)

            self.logger.addHandler(console_handler)
            self.logger.setLevel(logging.INFO)

        self.logger.propagate = False

    async def setup_camera(self) -> None:
        """
        Common setup method for camera initialization.

        This method provides a standardized setup pattern that can be used
        by all camera backends. It calls the abstract initialize() method
        and handles common initialization patterns.

        Raises:
            CameraNotFoundError: If camera cannot be found
            CameraInitializationError: If camera initialization fails
            CameraConnectionError: If camera connection fails
        """
        try:
            self.initialized, self.camera, _ = await self.initialize()
            if not self.initialized:
                raise CameraInitializationError(f"Camera '{self.camera_name}' initialization returned False")
        except (CameraNotFoundError, CameraInitializationError, CameraConnectionError):
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize camera '{self.camera_name}': {str(e)}")
            self.initialized = False
            raise CameraInitializationError(f"Failed to initialize camera '{self.camera_name}': {str(e)}")

    @abstractmethod
    async def initialize(self) -> Tuple[bool, Any, Any]:
        """
        Initialize the camera and establish connection.

        This method should handle all necessary setup to prepare the camera
        for image capture, including device discovery, connection establishment,
        and initial configuration.

        Returns:
            Tuple of (success, camera_object, remote_control_object)
            - success: True if initialization successful, False otherwise
            - camera_object: The initialized camera object (implementation-specific)
            - remote_control_object: Remote control interface (implementation-specific)
        """
        raise NotImplementedError

    @abstractmethod
    async def set_exposure(self, exposure: Union[int, float]) -> bool:
        """
        Set camera exposure time.

        Args:
            exposure: Exposure time value (units depend on implementation)

        Returns:
            True if exposure was set successfully, False otherwise
        """
        raise NotImplementedError

    @abstractmethod
    async def get_exposure(self) -> float:
        """
        Get current camera exposure time.

        Returns:
            Current exposure time value (units depend on implementation)
        """
        raise NotImplementedError

    @abstractmethod
    async def get_exposure_range(self) -> List[Union[int, float]]:
        """
        Get camera exposure time range.

        Returns:
            List containing [min_exposure, max_exposure] in implementation-specific units
        """
        raise NotImplementedError

    @abstractmethod
    async def capture(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Capture an image from the camera.

        This method should handle the complete image capture process,
        including any necessary retries based on retrieve_retry_count.

        Returns:
            Tuple of (success, image_array)
            - success: True if capture successful, False otherwise
            - image_array: Captured image as numpy array, None if capture failed
        """
        raise NotImplementedError

    @abstractmethod
    async def check_connection(self) -> bool:
        """
        Check if camera is connected and responding.

        Returns:
            True if camera is connected and responding, False otherwise
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """
        Close camera connection and release resources.

        This method should ensure all camera resources are properly
        released and the camera is disconnected safely.
        """
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """
        Get list of available cameras.

        Args:
            include_details: If True, return detailed camera information

        Returns:
            List of camera names or dictionary with detailed camera information
        """
        raise NotImplementedError

    # Default implementations for optional methods
    async def set_config(self, config: str) -> bool:
        """
        Set camera configuration.

        Default implementation that can be overridden by specific backends.

        Args:
            config: Configuration string or path

        Returns:
            True if configuration was set successfully, False otherwise
        """
        self.logger.warning(f"set_config not implemented for {self.__class__.__name__}")
        return False

    async def import_config(self, config_path: str) -> bool:
        """
        Import camera configuration from file.

        Default implementation that can be overridden by specific backends.

        Args:
            config_path: Path to configuration file

        Returns:
            True if configuration was imported successfully, False otherwise
        """
        self.logger.warning(f"import_config not implemented for {self.__class__.__name__}")
        return False

    async def export_config(self, config_path: str) -> bool:
        """
        Export camera configuration to file.

        Default implementation that can be overridden by specific backends.

        Args:
            config_path: Path to save configuration file

        Returns:
            True if configuration was exported successfully, False otherwise
        """
        self.logger.warning(f"export_config not implemented for {self.__class__.__name__}")
        return False

    async def get_wb(self) -> str:
        """
        Get camera white balance setting.

        Default implementation that can be overridden by specific backends.

        Returns:
            Current white balance setting
        """
        self.logger.warning(f"get_wb not implemented for {self.__class__.__name__}")
        return "unknown"

    async def set_auto_wb_once(self, value: str) -> bool:
        """
        Set camera white balance.

        Default implementation that can be overridden by specific backends.

        Args:
            value: White balance setting

        Returns:
            True if white balance was set successfully, False otherwise
        """
        self.logger.warning(f"set_auto_wb_once not implemented for {self.__class__.__name__}")
        return False

    def get_wb_range(self) -> List[str]:
        """
        Get available white balance modes.

        Default implementation that can be overridden by specific backends.

        Returns:
            List of available white balance modes
        """
        self.logger.warning(f"get_wb_range not implemented for {self.__class__.__name__}")
        return ["auto", "manual", "off"]

    async def get_triggermode(self) -> str:
        """
        Get camera trigger mode.

        Default implementation that can be overridden by specific backends.

        Returns:
            Current trigger mode
        """
        self.logger.warning(f"get_triggermode not implemented for {self.__class__.__name__}")
        return "continuous"

    async def set_triggermode(self, triggermode: str = "continuous") -> bool:
        """
        Set camera trigger mode.

        Default implementation that can be overridden by specific backends.

        Args:
            triggermode: Trigger mode to set

        Returns:
            True if trigger mode was set successfully, False otherwise
        """
        self.logger.warning(f"set_triggermode not implemented for {self.__class__.__name__}")
        return False

    def get_image_quality_enhancement(self) -> bool:
        """
        Get current image quality enhancement setting.

        Returns:
            True if image quality enhancement is enabled, False otherwise
        """
        return self.img_quality_enhancement

    def set_image_quality_enhancement(self, img_quality_enhancement: bool) -> bool:
        """
        Set image quality enhancement setting.

        Args:
            img_quality_enhancement: Whether to enable image quality enhancement

        Returns:
            True if setting was applied successfully, False otherwise
        """
        self.img_quality_enhancement = img_quality_enhancement
        self.logger.info(f"Image quality enhancement set to {img_quality_enhancement} for camera '{self.camera_name}'")
        return True

    async def get_width_range(self) -> List[int]:
        """
        Get camera width range.

        Default implementation that can be overridden by specific backends.

        Returns:
            List containing [min_width, max_width]
        """
        self.logger.warning(f"get_width_range not implemented for {self.__class__.__name__}")
        return [640, 1920]

    async def get_height_range(self) -> List[int]:
        """
        Get camera height range.

        Default implementation that can be overridden by specific backends.

        Returns:
            List containing [min_height, max_height]
        """
        self.logger.warning(f"get_height_range not implemented for {self.__class__.__name__}")
        return [480, 1080]

    # Additional standardized methods for camera control
    def set_gain(self, gain: Union[int, float]) -> bool:
        """
        Set camera gain.

        Default implementation that can be overridden by specific backends.

        Args:
            gain: Gain value

        Returns:
            True if gain was set successfully, False otherwise
        """
        self.logger.warning(f"set_gain not implemented for {self.__class__.__name__}")
        return False

    def get_gain(self) -> float:
        """
        Get current camera gain.

        Default implementation that can be overridden by specific backends.

        Returns:
            Current gain value
        """
        self.logger.warning(f"get_gain not implemented for {self.__class__.__name__}")
        return 1.0

    def get_gain_range(self) -> List[Union[int, float]]:
        """
        Get camera gain range.

        Default implementation that can be overridden by specific backends.

        Returns:
            List containing [min_gain, max_gain]
        """
        self.logger.warning(f"get_gain_range not implemented for {self.__class__.__name__}")
        return [1.0, 16.0]

    def set_ROI(self, x: int, y: int, width: int, height: int) -> bool:
        """
        Set Region of Interest (ROI).

        Default implementation that can be overridden by specific backends.

        Args:
            x: ROI x offset
            y: ROI y offset
            width: ROI width
            height: ROI height

        Returns:
            True if ROI was set successfully, False otherwise
        """
        self.logger.warning(f"set_ROI not implemented for {self.__class__.__name__}")
        return False

    def get_ROI(self) -> Dict[str, int]:
        """
        Get current Region of Interest (ROI).

        Default implementation that can be overridden by specific backends.

        Returns:
            Dictionary with ROI parameters
        """
        self.logger.warning(f"get_ROI not implemented for {self.__class__.__name__}")
        return {"x": 0, "y": 0, "width": 1920, "height": 1080}

    def reset_ROI(self) -> bool:
        """
        Reset ROI to full sensor size.

        Default implementation that can be overridden by specific backends.

        Returns:
            True if ROI was reset successfully, False otherwise
        """
        self.logger.warning(f"reset_ROI not implemented for {self.__class__.__name__}")
        return False

    def get_pixel_format_range(self) -> List[str]:
        """
        Get available pixel formats.

        Default implementation that can be overridden by specific backends.

        Returns:
            List of available pixel formats
        """
        self.logger.warning(f"get_pixel_format_range not implemented for {self.__class__.__name__}")
        return ["BGR8", "RGB8"]

    def get_current_pixel_format(self) -> str:
        """
        Get current pixel format.

        Default implementation that can be overridden by specific backends.

        Returns:
            Current pixel format
        """
        self.logger.warning(f"get_current_pixel_format not implemented for {self.__class__.__name__}")
        return "RGB8"

    def set_pixel_format(self, pixel_format: str) -> bool:
        """
        Set pixel format.

        Default implementation that can be overridden by specific backends.

        Args:
            pixel_format: Pixel format to set

        Returns:
            True if pixel format was set successfully, False otherwise
        """
        self.logger.warning(f"set_pixel_format not implemented for {self.__class__.__name__}")
        return False

    async def __aenter__(self):
        """Async context manager entry."""
        await self.setup_camera()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def __del__(self) -> None:
        """
        Destructor to ensure resources are cleaned up.
        """
        try:
            if hasattr(self, "camera") and self.camera is not None:
                if hasattr(self, "logger"):
                    self.logger.warning(
                        f"Camera '{self.camera_name}' destroyed without proper cleanup. "
                        f"Use 'async with camera' or call 'await camera.close()' for proper cleanup."
                    )
        except Exception:
            # Ignore all errors during destruction
            pass
