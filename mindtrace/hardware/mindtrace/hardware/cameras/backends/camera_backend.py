from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

import numpy as np

from mindtrace.core.base.mindtrace_base import MindtraceABC
from mindtrace.hardware.core.config import get_camera_config
from mindtrace.hardware.core.exceptions import CameraConnectionError, CameraInitializationError, CameraNotFoundError


class CameraBackend(MindtraceABC):
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
        raise NotImplementedError

    @abstractmethod
    async def set_exposure(self, exposure: Union[int, float]) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_exposure(self) -> float:
        raise NotImplementedError

    @abstractmethod
    async def get_exposure_range(self) -> List[Union[int, float]]:
        raise NotImplementedError

    @abstractmethod
    async def capture(self) -> Tuple[bool, Optional[np.ndarray]]:
        raise NotImplementedError

    @abstractmethod
    async def check_connection(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        raise NotImplementedError

    # Default implementations for optional methods
    async def set_config(self, config: str) -> bool:
        self.logger.warning(f"set_config not implemented for {self.__class__.__name__}")
        return False

    async def import_config(self, config_path: str) -> bool:
        self.logger.warning(f"import_config not implemented for {self.__class__.__name__}")
        return False

    async def export_config(self, config_path: str) -> bool:
        self.logger.warning(f"export_config not implemented for {self.__class__.__name__}")
        return False

    async def get_wb(self) -> str:
        self.logger.warning(f"get_wb not implemented for {self.__class__.__name__}")
        return "unknown"

    async def set_auto_wb_once(self, value: str) -> bool:
        self.logger.warning(f"set_auto_wb_once not implemented for {self.__class__.__name__}")
        return False

    def get_wb_range(self) -> List[str]:
        self.logger.warning(f"get_wb_range not implemented for {self.__class__.__name__}")
        return ["auto", "manual", "off"]

    async def get_triggermode(self) -> str:
        self.logger.warning(f"get_triggermode not implemented for {self.__class__.__name__}")
        return "continuous"

    async def set_triggermode(self, triggermode: str = "continuous") -> bool:
        self.logger.warning(f"set_triggermode not implemented for {self.__class__.__name__}")
        return False

    def get_image_quality_enhancement(self) -> bool:
        return self.img_quality_enhancement

    def set_image_quality_enhancement(self, img_quality_enhancement: bool) -> bool:
        self.img_quality_enhancement = img_quality_enhancement
        self.logger.info(f"Image quality enhancement set to {img_quality_enhancement} for camera '{self.camera_name}'")
        return True

    async def get_width_range(self) -> List[int]:
        self.logger.warning(f"get_width_range not implemented for {self.__class__.__name__}")
        return [640, 1920]

    async def get_height_range(self) -> List[int]:
        self.logger.warning(f"get_height_range not implemented for {self.__class__.__name__}")
        return [480, 1080]

    def set_gain(self, gain: Union[int, float]) -> bool:
        self.logger.warning(f"set_gain not implemented for {self.__class__.__name__}")
        return False

    def get_gain(self) -> float:
        self.logger.warning(f"get_gain not implemented for {self.__class__.__name__}")
        return 1.0

    def get_gain_range(self) -> List[Union[int, float]]:
        self.logger.warning(f"get_gain_range not implemented for {self.__class__.__name__}")
        return [1.0, 16.0]

    def set_ROI(self, x: int, y: int, width: int, height: int) -> bool:
        self.logger.warning(f"set_ROI not implemented for {self.__class__.__name__}")
        return False

    def get_ROI(self) -> Dict[str, int]:
        self.logger.warning(f"get_ROI not implemented for {self.__class__.__name__}")
        return {"x": 0, "y": 0, "width": 1920, "height": 1080}

    def reset_ROI(self) -> bool:
        self.logger.warning(f"reset_ROI not implemented for {self.__class__.__name__}")
        return False

    def get_pixel_format_range(self) -> List[str]:
        self.logger.warning(f"get_pixel_format_range not implemented for {self.__class__.__name__}")
        return ["BGR8", "RGB8"]

    def get_current_pixel_format(self) -> str:
        self.logger.warning(f"get_current_pixel_format not implemented for {self.__class__.__name__}")
        return "RGB8"

    def set_pixel_format(self, pixel_format: str) -> bool:
        self.logger.warning(f"set_pixel_format not implemented for {self.__class__.__name__}")
        return False

    async def __aenter__(self):
        await self.setup_camera()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def __del__(self) -> None:
        try:
            if hasattr(self, "camera") and self.camera is not None:
                if hasattr(self, "logger"):
                    self.logger.warning(
                        f"Camera '{self.camera_name}' destroyed without proper cleanup. "
                        f"Use 'async with camera' or call 'await camera.close()' for proper cleanup."
                    )
        except Exception:
            pass 