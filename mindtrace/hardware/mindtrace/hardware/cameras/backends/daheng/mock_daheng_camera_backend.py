"""Mock Daheng Camera Backend Module

Provides a mock implementation of the Daheng camera backend for testing and development
without requiring actual hardware or the Galaxy SDK.
"""

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


class MockDahengCameraBackend(CameraBackend):
    """Mock Daheng Camera Backend Implementation

    Simulates Daheng camera functionality without requiring actual hardware, with configurable
    behavior and error simulation.

    Features:
        - Complete simulation of Daheng camera API
        - Configurable image generation with realistic patterns
        - Error simulation for testing error handling
        - Configuration import/export simulation
        - Camera control features (exposure, ROI, trigger modes, etc.)

    Usage::

        from mindtrace.hardware.cameras.backends.daheng import MockDahengCameraBackend

        camera = MockDahengCameraBackend("mock_camera_1")
        await camera.set_exposure(20000)
        image = await camera.capture()
        await camera.close()

    Error Simulation:
        Enable error simulation via environment variables:
        - MOCK_DAHENG_FAIL_INIT: Simulate initialization failure
        - MOCK_DAHENG_FAIL_CAPTURE: Simulate capture failure
        - MOCK_DAHENG_TIMEOUT: Simulate timeout errors

    Attributes:
        initialized: Whether camera was successfully initialized
        camera_name: Name/identifier of the mock camera
        triggermode: Current trigger mode ("continuous" or "trigger")
        exposure_time: Current exposure time in microseconds
        gain: Current gain value
        roi: Current region of interest settings
    """

    def __init__(
        self,
        camera_name: str,
        camera_config: Optional[str] = None,
        img_quality_enhancement: Optional[bool] = None,
        retrieve_retry_count: Optional[int] = None,
        **backend_kwargs,
    ):
        """Initialize mock Daheng camera.

        Args:
            camera_name: Camera identifier
            camera_config: Path to configuration file (simulated)
            img_quality_enhancement: Enable image enhancement simulation (uses config default if None)
            retrieve_retry_count: Number of capture retry attempts (uses config default if None)
            **backend_kwargs: Backend-specific parameters:
                - pixel_format: Pixel format (simulated)
                - buffer_count: Buffer count (simulated)
                - timeout_ms: Timeout in milliseconds
                - fast_mode: If True, skip all sleep delays for fast unit tests (default: False)
                - simulate_fail_init: If True, simulate initialization failure
                - simulate_fail_capture: If True, simulate capture failure
                - simulate_timeout: If True, simulate timeout on capture
                - simulate_cancel: If True, simulate asyncio cancellation during capture
                - synthetic_width: Override synthetic image width (int)
                - synthetic_height: Override synthetic image height (int)
                - synthetic_pattern: One of {"auto","gradient","checkerboard","circular","noise"}
                - synthetic_overlay_text: If False, disables text overlays in synthetic images
        """
        super().__init__(camera_name, camera_config, img_quality_enhancement, retrieve_retry_count)

        # Fast mode for unit tests - skips all timing delays
        self.fast_mode = backend_kwargs.get("fast_mode", os.environ.get("MOCK_DAHENG_FAST_MODE") == "1")

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
        self._streaming = False

        # Synthetic image knobs
        self.synthetic_pattern: str = str(backend_kwargs.get("synthetic_pattern", "auto")).lower()
        self.synthetic_overlay_text: bool = bool(backend_kwargs.get("synthetic_overlay_text", True))

        # Optional file-backed fixtures for deterministic mock frames (mirrors
        # MockBasler). Populated by the manager from
        # ``cam_cfg.mock_daheng_image_dir`` / ``mock_daheng_image_map`` so the
        # docker-compose ``MINDTRACE_HW_CAMERA_MOCK_DAHENG_IMAGE_DIR`` env var
        # produces the same per-device deterministic frames here as it does
        # for the Basler mock.
        raw_paths = backend_kwargs.get("mock_image_paths")
        fixture_paths: List[str] = []
        if isinstance(raw_paths, list):
            fixture_paths.extend([p for p in raw_paths if isinstance(p, str) and p])
        self._fixture_image_paths: List[str] = fixture_paths
        self._fixture_images: Optional[List[np.ndarray]] = None

        syn_w = backend_kwargs.get("synthetic_width")
        syn_h = backend_kwargs.get("synthetic_height")
        self.synthetic_width = self.roi["width"]
        self.synthetic_height = self.roi["height"]

        try:
            if syn_w is not None:
                self.roi["width"] = int(syn_w)
                self.synthetic_width = int(syn_w)
            if syn_h is not None:
                self.roi["height"] = int(syn_h)
                self.synthetic_height = int(syn_h)
        except Exception:
            pass

        # Error/cancellation simulation flags
        env_fail_init = os.getenv("MOCK_DAHENG_FAIL_INIT", "false").lower() == "true"
        env_fail_capture = os.getenv("MOCK_DAHENG_FAIL_CAPTURE", "false").lower() == "true"
        env_timeout = os.getenv("MOCK_DAHENG_TIMEOUT", "false").lower() == "true"
        env_cancel = os.getenv("MOCK_DAHENG_CANCEL", "false").lower() == "true"

        self.fail_init = bool(backend_kwargs.get("simulate_fail_init", env_fail_init))
        self.fail_capture = bool(backend_kwargs.get("simulate_fail_capture", env_fail_capture))
        self.simulate_timeout = bool(backend_kwargs.get("simulate_timeout", env_timeout))
        self.simulate_cancel = bool(backend_kwargs.get("simulate_cancel", env_cancel))

        self.initialized = False
        self.camera = None

        self.logger.debug(f"Mock Daheng camera '{self.camera_name}' initialized successfully")

    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """Get available mock Daheng cameras.

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
                    "serial_number": f"DH{i:06d}",
                    "model": "MER2-G-P",
                    "vendor": "Daheng Imaging",
                    "interface": "GigE" if i % 2 == 0 else "USB3",
                    "ip": f"192.168.1.{100 + i}" if i % 2 == 0 else "",
                    "user_defined_name": camera_name,
                    "display_name": f"Daheng MER2-G-P ({camera_name})",
                    "index": str(i),
                }
            return camera_details

        return mock_cameras

    async def _sleep(self, seconds: float) -> None:
        """Conditional sleep - skips if fast_mode is enabled."""
        if not self.fast_mode:
            await asyncio.sleep(seconds)

    async def initialize(self) -> Tuple[bool, Any, Any]:
        """Initialize the mock camera connection.

        Returns:
            Tuple of (success status, mock camera object, None)

        Raises:
            CameraInitializationError: If initialization fails (when simulated)
        """
        if self.fail_init:
            raise CameraInitializationError(f"Simulated initialization failure for mock camera '{self.camera_name}'")

        try:
            available_cameras = self.get_available_cameras()
            if self.camera_name not in available_cameras:
                self.logger.debug(f"Mock camera '{self.camera_name}' not in standard list, but allowing for testing")

            mock_camera_object = {
                "name": self.camera_name,
                "model": "MER2-G-P",
                "serial": "DH000001",
                "connected": True,
            }

            if self.camera_config_path and os.path.exists(self.camera_config_path):
                await self.import_config(self.camera_config_path)

            self.initialized = True
            self._streaming = True
            self.logger.info(f"Mock Daheng camera '{self.camera_name}' initialized successfully")
            return True, mock_camera_object, None

        except (CameraNotFoundError, CameraConnectionError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error initializing mock Daheng camera '{self.camera_name}': {str(e)}")
            raise CameraInitializationError(f"Unexpected error initializing mock camera '{self.camera_name}': {str(e)}")

    async def capture(self) -> np.ndarray:
        """Capture a single image from the mock camera.

        Returns:
            Captured BGR image array

        Raises:
            CameraConnectionError: If camera is not initialized
            CameraCaptureError: If image capture fails
            CameraTimeoutError: If capture times out
        """
        if not self.initialized:
            raise CameraConnectionError(f"Mock camera '{self.camera_name}' is not initialized")

        if self.fail_capture:
            raise CameraCaptureError(f"Simulated capture failure for mock camera '{self.camera_name}'")

        if self.simulate_timeout:
            raise CameraTimeoutError(f"Simulated timeout for mock camera '{self.camera_name}'")

        if self.simulate_cancel:
            raise asyncio.CancelledError()

        try:
            capture_delay = max(0.01, self.exposure_time / 1000000.0)
            await self._sleep(min(capture_delay, 0.1))

            image = await asyncio.to_thread(self._generate_synthetic_image)

            if self.img_quality_enhancement:
                try:
                    image = await asyncio.to_thread(self._enhance_image, image)
                except Exception as enhance_error:
                    self.logger.warning(f"Image enhancement failed, using original image: {enhance_error}")

            self.image_counter += 1
            self.logger.debug(f"Captured frame {self.image_counter} from mock camera '{self.camera_name}'")
            return image

        except asyncio.CancelledError:
            raise
        except (CameraConnectionError, CameraCaptureError, CameraTimeoutError):
            raise
        except Exception as e:
            self.logger.error(f"Mock capture failed for camera '{self.camera_name}': {str(e)}")
            raise CameraCaptureError(f"Failed to capture image from mock camera '{self.camera_name}': {str(e)}")

    def get_image_quality_enhancement(self) -> bool:
        """Get image quality enhancement setting."""
        return self.img_quality_enhancement

    def set_image_quality_enhancement(self, value: bool):
        """Set image quality enhancement setting."""
        self.img_quality_enhancement = value
        self.logger.debug(f"Image quality enhancement set to {value} for mock camera '{self.camera_name}'")

    async def get_exposure_range(self) -> List[Union[int, float]]:
        """Get the supported exposure time range in microseconds."""
        return [20.0, 1000000.0]

    async def get_exposure(self) -> float:
        """Get current exposure time in microseconds."""
        return self.exposure_time

    async def set_exposure(self, exposure: Union[int, float]):
        """Set the camera exposure time in microseconds.

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
            raise CameraConfigurationError(f"Failed to set exposure for mock camera '{self.camera_name}': {str(e)}")

    async def get_triggermode(self) -> str:
        """Get current trigger mode."""
        return self.triggermode

    async def set_triggermode(self, triggermode: str = "continuous"):
        """Set trigger mode.

        Raises:
            CameraConfigurationError: If trigger mode is invalid
        """
        if triggermode not in ["continuous", "trigger"]:
            raise CameraConfigurationError(f"Invalid trigger mode: {triggermode}")
        self.triggermode = triggermode
        self.logger.debug(f"Trigger mode set to '{triggermode}' for mock camera '{self.camera_name}'")

    async def check_connection(self) -> bool:
        """Check if mock camera is connected and operational."""
        if not self.initialized:
            return False
        try:
            img = await self.capture()
            return img is not None and img.shape[0] > 0 and img.shape[1] > 0
        except Exception as e:
            self.logger.warning(f"Connection check failed for mock camera '{self.camera_name}': {str(e)}")
            return False

    async def import_config(self, config_path: str):
        """Import camera configuration from JSON file.

        Raises:
            CameraConfigurationError: If configuration file is not found or invalid
        """
        try:
            if not os.path.exists(config_path):
                raise CameraConfigurationError(f"Configuration file not found: {config_path}")

            await self._sleep(0.01)

            with open(config_path, "r") as f:
                config_data = json.load(f)

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

            self.logger.debug(f"Configuration imported from '{config_path}' for mock camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise CameraConfigurationError(f"Invalid JSON configuration format: {e}")
        except Exception as e:
            raise CameraConfigurationError(f"Failed to import config from '{config_path}': {str(e)}")

    async def export_config(self, config_path: str):
        """Export camera configuration to JSON file."""
        try:
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
                "pixel_format": self.default_pixel_format,
                "image_enhancement": self.img_quality_enhancement,
                "retrieve_retry_count": self.retrieve_retry_count,
                "timeout_ms": self.timeout_ms,
                "buffer_count": self.buffer_count,
            }

            os.makedirs(os.path.dirname(config_path), exist_ok=True)

            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            self.logger.debug(f"Configuration exported to '{config_path}' for mock camera '{self.camera_name}'")
        except Exception as e:
            self.logger.error(f"Failed to export config to '{config_path}': {str(e)}")

    async def set_ROI(self, x: int, y: int, width: int, height: int):
        """Set Region of Interest (ROI).

        Raises:
            CameraConfigurationError: If ROI parameters are invalid
        """
        await self._sleep(0.001)
        if width <= 0 or height <= 0:
            raise CameraConfigurationError(f"Invalid ROI dimensions: {width}x{height}")
        if x < 0 or y < 0:
            raise CameraConfigurationError(f"Invalid ROI offset: ({x}, {y})")
        self.roi = {"x": x, "y": y, "width": width, "height": height}
        self.logger.debug(f"ROI set to ({x}, {y}, {width}, {height}) for mock camera '{self.camera_name}'")

    async def get_ROI(self) -> Dict[str, int]:
        """Get current Region of Interest (ROI)."""
        await self._sleep(0.001)
        return self.roi.copy()

    async def reset_ROI(self):
        """Reset ROI to full sensor size."""
        await self._sleep(0.001)
        self.roi = {"x": 0, "y": 0, "width": self.synthetic_width, "height": self.synthetic_height}
        self.logger.debug(f"ROI reset to full size for mock camera '{self.camera_name}'")

    async def set_gain(self, gain: Union[int, float]):
        """Set camera gain.

        Raises:
            CameraConfigurationError: If gain value is out of range
        """
        await self._sleep(0.001)
        if gain < 0.0 or gain > 24.0:
            raise CameraConfigurationError(f"Gain {gain} out of range [0.0, 24.0]")
        self.gain = float(gain)
        self.logger.debug(f"Gain set to {gain} for mock camera '{self.camera_name}'")

    async def get_gain_range(self) -> List[Union[int, float]]:
        """Get the supported gain range."""
        await self._sleep(0.001)
        return [0.0, 24.0]

    async def get_gain(self) -> float:
        """Get current camera gain."""
        await self._sleep(0.001)
        return self.gain

    async def get_wb(self) -> str:
        """Get current white balance mode."""
        return self.white_balance_mode

    async def set_auto_wb_once(self, value: str):
        """Set white balance mode."""
        self.white_balance_mode = value
        self.logger.debug(f"White balance set to '{value}' for mock camera '{self.camera_name}'")

    async def get_wb_range(self) -> List[str]:
        """Get available white balance modes."""
        await self._sleep(0.001)
        return ["off", "once", "continuous"]

    async def get_pixel_format_range(self) -> List[str]:
        """Get available pixel formats."""
        await self._sleep(0.001)
        return ["BGR8", "RGB8", "Mono8", "BayerRG8", "BayerGB8"]

    async def get_current_pixel_format(self) -> str:
        """Get current pixel format."""
        await self._sleep(0.001)
        return self.default_pixel_format

    async def set_pixel_format(self, pixel_format: str):
        """Set pixel format.

        Raises:
            CameraConfigurationError: If pixel format is not supported
        """
        await self._sleep(0.001)
        available_formats = await self.get_pixel_format_range()
        if pixel_format not in available_formats:
            raise CameraConfigurationError(f"Unsupported pixel format: {pixel_format}")
        self.default_pixel_format = pixel_format
        self.logger.debug(f"Pixel format set to '{pixel_format}' for mock camera '{self.camera_name}'")

    async def set_capture_timeout(self, timeout_ms: int):
        """Set capture timeout in milliseconds."""
        if timeout_ms < 0:
            raise ValueError(f"Timeout must be non-negative, got {timeout_ms}")
        self.timeout_ms = timeout_ms
        self.logger.debug(f"Set capture timeout to {timeout_ms}ms for mock camera '{self.camera_name}'")

    async def get_capture_timeout(self) -> int:
        """Get current capture timeout in milliseconds."""
        return self.timeout_ms

    async def close(self):
        """Close the mock camera and release resources."""
        try:
            self._streaming = False
            self.initialized = False
            self.camera = None
            self.logger.info(f"Mock Daheng camera '{self.camera_name}' closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing mock camera '{self.camera_name}': {str(e)}")

    def _get_fixture_image(self, *, width: int, height: int) -> Optional[np.ndarray]:
        """Return a resized fixture image if configured; otherwise None."""
        if not self._fixture_image_paths:
            return None

        if self._fixture_images is None:
            images: List[np.ndarray] = []
            for path in self._fixture_image_paths:
                try:
                    if not os.path.exists(path):
                        self.logger.warning(
                            f"Mock Daheng fixture image not found for '{self.camera_name}': {path}. Falling back to synthetic."
                        )
                        continue
                    with open(path, "rb") as f:
                        encoded = np.frombuffer(f.read(), dtype=np.uint8)
                    img = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
                    if img is None or img.size == 0:
                        self.logger.warning(
                            f"Mock Daheng fixture image unreadable for '{self.camera_name}': {path}. Falling back to synthetic."
                        )
                        continue
                    images.append(img)
                except Exception as e:
                    self.logger.warning(
                        f"Mock Daheng fixture image failed to load for '{self.camera_name}': {path}. Error: {e}. Falling back to synthetic."
                    )
            self._fixture_images = images

        if not self._fixture_images:
            return None

        idx = self.image_counter % len(self._fixture_images)
        base = self._fixture_images[idx]
        if base.shape[1] != width or base.shape[0] != height:
            return cv2.resize(base, (width, height), interpolation=cv2.INTER_AREA)
        return base.copy()

    def _generate_synthetic_image(self) -> np.ndarray:
        """Generate synthetic test image.

        Returns:
            BGR image array
        """
        width = self.roi["width"]
        height = self.roi["height"]
        try:
            fixture = self._get_fixture_image(width=width, height=height)
            if fixture is not None:
                return fixture

            x_coords = np.arange(width)
            y_coords = np.arange(height)
            X, Y = np.meshgrid(x_coords, y_coords)

            pattern_map = {"gradient": 0, "checkerboard": 1, "circular": 2, "noise": 3}
            if self.synthetic_pattern in pattern_map:
                pattern_type = pattern_map[self.synthetic_pattern]
            else:
                pattern_type = self.image_counter % 4

            if pattern_type == 0:
                r_channel = (128 + 127 * np.sin(2 * np.pi * X / width)).astype(np.uint8)
                g_channel = (128 + 127 * np.cos(2 * np.pi * Y / height)).astype(np.uint8)
                b_channel = (64 + 64 * np.sin(2 * np.pi * (X + Y) / (width + height))).astype(np.uint8)
                image = np.stack([b_channel, g_channel, r_channel], axis=-1)
            elif pattern_type == 1:
                checker_x = (X // 50) % 2
                checker_y = (Y // 50) % 2
                checkerboard = (checker_x + checker_y) % 2
                image = np.where(checkerboard[..., np.newaxis], 200, 50).astype(np.uint8)
                image = np.repeat(image, 3, axis=-1)
            elif pattern_type == 2:
                center_x, center_y = width // 2, height // 2
                max_radius = min(width, height) // 2
                dist = np.sqrt((X - center_x) ** 2 + (Y - center_y) ** 2)
                intensity = (128 + 127 * np.sin(2 * np.pi * dist / max_radius)).astype(np.uint8)
                image = np.stack([intensity, intensity // 2, (255 - intensity) // 2], axis=-1)
            else:
                image = np.random.randint(50, 200, (height, width, 3), dtype=np.uint8)

            exposure_factor = min(1.0, self.exposure_time / 20000.0)
            image = (image * exposure_factor).astype(np.uint8)

            if self.gain > 1.0:
                image = np.clip(image * self.gain, 0, 255).astype(np.uint8)

            if self.synthetic_overlay_text:
                timestamp = time.strftime("%H:%M:%S")
                font_scale = min(width, height) / 1000.0
                thickness = max(1, int(font_scale * 2))
                cv2.putText(
                    image, f"Mock Daheng {timestamp}", (50, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), thickness,
                )
                cv2.putText(
                    image, f"Frame: {self.image_counter}", (50, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), thickness,
                )

            return image

        except Exception as e:
            self.logger.error(f"Failed to generate synthetic image: {str(e)}")
            return np.full((height, width, 3), 128, dtype=np.uint8)

    def _enhance_image(self, image: np.ndarray) -> np.ndarray:
        """Apply CLAHE enhancement."""
        try:
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l_channel, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(l_channel)
            enhanced_lab = cv2.merge((cl, a, b))
            return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
        except Exception as e:
            self.logger.error(f"Image enhancement failed for mock camera '{self.camera_name}': {str(e)}")
            return image
