"""Mock Basler Camera Backend Module"""

import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

from mindtrace.hardware.cameras.backends.camera_backend import CameraBackend
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
    CameraTimeoutError,
)


class MockBaslerCameraBackend(CameraBackend):
    """Mock Basler Camera Backend Implementation

    This class provides a mock implementation of the Basler camera backend for testing and development. It simulates
    Basler camera functionality without requiring actual hardware, with configurable behavior and error simulation.

    Features:
        - Complete simulation of Basler camera API
        - Configurable image generation with realistic patterns
        - Error simulation for testing error handling
        - Configuration import/export simulation
        - Camera control features (exposure, ROI, trigger modes, etc.)
        - Realistic timing and behavior simulation

    Usage::

        from mindtrace.hardware.cameras.backends.basler import MockBaslerCameraBackend

        camera = MockBaslerCameraBackend("mock_camera_1")
        await camera.set_exposure(20000)
        image = await camera.capture()
        await camera.close()

    Error Simulation:
        Enable error simulation via environment variables:
        - MOCK_BASLER_FAIL_INIT: Simulate initialization failure
        - MOCK_BASLER_FAIL_CAPTURE: Simulate capture failure
        - MOCK_BASLER_TIMEOUT: Simulate timeout errors

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
        **backend_kwargs,
    ):
        """Initialize mock Basler camera.

        Args:
            camera_name: Camera identifier
            camera_config: Path to configuration file (simulated)
            img_quality_enhancement: Enable image enhancement simulation (uses config default if None)
            retrieve_retry_count: Number of capture retry attempts (uses config default if None)
            **backend_kwargs: Backend-specific parameters:
                - pixel_format: Pixel format (simulated)
                - buffer_count: Buffer count (simulated)
                - timeout_ms: Timeout in milliseconds
                - simulate_fail_init: If True, simulate initialization failure (overrides env)
                - simulate_fail_capture: If True, simulate capture failure (overrides env)
                - simulate_timeout: If True, simulate timeout on capture (overrides env)
                - simulate_cancel: If True, simulate asyncio cancellation during capture
                - synthetic_width: Override synthetic image width (int)
                - synthetic_height: Override synthetic image height (int)
                - synthetic_pattern: One of {"auto","gradient","checkerboard","circular","noise"}
                - synthetic_checker_size: Checker size (int) used when pattern is checkerboard
                - synthetic_overlay_text: If False, disables text overlays in synthetic images

        Raises:
            CameraConfigurationError: If configuration is invalid
            CameraInitializationError: If initialization fails (when simulated)
        """
        super().__init__(camera_name, camera_config, img_quality_enhancement, retrieve_retry_count)

        # Get backend-specific configuration with fallbacks
        pixel_format = backend_kwargs.get("pixel_format")
        buffer_count = backend_kwargs.get("buffer_count")
        timeout_ms = backend_kwargs.get("timeout_ms")

        if pixel_format is None:
            pixel_format = getattr(self.camera_config, "pixel_format", "BGR8")
        if buffer_count is None:
            buffer_count = getattr(self.camera_config, "buffer_count", 25)
        if timeout_ms is None:
            timeout_ms = getattr(self.camera_config, "timeout_ms", 5000)

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

        # Mock camera state
        self.exposure_time = 20000.0
        self.gain = 1.0
        self.roi = {"x": 0, "y": 0, "width": 1920, "height": 1080}
        self.white_balance_mode = "off"
        self.triggermode = self.camera_config.cameras.trigger_mode
        self.image_counter = 0

        # Internal state
        self.converter = None
        self.grabbing_mode = "LatestImageOnly"  # Mock grabbing mode
        self._grabbing = False

        # Synthetic image knobs for testing
        self.synthetic_pattern: str = str(backend_kwargs.get("synthetic_pattern", "auto")).lower()
        self.synthetic_checker_size: int = int(backend_kwargs.get("synthetic_checker_size", 50))
        self.synthetic_overlay_text: bool = bool(backend_kwargs.get("synthetic_overlay_text", True))

        # Optionally override image size via constructor
        syn_w = backend_kwargs.get("synthetic_width")
        syn_h = backend_kwargs.get("synthetic_height")

        # Store synthetic dimensions as attributes (needed by reset_ROI)
        self.synthetic_width = self.roi["width"]  # Default from ROI
        self.synthetic_height = self.roi["height"]  # Default from ROI

        try:
            if syn_w is not None:
                self.roi["width"] = int(syn_w)
                self.synthetic_width = int(syn_w)
            if syn_h is not None:
                self.roi["height"] = int(syn_h)
                self.synthetic_height = int(syn_h)
        except Exception:
            # Ignore invalid overrides; keep defaults
            pass

        # Error/cancellation simulation flags (constructor kwargs override env defaults)
        env_fail_init = os.getenv("MOCK_BASLER_FAIL_INIT", "false").lower() == "true"
        env_fail_capture = os.getenv("MOCK_BASLER_FAIL_CAPTURE", "false").lower() == "true"
        env_timeout = os.getenv("MOCK_BASLER_TIMEOUT", "false").lower() == "true"
        env_cancel = os.getenv("MOCK_BASLER_CANCEL", "false").lower() == "true"

        self.fail_init = bool(backend_kwargs.get("simulate_fail_init", env_fail_init))
        self.fail_capture = bool(backend_kwargs.get("simulate_fail_capture", env_fail_capture))
        self.simulate_timeout = bool(backend_kwargs.get("simulate_timeout", env_timeout))
        self.simulate_cancel = bool(backend_kwargs.get("simulate_cancel", env_cancel))

        # Initialize camera state (actual initialization happens in async initialize method)
        self.initialized = False
        self.camera = None

        self.logger.debug(f"Mock Basler camera '{self.camera_name}' initialized successfully")

    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """Get available mock Basler cameras.

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
                    "user_defined_name": camera_name,
                }
            return camera_details

        return mock_cameras

    async def initialize(self) -> Tuple[bool, Any, Any]:
        """Initialize the mock camera connection.

        Returns:
            Tuple of (success status, mock camera object, None)

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
                "model": "acA1920-40uc",
                "serial": "12345001",
                "connected": True,
            }

            # Load config if provided
            if self.camera_config_path and os.path.exists(self.camera_config_path):
                await self.import_config(self.camera_config_path)

            # Set initialized flag
            self.initialized = True
            self.logger.info(f"Mock Basler camera '{self.camera_name}' initialized successfully")

            return True, mock_camera_object, None

        except (CameraNotFoundError, CameraConnectionError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error initializing mock Basler camera '{self.camera_name}': {str(e)}")
            raise CameraInitializationError(f"Unexpected error initializing mock camera '{self.camera_name}': {str(e)}")

    async def capture(self) -> np.ndarray:
        """Capture a single image from the mock camera.

        Returns:
            Captured BGR image array

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            CameraCaptureError: If image capture fails
            CameraTimeoutError: If capture times out
        """
        if not self.initialized:
            raise CameraConnectionError(f"Mock camera '{self.camera_name}' is not initialized")

        # Simulate different error/cancellation conditions
        if self.fail_capture:
            raise CameraCaptureError(f"Simulated capture failure for mock camera '{self.camera_name}'")

        if self.simulate_timeout:
            raise CameraTimeoutError(f"Simulated timeout for mock camera '{self.camera_name}'")

        if self.simulate_cancel:
            raise asyncio.CancelledError()

        try:
            # Auto-start grabbing if not already grabbing, to mirror SDK behavior
            if not self.IsGrabbing():
                self.StartGrabbing(self.grabbing_mode)

            # Simulate capture delay based on exposure time
            capture_delay = max(0.01, self.exposure_time / 1000000.0)  # Convert to seconds
            await asyncio.sleep(min(capture_delay, 0.1))  # Cap at 100ms for testing

            # Generate synthetic image off the event loop
            image = await asyncio.to_thread(self._generate_synthetic_image)

            # Apply image enhancement if enabled (off the event loop)
            if self.img_quality_enhancement:
                try:
                    image = await asyncio.to_thread(self._enhance_image, image)
                except Exception as enhance_error:
                    self.logger.warning(f"Image enhancement failed, using original image: {enhance_error}")

            self.image_counter += 1
            self.logger.debug(f"Captured frame {self.image_counter} from mock camera '{self.camera_name}'")
            return image

        except asyncio.CancelledError:
            # Propagate cancellations unchanged to mirror real behavior
            raise
        except (CameraConnectionError, CameraCaptureError, CameraTimeoutError):
            raise
        except Exception as e:
            self.logger.error(f"Mock capture failed for camera '{self.camera_name}': {str(e)}")
            raise CameraCaptureError(f"Failed to capture image from mock camera '{self.camera_name}': {str(e)}")

    def IsGrabbing(self) -> bool:
        """Return whether the mock camera is currently in a grabbing state."""
        return self._grabbing

    def StartGrabbing(self, grabbing_mode: Optional[str] = None) -> None:
        """Enter grabbing state, optionally updating grabbing mode.

        Args:
            grabbing_mode: Optional grabbing mode string; if provided, updates current mode.
        """
        if grabbing_mode is not None:
            self.grabbing_mode = grabbing_mode
        self._grabbing = True
        self.logger.debug(f"StartGrabbing called; mode={self.grabbing_mode}")

    def StopGrabbing(self) -> None:
        """Exit grabbing state."""
        self._grabbing = False
        self.logger.debug("StopGrabbing called; grabbing stopped")

    async def get_image_quality_enhancement(self) -> bool:
        """Get image quality enhancement setting.

        Returns:
            True if enhancement is enabled, otherwise False.
        """
        return self.img_quality_enhancement

    async def set_image_quality_enhancement(self, value: bool):
        """Set image quality enhancement setting.

        Args:
            value: True to enable enhancement, False to disable.
        """
        self.img_quality_enhancement = value
        if value and not hasattr(self, "_enhancement_initialized"):
            self._initialize_image_enhancement()
        self.logger.debug(f"Image quality enhancement set to {value} for mock camera '{self.camera_name}'")

    async def get_exposure_range(self) -> List[Union[int, float]]:
        """Get the supported exposure time range in microseconds.

        Returns:
            List with [min_exposure, max_exposure] in microseconds
        """
        return [20.0, 1000000.0]

    async def get_exposure(self) -> float:
        """Get current exposure time in microseconds.

        Returns:
            Current exposure time
        """
        return self.exposure_time

    async def set_exposure(self, exposure: Union[int, float]):
        """Set the camera exposure time in microseconds.

        Args:
            exposure: Exposure time in microseconds


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
            self.logger.debug(f"Exposure set to {exposure} for mock camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set exposure for mock camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set exposure for mock camera '{self.camera_name}': {str(e)}")

    async def get_triggermode(self) -> str:
        """Get current trigger mode.

        Returns:
            Current trigger mode
        """
        return self.triggermode

    async def set_triggermode(self, triggermode: str = "continuous"):
        """Set trigger mode.

        Args:
            triggermode: Trigger mode ("continuous" or "trigger")

        Raises:
            CameraConfigurationError: If trigger mode is invalid
        """
        if triggermode not in ["continuous", "trigger"]:
            raise CameraConfigurationError(f"Invalid trigger mode: {triggermode}")

        try:
            self.triggermode = triggermode
            self.logger.debug(f"Trigger mode set to '{triggermode}' for mock camera '{self.camera_name}'")
        except Exception as e:
            self.logger.error(f"Failed to set trigger mode for mock camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set trigger mode for mock camera '{self.camera_name}': {str(e)}")

    async def check_connection(self) -> bool:
        """Check if mock camera is connected and operational.

        Returns:
            True if connected and operational, False otherwise
        """
        if not self.initialized:
            return False

        try:
            img = await self.capture()
            return img is not None and img.shape[0] > 0 and img.shape[1] > 0
        except Exception as e:
            self.logger.warning(f"Connection check failed for mock camera '{self.camera_name}': {str(e)}")
            return False

    async def import_config(self, config_path: str):
        """Import camera configuration from common JSON format.

        Args:
            config_path: Path to configuration file

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
                with open(config_path, "r") as f:
                    config_data = json.load(f)

                # Apply configuration settings using common format
                if "exposure_time" in config_data:
                    self.exposure_time = float(config_data["exposure_time"])
                if "gain" in config_data:
                    self.gain = float(config_data["gain"])
                if "trigger_mode" in config_data:
                    self.triggermode = config_data["trigger_mode"]
                if "white_balance" in config_data:
                    self.white_balance_mode = config_data["white_balance"]
                if "image_enhancement" in config_data:
                    self.img_quality_enhancement = config_data["image_enhancement"]
                if "roi" in config_data:
                    self.roi = config_data["roi"]
                if "retrieve_retry_count" in config_data:
                    self.retrieve_retry_count = config_data["retrieve_retry_count"]
                if "timeout_ms" in config_data:
                    self.timeout_ms = config_data["timeout_ms"]
                if "pixel_format" in config_data:
                    self.default_pixel_format = config_data["pixel_format"]

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                raise CameraConfigurationError(f"Invalid JSON configuration format: {e}")

            self.logger.debug(f"Configuration imported from '{config_path}' for mock camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to import config from '{config_path}': {str(e)}")
            raise CameraConfigurationError(f"Failed to import config from '{config_path}': {str(e)}")

    async def export_config(self, config_path: str):
        """Export camera configuration to common JSON format.

        Args:
            config_path: Path to save configuration file
        """
        try:
            # Create common format configuration data
            config_data = {
                "camera_type": "mock_basler",
                "camera_name": self.camera_name,
                "timestamp": time.time(),
                "exposure_time": self.exposure_time,
                "gain": self.gain,
                "trigger_mode": self.triggermode,
                "white_balance": self.white_balance_mode,
                "width": self.roi["width"],
                "height": self.roi["height"],
                "roi": self.roi,
                "pixel_format": self.default_pixel_format,
                "image_enhancement": self.img_quality_enhancement,
                "retrieve_retry_count": self.retrieve_retry_count,
                "timeout_ms": self.timeout_ms,
                "buffer_count": self.buffer_count,
            }

            # Ensure directory exists
            os.makedirs(os.path.dirname(config_path), exist_ok=True)

            # Write configuration as JSON
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            self.logger.debug(
                f"Configuration exported to '{config_path}' for mock camera '{self.camera_name}' using common JSON format"
            )
        except Exception as e:
            self.logger.error(f"Failed to export config to '{config_path}': {str(e)}")
            return False

    async def set_ROI(self, x: int, y: int, width: int, height: int):
        """Set Region of Interest (ROI).

        Args:
            x: ROI x offset
            y: ROI y offset
            width: ROI width
            height: ROI height

        Raises:
            CameraConfigurationError: If ROI parameters are invalid
        """
        try:
            # Simulate async operation delay
            await asyncio.sleep(0.001)

            if width <= 0 or height <= 0:
                raise CameraConfigurationError(f"Invalid ROI dimensions: {width}x{height}")

            if x < 0 or y < 0:
                raise CameraConfigurationError(f"Invalid ROI offset: ({x}, {y})")

            self.roi = {"x": x, "y": y, "width": width, "height": height}
            self.logger.debug(f"ROI set to ({x}, {y}, {width}, {height}) for mock camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set ROI for mock camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set ROI for mock camera '{self.camera_name}': {str(e)}")

    async def get_ROI(self) -> Dict[str, int]:
        """Get current Region of Interest (ROI).

        Returns:
            Dictionary with ROI parameters
        """
        # Simulate async operation
        await asyncio.sleep(0.001)
        return self.roi.copy()

    async def reset_ROI(self):
        """Reset ROI to full sensor size."""
        try:
            # Simulate async operation
            await asyncio.sleep(0.001)
            self.roi = {"x": 0, "y": 0, "width": self.synthetic_width, "height": self.synthetic_height}
            self.logger.debug(f"ROI reset to full size for mock camera '{self.camera_name}'")
        except Exception as e:
            self.logger.error(f"Failed to reset ROI for mock camera '{self.camera_name}': {str(e)}")
            return False

    async def set_gain(self, gain: Union[int, float]):
        """Set camera gain.

        Args:
            gain: Gain value

        Raises:
            CameraConfigurationError: If gain value is out of range
        """
        try:
            # Simulate async operation
            await asyncio.sleep(0.001)

            if gain < 1.0 or gain > 16.0:
                raise CameraConfigurationError(f"Gain {gain} out of range [1.0, 16.0]")

            self.gain = float(gain)
            self.logger.debug(f"Gain set to {gain} for mock camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set gain for mock camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set gain for mock camera '{self.camera_name}': {str(e)}")

    async def get_gain_range(self) -> List[Union[int, float]]:
        """Get the supported gain range.

        Returns:
            List with [min_gain, max_gain]
        """
        # Simulate async operation
        await asyncio.sleep(0.001)
        return [1.0, 16.0]

    async def get_gain(self) -> float:
        """Get current camera gain.

        Returns:
            Current gain value
        """
        # Simulate async operation
        await asyncio.sleep(0.001)
        return self.gain

    async def get_wb(self) -> str:
        """Get current white balance mode.

        Returns:
            Current white balance mode
        """
        return self.white_balance_mode

    async def set_auto_wb_once(self, value: str):
        """Set white balance mode.

        Args:
            value: White balance mode
        """
        try:
            self.white_balance_mode = value
            self.logger.debug(f"White balance set to '{value}' for mock camera '{self.camera_name}'")
        except Exception as e:
            self.logger.error(f"Failed to set white balance for mock camera '{self.camera_name}': {str(e)}")
            return False

    async def get_wb_range(self) -> List[str]:
        """Get available white balance modes.

        Returns:
            List of available white balance modes
        """
        # Simulate async operation
        await asyncio.sleep(0.001)
        return ["off", "auto", "continuous", "once"]

    async def get_pixel_format_range(self) -> List[str]:
        """Get available pixel formats.

        Returns:
            List of available pixel formats
        """
        # Simulate async operation
        await asyncio.sleep(0.001)
        return ["BGR8", "RGB8", "Mono8", "BayerRG8", "BayerGB8", "BayerGR8", "BayerBG8"]

    async def get_current_pixel_format(self) -> str:
        """Get current pixel format.

        Returns:
            Current pixel format
        """
        # Simulate async operation
        await asyncio.sleep(0.001)
        return self.default_pixel_format

    async def set_pixel_format(self, pixel_format: str):
        """Set pixel format.

        Args:
            pixel_format: Pixel format to set

        Raises:
            CameraConfigurationError: If pixel format is not supported
        """
        try:
            # Simulate async operation
            await asyncio.sleep(0.001)
            available_formats = await self.get_pixel_format_range()
            if pixel_format not in available_formats:
                raise CameraConfigurationError(f"Unsupported pixel format: {pixel_format}")

            self.default_pixel_format = pixel_format
            self.logger.debug(f"Pixel format set to '{pixel_format}' for mock camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set pixel format for mock camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set pixel format for mock camera '{self.camera_name}': {str(e)}")

    # Width/Height range methods
    async def get_width_range(self) -> List[int]:
        """Get camera width range.

        Returns:
            List containing [min_width, max_width]
        """
        await asyncio.sleep(0.001)
        return [320, 1920]

    async def get_height_range(self) -> List[int]:
        """Get camera height range.

        Returns:
            List containing [min_height, max_height]
        """
        await asyncio.sleep(0.001)
        return [240, 1080]

    # Network-related methods (simulated for GigE cameras)
    async def set_bandwidth_limit(self, limit_mbps: Optional[float]):
        """Set GigE camera bandwidth limit in Mbps (simulated)."""
        await asyncio.sleep(0.001)
        self.logger.debug(f"Bandwidth limit set to {limit_mbps} Mbps for mock camera '{self.camera_name}' (simulated)")

    async def get_bandwidth_limit(self) -> float:
        """Get current bandwidth limit (simulated)."""
        await asyncio.sleep(0.001)
        return 125.0  # Simulated 1Gbps = 125MB/s

    async def set_packet_size(self, size: int):
        """Set GigE packet size for network optimization (simulated)."""
        await asyncio.sleep(0.001)
        self.logger.debug(f"Packet size set to {size} bytes for mock camera '{self.camera_name}' (simulated)")

    async def get_packet_size(self) -> int:
        """Get current packet size (simulated)."""
        await asyncio.sleep(0.001)
        return 1500  # Simulated standard MTU

    async def set_inter_packet_delay(self, delay_ticks: int):
        """Set inter-packet delay for network traffic control (simulated)."""
        await asyncio.sleep(0.001)
        self.logger.debug(
            f"Inter-packet delay set to {delay_ticks} ticks for mock camera '{self.camera_name}' (simulated)"
        )

    async def get_inter_packet_delay(self) -> int:
        """Get current inter-packet delay (simulated)."""
        await asyncio.sleep(0.001)
        return 0  # Simulated no delay

    async def close(self):
        """Close the mock camera and release resources."""
        try:
            self._grabbing = False
            self.initialized = False
            self.camera = None
            self.logger.info(f"Mock Basler camera '{self.camera_name}' closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing mock camera '{self.camera_name}': {str(e)}")

    # ===== Private helpers =====
    def _initialize_image_enhancement(self):
        """Initialize image enhancement parameters for mock camera."""
        try:
            # Mock CLAHE parameters - just mark as initialized for consistency
            self._enhancement_initialized = True
            self.logger.debug(f"Image enhancement initialized for mock camera '{self.camera_name}'")
        except Exception as e:
            self.logger.error(f"Failed to initialize image enhancement for mock camera '{self.camera_name}': {str(e)}")

    def _generate_synthetic_image(self) -> np.ndarray:
        """Generate synthetic test image using vectorized operations for performance.

        Returns:
            BGR image array
        """
        width = self.roi["width"]
        height = self.roi["height"]
        try:
            # Use vectorized operations for much better performance
            x_coords = np.arange(width)
            y_coords = np.arange(height)
            X, Y = np.meshgrid(x_coords, y_coords)

            # Determine pattern selection
            pattern_map = {"gradient": 0, "checkerboard": 1, "circular": 2, "noise": 3}
            if self.synthetic_pattern in pattern_map:
                pattern_type = pattern_map[self.synthetic_pattern]
            else:
                # auto-rotate
                pattern_type = self.image_counter % 4

            if pattern_type == 0:
                # Gradient pattern using vectorized operations
                r_channel = (128 + 127 * np.sin(2 * np.pi * X / width)).astype(np.uint8)
                g_channel = (128 + 127 * np.cos(2 * np.pi * Y / height)).astype(np.uint8)
                b_channel = (64 + 64 * np.sin(2 * np.pi * (X + Y) / (width + height))).astype(np.uint8)
                image = np.stack([b_channel, g_channel, r_channel], axis=-1)
            elif pattern_type == 1:
                # Checkerboard pattern using vectorized operations
                checker_size = int(self.synthetic_checker_size) if self.synthetic_checker_size > 0 else 50
                checker_x = (X // checker_size) % 2
                checker_y = (Y // checker_size) % 2
                checkerboard = (checker_x + checker_y) % 2
                image = np.where(checkerboard[..., np.newaxis], 200, 50).astype(np.uint8)
                image = np.repeat(image, 3, axis=-1)
            elif pattern_type == 2:
                # Circular pattern using vectorized operations
                center_x, center_y = width // 2, height // 2
                max_radius = min(width, height) // 2
                dist = np.sqrt((X - center_x) ** 2 + (Y - center_y) ** 2)
                intensity = (128 + 127 * np.sin(2 * np.pi * dist / max_radius)).astype(np.uint8)
                image = np.stack([intensity, intensity // 2, (255 - intensity) // 2], axis=-1)
            else:
                # Simple noise pattern (much faster than Gaussian blur)
                image = np.random.randint(50, 200, (height, width, 3), dtype=np.uint8)

            # Apply exposure effect
            exposure_factor = min(1.0, self.exposure_time / 20000.0)  # Normalize to 20ms
            image = (image * exposure_factor).astype(np.uint8)

            # Add gain effect
            if self.gain > 1.0:
                image = np.clip(image * self.gain, 0, 255).astype(np.uint8)

            # Add noise based on gain (vectorized)
            if self.gain > 1.0:
                noise_level = int((self.gain - 1.0) * 10)
                noise = np.random.randint(-noise_level, noise_level + 1, image.shape, dtype=np.int16)
                image = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)

            # Add text overlay (optional)
            if self.synthetic_overlay_text:
                timestamp = time.strftime("%H:%M:%S")
                font_scale = min(width, height) / 1000.0  # Scale font with image size
                thickness = max(1, int(font_scale * 2))

                cv2.putText(
                    image,
                    f"Mock Basler {timestamp}",
                    (50, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (255, 255, 255),
                    thickness,
                )
                cv2.putText(
                    image,
                    f"Frame: {self.image_counter}",
                    (50, 90),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (255, 255, 255),
                    thickness,
                )
                cv2.putText(
                    image,
                    f"Exp: {self.exposure_time:.0f}us",
                    (50, 130),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (255, 255, 255),
                    thickness,
                )
                cv2.putText(
                    image,
                    f"Gain: {self.gain:.1f}",
                    (50, 170),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (255, 255, 255),
                    thickness,
                )
                cv2.putText(
                    image,
                    f"ROI: {width}x{height}",
                    (50, 210),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (255, 255, 255),
                    thickness,
                )

            return image

        except Exception as e:
            self.logger.error(f"Failed to generate synthetic image: {str(e)}")
            # Return simple pattern as fallback
            return np.full((height, width, 3), 128, dtype=np.uint8)

    def _enhance_image(self, image: np.ndarray) -> np.ndarray:
        """Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) enhancement.

        Args:
            image: Input BGR image

        Returns:
            Enhanced BGR image
        """
        try:
            # Convert to LAB color space
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            length, a, b = cv2.split(lab)

            # Apply CLAHE to L channel
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(length)

            # Merge channels and convert back to BGR
            enhanced_lab = cv2.merge((cl, a, b))
            enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

            # Additional enhancement: gamma correction
            gamma = 1.2
            enhanced_img = np.power(enhanced_img / 255.0, gamma) * 255.0
            enhanced_img = enhanced_img.astype(np.uint8)

            # Slight contrast adjustment
            alpha = 1.1
            beta = 10
            enhanced_img = cv2.convertScaleAbs(enhanced_img, alpha=alpha, beta=beta)

            return enhanced_img
        except Exception as e:
            self.logger.error(f"Image enhancement failed for mock camera '{self.camera_name}': {str(e)}")
            return image
