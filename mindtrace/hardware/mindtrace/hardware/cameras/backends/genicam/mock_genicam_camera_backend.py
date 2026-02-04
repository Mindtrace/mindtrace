"""Mock GenICam Camera Backend Module"""

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


class MockGenICamCameraBackend(CameraBackend):
    """Mock GenICam Camera Backend Implementation

    This class provides a mock implementation of the GenICam camera backend for testing and development. It simulates
    GenICam camera functionality without requiring actual hardware, Harvesters library, or GenTL Producer files.

    Features:
        - Complete simulation of GenICam camera API
        - Configurable image generation with realistic patterns
        - Error simulation for testing error handling
        - Configuration import/export simulation
        - Camera control features (exposure, ROI, trigger modes, etc.)
        - Vendor-specific quirks simulation (Keyence, Basler, etc.)
        - Realistic timing and behavior simulation

    Usage::

        from mindtrace.hardware.cameras.backends.genicam import MockGenICamCameraBackend

        camera = MockGenICamCameraBackend("mock_keyence_001", vendor="KEYENCE")
        await camera.set_exposure(50000)
        image = await camera.capture()
        await camera.close()

    Error Simulation:
        Enable error simulation via environment variables:
        - MOCK_GENICAM_FAIL_INIT: Simulate initialization failure
        - MOCK_GENICAM_FAIL_CAPTURE: Simulate capture failure
        - MOCK_GENICAM_TIMEOUT: Simulate timeout errors

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
        vendor: Simulated camera vendor
        model: Simulated camera model
        serial_number: Simulated serial number
        vendor_quirks: Vendor-specific parameter handling flags
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
        """Initialize mock GenICam camera.

        Args:
            camera_name: Camera identifier
            camera_config: Path to configuration file (simulated)
            img_quality_enhancement: Enable image enhancement simulation (uses config default if None)
            retrieve_retry_count: Number of capture retry attempts (uses config default if None)
            **backend_kwargs: Backend-specific parameters:
                - vendor: Simulated vendor ("KEYENCE", "BASLER", "FLIR", etc.)
                - model: Simulated model name
                - serial_number: Simulated serial number
                - cti_path: Simulated CTI path (ignored in mock)
                - timeout_ms: Timeout in milliseconds
                - buffer_count: Buffer count (simulated)
                - simulate_fail_init: If True, simulate initialization failure
                - simulate_fail_capture: If True, simulate capture failure
                - simulate_timeout: If True, simulate timeout on capture
                - synthetic_width: Override synthetic image width (int)
                - synthetic_height: Override synthetic image height (int)
                - synthetic_pattern: One of {"auto","gradient","checkerboard","circular","noise"}
                - synthetic_overlay_text: If False, disables text overlays in synthetic images

        Raises:
            CameraConfigurationError: If configuration is invalid
            CameraInitializationError: If initialization fails (when simulated)
        """
        super().__init__(camera_name, camera_config, img_quality_enhancement, retrieve_retry_count)

        # Get backend-specific configuration with fallbacks
        self.vendor = backend_kwargs.get("vendor", "KEYENCE")
        self.model = backend_kwargs.get("model", "VJ-H500CX")
        self.serial_number = backend_kwargs.get("serial_number", f"MOCK_{camera_name}")
        timeout_ms = backend_kwargs.get("timeout_ms")
        buffer_count = backend_kwargs.get("buffer_count")

        if timeout_ms is None:
            timeout_ms = getattr(self.camera_config, "timeout_ms", 5000)
        if buffer_count is None:
            buffer_count = getattr(self.camera_config, "buffer_count", 10)

        # Validate parameters
        if buffer_count < 1:
            raise CameraConfigurationError("Buffer count must be at least 1")
        if timeout_ms < 100:
            raise CameraConfigurationError("Timeout must be at least 100ms")

        # Store configuration
        self.camera_config_path = camera_config
        self.timeout_ms = timeout_ms
        self.buffer_count = buffer_count

        # Simulation parameters
        self.synthetic_width = backend_kwargs.get("synthetic_width", 2432)
        self.synthetic_height = backend_kwargs.get("synthetic_height", 2040)
        self.synthetic_pattern = backend_kwargs.get("synthetic_pattern", "auto")
        self.synthetic_overlay_text = backend_kwargs.get("synthetic_overlay_text", True)

        # Error simulation flags
        self.fail_init = backend_kwargs.get(
            "simulate_fail_init", os.getenv("MOCK_GENICAM_FAIL_INIT", "false").lower() == "true"
        )
        self.fail_capture = backend_kwargs.get(
            "simulate_fail_capture", os.getenv("MOCK_GENICAM_FAIL_CAPTURE", "false").lower() == "true"
        )
        self.simulate_timeout = backend_kwargs.get(
            "simulate_timeout", os.getenv("MOCK_GENICAM_TIMEOUT", "false").lower() == "true"
        )

        # Camera state
        self.exposure_time = 50000.0  # 50ms
        self.gain = 2.0
        self.roi = {"x": 0, "y": 0, "width": self.synthetic_width, "height": self.synthetic_height}
        self.pixel_format = "RGB8"
        self.image_counter = 0
        self.triggermode = self.camera_config.cameras.trigger_mode

        # Vendor-specific quirks simulation
        self.vendor_quirks = self._setup_vendor_quirks()

        # Device info simulation
        self.device_info = {
            "serial_number": self.serial_number,
            "model": self.model,
            "vendor": self.vendor,
            "device_class": "Camera",
            "display_name": f"{self.vendor} {self.model} ({self.serial_number})",
        }

        # Derived operation timeout
        self._op_timeout_s = max(3.0, float(self.timeout_ms) / 1000.0)

        self.logger.info(f"Mock GenICam camera '{self.camera_name}' initialized successfully (vendor: {self.vendor})")

    def _setup_vendor_quirks(self) -> Dict[str, bool]:
        """Setup vendor-specific parameter handling quirks."""
        quirks = {
            "use_integer_exposure": False,
            "exposure_node_name": "ExposureTime",
            "gain_node_name": "Gain",
        }

        if "KEYENCE" in self.vendor.upper():
            quirks.update(
                {
                    "use_integer_exposure": True,
                    "exposure_node_name": "ExposureTime",
                    "gain_node_name": "Gain",
                }
            )
            self.logger.debug("Mock camera using Keyence quirks (integer exposure)")
        elif "BASLER" in self.vendor.upper():
            quirks.update(
                {
                    "use_integer_exposure": False,
                    "exposure_node_name": "ExposureTime",
                    "gain_node_name": "Gain",
                }
            )
            self.logger.debug("Mock camera using Basler quirks (float exposure)")

        return quirks

    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """Get available mock GenICam cameras.

        Args:
            include_details: If True, return detailed information

        Returns:
            List of camera names or dict with details
        """
        # Simulate multiple mock cameras
        mock_cameras = [
            {
                "identifier": "MOCK_KEYENCE_001",
                "details": {
                    "serial_number": "MOCK_KEYENCE_001",
                    "model": "VJ-H500CX",
                    "vendor": "KEYENCE",
                    "device_class": "Camera",
                    "interface": "GigEVision",
                    "display_name": "KEYENCE VJ-H500CX (MOCK_KEYENCE_001)",
                    "user_defined_name": "",
                    "device_id": "KEYENCE_VJ_001",
                },
            },
            {
                "identifier": "MOCK_KEYENCE_002",
                "details": {
                    "serial_number": "MOCK_KEYENCE_002",
                    "model": "VJ-H500CX",
                    "vendor": "KEYENCE",
                    "device_class": "Camera",
                    "interface": "GigEVision",
                    "display_name": "KEYENCE VJ-H500CX (MOCK_KEYENCE_002)",
                    "user_defined_name": "",
                    "device_id": "KEYENCE_VJ_002",
                },
            },
            {
                "identifier": "MOCK_BASLER_001",
                "details": {
                    "serial_number": "MOCK_BASLER_001",
                    "model": "acA2440-75gm",
                    "vendor": "BASLER",
                    "device_class": "Camera",
                    "interface": "GigEVision",
                    "display_name": "BASLER acA2440-75gm (MOCK_BASLER_001)",
                    "user_defined_name": "",
                    "device_id": "BASLER_ACA_001",
                },
            },
        ]

        if include_details:
            return {cam["identifier"]: cam["details"] for cam in mock_cameras}
        else:
            return [cam["identifier"] for cam in mock_cameras]

    async def initialize(self) -> Tuple[bool, Any, Any]:
        """Initialize the mock camera connection.

        Returns:
            Tuple of (success status, mock camera object, device_info)

        Raises:
            CameraNotFoundError: If camera not found (when simulated)
            CameraInitializationError: If initialization fails (when simulated)
            CameraConnectionError: If connection fails (when simulated)
        """
        if self.fail_init:
            raise CameraInitializationError(f"Simulated initialization failure for camera '{self.camera_name}'")

        # Simulate discovery delay
        await asyncio.sleep(0.1)

        # Check if camera name matches available mock cameras
        available_cameras = self.get_available_cameras()
        if self.camera_name not in available_cameras:
            raise CameraNotFoundError(
                f"Mock camera '{self.camera_name}' not found. Available cameras: {available_cameras}"
            )

        # Simulate initialization work
        await asyncio.sleep(0.2)

        # Load config if provided
        if self.camera_config_path and os.path.exists(self.camera_config_path):
            await self.import_config(self.camera_config_path)

        self.initialized = True

        # Return mock objects
        mock_camera_object = {"type": "mock_genicam", "name": self.camera_name}

        return True, mock_camera_object, self.device_info

    async def get_exposure_range(self) -> List[Union[int, float]]:
        """Get the simulated exposure time range in microseconds."""
        if not self.initialized:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        # Simulate vendor-specific ranges
        if "KEYENCE" in self.vendor.upper():
            return [10.0, 10000000.0]  # 10μs to 10s
        elif "BASLER" in self.vendor.upper():
            return [1.0, 1000000.0]  # 1μs to 1s
        else:
            return [1.0, 5000000.0]  # 1μs to 5s

    async def get_exposure(self) -> float:
        """Get current simulated exposure time in microseconds."""
        if not self.initialized:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        return self.exposure_time

    async def set_exposure(self, exposure: Union[int, float]):
        """Set the simulated camera exposure time in microseconds."""
        if not self.initialized:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        min_exp, max_exp = await self.get_exposure_range()

        if exposure < min_exp or exposure > max_exp:
            raise CameraConfigurationError(
                f"Exposure {exposure} outside valid range [{min_exp}, {max_exp}] for camera '{self.camera_name}'"
            )

        # Apply vendor-specific type conversion
        if self.vendor_quirks.get("use_integer_exposure", False):
            self.exposure_time = float(int(exposure))
        else:
            self.exposure_time = float(exposure)

        # Simulate setting delay
        await asyncio.sleep(0.05)

        self.logger.debug(f"Mock camera exposure set to {self.exposure_time}μs")

    async def get_triggermode(self) -> str:
        """Get current simulated trigger mode."""
        if not self.initialized:
            return "continuous"

        return self.triggermode

    async def set_triggermode(self, triggermode: str = "continuous"):
        """Set the simulated camera's trigger mode."""
        if not self.initialized:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        if triggermode not in ["continuous", "trigger"]:
            raise CameraConfigurationError(
                f"Invalid trigger mode '{triggermode}' for camera '{self.camera_name}'. "
                "Must be 'continuous' or 'trigger'"
            )

        self.triggermode = triggermode

        # Simulate setting delay
        await asyncio.sleep(0.05)

        self.logger.debug(f"Mock camera trigger mode set to '{triggermode}'")

    async def capture(self) -> np.ndarray:
        """Capture a simulated image from the mock camera."""
        if not self.initialized:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        if self.fail_capture:
            raise CameraCaptureError(f"Simulated capture failure for camera '{self.camera_name}'")

        if self.simulate_timeout:
            raise CameraTimeoutError(f"Simulated timeout for camera '{self.camera_name}'")

        # Simulate capture time based on exposure
        capture_delay = max(0.01, min(0.5, self.exposure_time / 1000000.0))  # Convert μs to seconds
        await asyncio.sleep(capture_delay)

        # Generate synthetic image
        image = await self._generate_synthetic_image()

        if self.img_quality_enhancement:
            image = await self._enhance_image(image)

        self.image_counter += 1
        return image

    async def _generate_synthetic_image(self) -> np.ndarray:
        """Generate a synthetic image based on configured pattern."""
        width = self.roi["width"]
        height = self.roi["height"]

        def generate():
            if self.synthetic_pattern == "gradient":
                # Create gradient pattern
                image = np.zeros((height, width, 3), dtype=np.uint8)
                for y in range(height):
                    for x in range(width):
                        image[y, x] = [
                            int(255 * x / width),
                            int(255 * y / height),
                            int(255 * (x + y) / (width + height)),
                        ]

            elif self.synthetic_pattern == "checkerboard":
                # Create checkerboard pattern
                checker_size = 50
                image = np.zeros((height, width, 3), dtype=np.uint8)
                for y in range(height):
                    for x in range(width):
                        if ((x // checker_size) + (y // checker_size)) % 2:
                            image[y, x] = [255, 255, 255]
                        else:
                            image[y, x] = [0, 0, 0]

            elif self.synthetic_pattern == "circular":
                # Create circular pattern
                image = np.zeros((height, width, 3), dtype=np.uint8)
                center_x, center_y = width // 2, height // 2
                max_radius = min(center_x, center_y)
                for y in range(height):
                    for x in range(width):
                        radius = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
                        intensity = int(255 * (1 - radius / max_radius)) if radius < max_radius else 0
                        image[y, x] = [intensity, intensity, intensity]

            elif self.synthetic_pattern == "noise":
                # Create noise pattern
                image = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)

            else:  # "auto" or default
                # Create a pattern based on camera info
                image = np.zeros((height, width, 3), dtype=np.uint8)

                # Base color based on vendor
                if "KEYENCE" in self.vendor.upper():
                    base_color = [0, 100, 200]  # Blue-ish
                elif "BASLER" in self.vendor.upper():
                    base_color = [200, 100, 0]  # Orange-ish
                else:
                    base_color = [100, 200, 100]  # Green-ish

                # Fill with base color
                image[:, :] = base_color

                # Add some pattern variation
                for i in range(10):
                    x = np.random.randint(0, width)
                    y = np.random.randint(0, height)
                    radius = np.random.randint(20, 100)
                    cv2.circle(image, (x, y), radius, (255, 255, 255), -1)

            # Add text overlay if enabled
            if self.synthetic_overlay_text:
                # Add camera info text
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 1.0
                color = (255, 255, 255)
                thickness = 2

                text_lines = [
                    f"{self.vendor} {self.model}",
                    f"SN: {self.serial_number}",
                    f"Frame: {self.image_counter + 1}",
                    f"Exp: {self.exposure_time:.0f}μs",
                    f"Gain: {self.gain:.1f}",
                    f"Mode: {self.triggermode}",
                ]

                y_offset = 30
                for i, line in enumerate(text_lines):
                    y_pos = y_offset + i * 30
                    cv2.putText(image, line, (10, y_pos), font, font_scale, color, thickness)

                # Add timestamp
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                cv2.putText(image, timestamp, (10, height - 20), font, font_scale * 0.7, color, thickness)

            return image

        return await asyncio.to_thread(generate)

    async def _enhance_image(self, image: np.ndarray) -> np.ndarray:
        """Apply simulated CLAHE enhancement to the image."""
        try:

            def enhance():
                lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
                length, a, b = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                cl = clahe.apply(length)
                enhanced_lab = cv2.merge((cl, a, b))
                enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
                return enhanced_img

            return await asyncio.to_thread(enhance)
        except Exception as e:
            self.logger.error(f"Image enhancement failed for camera '{self.camera_name}': {str(e)}")
            return image  # Return original if enhancement fails

    async def check_connection(self) -> bool:
        """Check if mock camera is connected and operational."""
        if not self.initialized:
            return False

        try:
            # Simulate connection check
            await asyncio.sleep(0.05)
            img = await self.capture()
            return img is not None and img.shape[0] > 0 and img.shape[1] > 0
        except Exception as e:
            self.logger.warning(f"Mock connection check failed for camera '{self.camera_name}': {str(e)}")
            return False

    async def close(self):
        """Close the mock camera and release simulated resources."""
        if self.initialized:
            self.initialized = False

            # Simulate cleanup delay
            await asyncio.sleep(0.1)

            self.logger.info(f"Mock GenICam camera '{self.camera_name}' closed")

    # Additional methods following the camera backend interface
    async def get_gain_range(self) -> List[Union[int, float]]:
        """Get simulated camera gain range."""
        if "KEYENCE" in self.vendor.upper():
            return [1.0, 7.0]  # Keyence typical range
        elif "BASLER" in self.vendor.upper():
            return [0.0, 48.0]  # Basler typical range
        else:
            return [1.0, 16.0]  # Generic range

    async def get_gain(self) -> float:
        """Get current simulated camera gain."""
        if not self.initialized:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        return self.gain

    async def set_gain(self, gain: Union[int, float]):
        """Set simulated camera gain."""
        if not self.initialized:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        min_gain, max_gain = await self.get_gain_range()

        if gain < min_gain or gain > max_gain:
            raise CameraConfigurationError(
                f"Gain {gain} outside valid range [{min_gain}, {max_gain}] for camera '{self.camera_name}'"
            )

        self.gain = float(gain)
        await asyncio.sleep(0.05)  # Simulate setting delay

        self.logger.debug(f"Mock camera gain set to {self.gain}")

    async def set_ROI(self, x: int, y: int, width: int, height: int):
        """Set simulated Region of Interest."""
        if not self.initialized:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        if width <= 0 or height <= 0:
            raise CameraConfigurationError(f"Invalid ROI dimensions: {width}x{height}")
        if x < 0 or y < 0:
            raise CameraConfigurationError(f"Invalid ROI offsets: ({x}, {y})")

        max_width = self.synthetic_width
        max_height = self.synthetic_height

        if x + width > max_width or y + height > max_height:
            raise CameraConfigurationError(
                f"ROI ({x}, {y}, {width}, {height}) exceeds sensor bounds ({max_width}x{max_height})"
            )

        self.roi = {"x": x, "y": y, "width": width, "height": height}
        await asyncio.sleep(0.05)  # Simulate setting delay

        self.logger.debug(f"Mock camera ROI set to ({x}, {y}, {width}, {height})")

    async def get_ROI(self) -> Dict[str, int]:
        """Get current simulated ROI settings."""
        if not self.initialized:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        return self.roi.copy()

    async def reset_ROI(self):
        """Reset simulated ROI to maximum sensor area."""
        if not self.initialized:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        self.roi = {"x": 0, "y": 0, "width": self.synthetic_width, "height": self.synthetic_height}
        await asyncio.sleep(0.05)  # Simulate setting delay

        self.logger.debug("Mock camera ROI reset to maximum")

    async def set_capture_timeout(self, timeout_ms: int):
        """Set capture timeout in milliseconds.

        Args:
            timeout_ms: Timeout value in milliseconds

        Raises:
            ValueError: If timeout_ms is negative
        """
        if timeout_ms < 0:
            raise ValueError(f"Timeout must be non-negative, got {timeout_ms}")

        await asyncio.sleep(0.001)  # Simulate operation delay
        self.timeout_ms = timeout_ms
        self.logger.debug(f"Set capture timeout to {timeout_ms}ms for camera '{self.camera_name}'")

    async def get_capture_timeout(self) -> int:
        """Get current capture timeout in milliseconds.

        Returns:
            Current timeout value in milliseconds
        """
        await asyncio.sleep(0.001)  # Simulate operation delay
        return self.timeout_ms

    async def import_config(self, config_path: str):
        """Import simulated camera configuration from JSON file."""
        if not os.path.exists(config_path):
            raise CameraConfigurationError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path, "r") as f:
                config_data = json.load(f)

            # Apply mock configuration
            if "exposure_time" in config_data:
                await self.set_exposure(config_data["exposure_time"])

            if "gain" in config_data:
                await self.set_gain(config_data["gain"])

            if "trigger_mode" in config_data:
                await self.set_triggermode(config_data["trigger_mode"])

            if "roi" in config_data:
                roi = config_data["roi"]
                await self.set_ROI(
                    roi.get("x", 0),
                    roi.get("y", 0),
                    roi.get("width", self.synthetic_width),
                    roi.get("height", self.synthetic_height),
                )

            if "image_enhancement" in config_data:
                self.img_quality_enhancement = config_data["image_enhancement"]

            self.logger.debug(f"Mock configuration imported from '{config_path}'")

        except Exception as e:
            raise CameraConfigurationError(f"Failed to import configuration: {str(e)}")

    async def export_config(self, config_path: str):
        """Export current simulated camera configuration to JSON file."""
        if not self.initialized:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)

            config_data = {
                "camera_type": "mock_genicam",
                "camera_name": self.camera_name,
                "vendor": self.vendor,
                "model": self.model,
                "serial_number": self.serial_number,
                "timestamp": time.time(),
                "exposure_time": self.exposure_time,
                "gain": self.gain,
                "trigger_mode": self.triggermode,
                "roi": self.roi.copy(),
                "pixel_format": self.pixel_format,
                "image_enhancement": self.img_quality_enhancement,
                "retrieve_retry_count": self.retrieve_retry_count,
                "timeout_ms": self.timeout_ms,
                "buffer_count": self.buffer_count,
            }

            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            self.logger.debug(f"Mock configuration exported to '{config_path}'")

        except Exception as e:
            raise CameraConfigurationError(f"Failed to export configuration: {str(e)}")
