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

import asyncio
from abc import ABC, abstractmethod
import uuid
import numpy as np
from typing import Tuple, Optional, List, Dict, Any, Union
from pathlib import Path

from mindtrace.core.base.mindtrace_base import MindtraceABC
from mindtrace.hardware.core.config import get_camera_config

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
        
        self.config = self.config.get_config()
        self.camera_config = get_camera_config().get_config()
        self.logger = self.logger
        
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
                '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(formatter)
            
            self.logger.addHandler(console_handler)
            self.logger.setLevel(logging.INFO)
        
        self.logger.propagate = False

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
    async def set_exposure(self, exposure: float) -> bool:
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
        Check if camera is connected and operational.
        
        Returns:
            True if camera is connected and can capture images, False otherwise
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """
        Close the camera connection and release resources.
        
        This method should properly clean up all camera resources,
        close connections, and prepare for safe destruction.
        """
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """
        Get list of available cameras for this backend.
        
        This method should discover and return all cameras that can be
        accessed by this backend implementation. It's a static method
        because it doesn't require an instance.
        
        Args:
            include_details: If True, return detailed information about each camera
            
        Returns:
            List of camera names or dict with detailed information
        """
        raise NotImplementedError

    # Optional methods with default implementations
    
    async def set_config(self, config: str) -> bool:
        """
        Set camera configuration.
        
        Args:
            config: Configuration string or identifier
            
        Returns:
            True if configuration was set successfully, False otherwise
        """
        self.logger.warning(f"Configuration setting not implemented for {self.__class__.__name__}")
        return False

    async def import_config(self, config_path: str) -> bool:
        """
        Import camera configuration from file.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            True if configuration was imported successfully, False otherwise
        """
        self.logger.warning(f"Configuration import not implemented for {self.__class__.__name__}")
        return False

    async def export_config(self, config_path: str) -> bool:
        """
        Export camera configuration to file.
        
        Args:
            config_path: Path where to save configuration file
            
        Returns:
            True if configuration was exported successfully, False otherwise
        """
        self.logger.warning(f"Configuration export not implemented for {self.__class__.__name__}")
        return False

    async def get_wb(self) -> str:
        """
        Get current white balance setting.
        
        Returns:
            Current white balance mode or setting
        """
        self.logger.warning(f"White balance reading not implemented for {self.__class__.__name__}")
        return "off"

    async def set_auto_wb_once(self, value: str) -> bool:
        """
        Set white balance auto mode.
        
        Args:
            value: White balance mode (e.g., "auto", "off", "once")
            
        Returns:
            True if white balance was set successfully, False otherwise
        """
        self.logger.warning(f"White balance setting not implemented for {self.__class__.__name__}")
        return False

    async def get_triggermode(self) -> str:
        """
        Get current trigger mode.
        
        Returns:
            Current trigger mode (e.g., "continuous", "trigger", "software")
        """
        self.logger.warning(f"Trigger mode reading not implemented for {self.__class__.__name__}")
        return "continuous"

    async def set_triggermode(self, triggermode: str = "continuous") -> bool:
        """
        Set camera trigger mode.
        
        Args:
            triggermode: Trigger mode to set (e.g., "continuous", "trigger", "software")
            
        Returns:
            True if trigger mode was set successfully, False otherwise
        """
        self.logger.warning(f"Trigger mode setting not implemented for {self.__class__.__name__}")
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
        Set image quality enhancement.
        
        Args:
            img_quality_enhancement: Whether to enable image quality enhancement
            
        Returns:
            True if setting was applied successfully, False otherwise
        """
        self.img_quality_enhancement = img_quality_enhancement
        self.logger.info(f"Image quality enhancement set to {img_quality_enhancement}")
        return True

    async def get_width_range(self) -> List[int]:
        """
        Get camera width range.
        
        Returns:
            List containing [min_width, max_width] in pixels
        """
        self.logger.warning(f"Width range reading not implemented for {self.__class__.__name__}")
        return [0, 1920]  # Default values

    async def get_height_range(self) -> List[int]:
        """
        Get camera height range.
        
        Returns:
            List containing [min_height, max_height] in pixels
        """
        self.logger.warning(f"Height range reading not implemented for {self.__class__.__name__}")
        return [0, 1080]  # Default values

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def __del__(self) -> None:
        """
        Cleanup when camera object is destroyed.
        
        Note: In async context, prefer explicit cleanup with close() method.
        This destructor is for safety only and may not properly clean up async resources.
        """
        try:
            if hasattr(self, 'initialized') and self.initialized:
                self.logger.warning(
                    f"Camera '{self.camera_name}' destroyed without explicit cleanup. "
                    "Use 'await camera.close()' for proper async cleanup."
                )
        except Exception:
            pass 