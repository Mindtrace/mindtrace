"""Daheng Camera Backend Module

Provides camera control for Daheng Imaging industrial cameras using the Galaxy SDK (gxipy).
Supports GigE Vision and USB3 Vision cameras with full feature control.
"""

import asyncio
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

try:
    import gxipy as gx  # type: ignore

    GXIPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    GXIPY_AVAILABLE = False
    gx = None

from mindtrace.hardware.cameras.backends.camera_backend import CameraBackend
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
    CameraTimeoutError,
    HardwareOperationError,
    SDKNotAvailableError,
)


class DahengCameraBackend(CameraBackend):
    """Daheng camera backend using the Galaxy SDK (gxipy).

    This backend provides comprehensive support for Daheng Imaging cameras including
    hardware triggers, exposure control, gain, ROI settings, and image enhancement.

    Thread Model:
        The gxipy SDK uses ctypes to call native C libraries and requires thread
        affinity - all SDK operations for a camera must execute on the same OS thread
        that opened it. This backend uses a dedicated single-thread executor per camera
        instance to satisfy this requirement.

    Features:
        - Full gxipy SDK integration for GigE Vision and USB3 Vision cameras
        - Hardware trigger and continuous capture modes
        - Region of Interest (ROI) control
        - Automatic and manual exposure/gain control
        - White balance control
        - CLAHE image quality enhancement
        - Pixel format control

    Requirements:
        - Daheng Galaxy SDK installed on system (provides native libgxiapi.so/GxIAPI.dll)
        - gxipy package (pip install iai-gxipy)
        - OpenCV for image processing

    Example::

        from mindtrace.hardware.cameras.backends.daheng import DahengCameraBackend

        async with DahengCameraBackend("serial_number") as camera:
            await camera.set_exposure(20000)
            await camera.set_triggermode("continuous")
            image = await camera.capture()

    Attributes:
        camera: Underlying gxipy Device object
        triggermode: Current trigger mode ("continuous" or "trigger")
        timeout_ms: Capture timeout in milliseconds
        buffer_count: Number of frame buffers for streaming
    """

    REQUIRES_THREAD_AFFINITY = True

    def __init__(
        self,
        camera_name: str,
        camera_config: Optional[str] = None,
        img_quality_enhancement: Optional[bool] = None,
        retrieve_retry_count: Optional[int] = None,
        **backend_kwargs,
    ):
        """Initialize Daheng camera with configurable parameters.

        Args:
            camera_name: Camera identifier (serial number, IP address, or user-defined name)
            camera_config: Path to JSON configuration file (optional)
            img_quality_enhancement: Enable CLAHE image enhancement (uses config default if None)
            retrieve_retry_count: Number of capture retry attempts (uses config default if None)
            **backend_kwargs: Backend-specific parameters:
                - pixel_format: Default pixel format (uses config default if None)
                - buffer_count: Number of frame buffers (uses config default if None)
                - timeout_ms: Capture timeout in milliseconds (uses config default if None)

        Raises:
            SDKNotAvailableError: If gxipy SDK is not available
            CameraConfigurationError: If configuration is invalid
        """
        if not GXIPY_AVAILABLE:
            raise SDKNotAvailableError(
                "gxipy",
                "Install gxipy to use Daheng cameras:\n"
                "1. Download and install Daheng Galaxy SDK from https://en.daheng-imaging.com/list-59-1.html\n"
                "2. pip install iai-gxipy\n"
                "3. Ensure Galaxy SDK native libraries are properly installed",
            )
        else:
            assert gx is not None, "gxipy SDK is available but gx is not initialized"

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

        # Internal state
        self.triggermode = self.camera_config.cameras.trigger_mode
        self._streaming = False

        # Derived operation timeout for non-capture SDK calls
        self._op_timeout_s = max(1.0, float(self.timeout_ms) / 1000.0)

        self.logger.info(f"Daheng camera '{self.camera_name}' initialized successfully")

    # NOTE: ``_run_blocking`` is provided by the base ``CameraBackend`` and routes
    # automatically to a per-instance single-thread executor when
    # ``REQUIRES_THREAD_AFFINITY = True`` (set above). No override needed here.

    @staticmethod
    def _is_ip_address(name: str) -> bool:
        """Check if camera_name is a valid IP address.

        Args:
            name: String to check

        Returns:
            True if name is a valid IP address format, False otherwise
        """
        ip_pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
        if not re.match(ip_pattern, name):
            return False
        octets = name.split(".")
        return all(int(octet) <= 255 for octet in octets)

    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """Get available Daheng cameras.

        Args:
            include_details: If True, return detailed information

        Returns:
            List of camera serial numbers or dict with details

        Raises:
            SDKNotAvailableError: If gxipy SDK is not available
            HardwareOperationError: If camera discovery fails
        """
        if not GXIPY_AVAILABLE:
            raise SDKNotAvailableError("gxipy", "Galaxy SDK (gxipy) is not available for camera discovery")
        else:
            assert gx is not None, "gxipy SDK is available but gx is not initialized"

        try:
            device_manager = gx.DeviceManager()
            dev_num, dev_info_list = device_manager.update_all_device_list()

            if dev_num == 0:
                return {} if include_details else []

            available_cameras = []
            camera_details = {}

            for i, dev_info in enumerate(dev_info_list):
                sn = dev_info.get("sn", f"unknown_{i}")
                model = dev_info.get("model_name", "Unknown")
                ip = dev_info.get("ip", "")
                user_id = dev_info.get("user_id", "")
                display_name = dev_info.get("display_name", "")
                vendor = dev_info.get("vendor_name", "Daheng Imaging")

                # Use serial number as primary identifier
                camera_identifier = sn
                available_cameras.append(camera_identifier)

                if include_details:
                    camera_details[camera_identifier] = {
                        "serial_number": sn,
                        "model": model,
                        "vendor": vendor,
                        "ip": ip,
                        "user_defined_name": user_id,
                        "display_name": display_name,
                        "interface": "GigE" if ip else "USB3",
                        "index": str(i + 1),
                    }

            return camera_details if include_details else available_cameras

        except Exception as e:
            raise HardwareOperationError(f"Failed to discover Daheng cameras: {str(e)}")

    @classmethod
    async def discover_async(cls, include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """Async wrapper for get_available_cameras() - runs discovery in threadpool.

        Args:
            include_details: If True, return a dict of details per camera.

        Returns:
            Union[List[str], Dict[str, Dict[str, str]]]: List of camera names or dict of details.
        """
        return await asyncio.to_thread(cls.get_available_cameras, include_details)

    async def initialize(self) -> Tuple[bool, Any, Any]:
        """Initialize the camera connection.

        Searches for the camera by serial number, IP address, or index and establishes
        a connection if found.

        Returns:
            Tuple of (success status, camera device object, None)

        Raises:
            CameraNotFoundError: If no cameras found or specified camera not found
            CameraInitializationError: If camera initialization fails
            CameraConnectionError: If camera connection fails
        """
        # Return early if already initialized
        if self.initialized and self.camera is not None:
            self.logger.debug(f"Camera '{self.camera_name}' is already initialized, skipping re-initialization")
            return (True, self.camera, None)

        if not GXIPY_AVAILABLE:
            raise SDKNotAvailableError("gxipy", "Galaxy SDK (gxipy) is not available for camera initialization")
        else:
            assert gx is not None, "gxipy SDK is available but gx is not initialized"

        try:

            def _init_camera():
                device_manager = gx.DeviceManager()
                dev_num, dev_info_list = device_manager.update_all_device_list()

                if dev_num == 0:
                    raise CameraNotFoundError("No Daheng cameras found")

                cam = None
                camera_name = self.camera_name

                # Try opening by different identifiers
                if self._is_ip_address(camera_name):
                    cam = device_manager.open_device_by_ip(camera_name)
                else:
                    # Try serial number first
                    for dev_info in dev_info_list:
                        if dev_info.get("sn") == camera_name:
                            cam = device_manager.open_device_by_sn(camera_name)
                            break

                    # Try user-defined name
                    if cam is None:
                        for dev_info in dev_info_list:
                            if dev_info.get("user_id") == camera_name:
                                cam = device_manager.open_device_by_user_id(camera_name)
                                break

                    # Try by index (1-based)
                    if cam is None:
                        try:
                            idx = int(camera_name)
                            if 1 <= idx <= dev_num:
                                cam = device_manager.open_device_by_index(idx)
                        except (ValueError, TypeError):
                            pass

                if cam is None:
                    available = [d.get("sn", "unknown") for d in dev_info_list]
                    raise CameraNotFoundError(
                        f"Camera '{camera_name}' not found. Available cameras: {available}"
                    )

                return cam, device_manager

            cam, device_manager = await self._run_blocking(_init_camera, timeout=self._op_timeout_s * 2)

            self.camera = cam
            self.device_manager = device_manager

            # Configure the camera
            await self._configure_camera()

            # Load config if provided
            if self.camera_config_path and os.path.exists(self.camera_config_path):
                await self.import_config(self.camera_config_path)

            self.initialized = True
            self.logger.info(f"Daheng camera '{self.camera_name}' connected and initialized")
            return True, cam, None

        except (CameraNotFoundError, CameraConnectionError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error initializing Daheng camera '{self.camera_name}': {str(e)}")
            raise CameraInitializationError(f"Unexpected error initializing camera '{self.camera_name}': {str(e)}")

    async def _configure_camera(self):
        """Configure initial camera settings.

        Raises:
            CameraConfigurationError: If camera configuration fails
        """
        try:

            def _configure():
                cam = self.camera

                # Set trigger mode to software trigger by default
                if cam.TriggerMode.is_implemented():
                    cam.TriggerMode.set(gx.GxSwitchEntry.ON)
                if cam.TriggerSource.is_implemented():
                    cam.TriggerSource.set(gx.GxTriggerSourceEntry.SOFTWARE)

                # Set acquisition mode to continuous
                if cam.AcquisitionMode.is_implemented():
                    cam.AcquisitionMode.set(gx.GxAcquisitionModeEntry.CONTINUOUS)

                # Start streaming
                cam.stream_on()

            await self._run_blocking(_configure, timeout=self._op_timeout_s)
            self._streaming = True
            self.triggermode = "trigger"

            self.logger.debug(
                f"Daheng camera '{self.camera_name}' configured with buffer_count={self.buffer_count}"
            )

        except Exception as e:
            self.logger.error(f"Failed to configure Daheng camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to configure camera '{self.camera_name}': {str(e)}")

    async def capture(self) -> np.ndarray:
        """Capture a single image from the camera.

        In continuous mode, returns the latest available frame.
        In trigger mode, executes a software trigger and waits for the image.

        Returns:
            Image array in BGR format

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            CameraCaptureError: If image capture fails
            CameraTimeoutError: If capture times out
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
        assert gx is not None, "camera is initialized but gx is not available"

        def _capture_sync() -> np.ndarray:
            """Synchronous capture - runs entirely on dedicated executor thread."""
            cam = self.camera

            # Ensure streaming is active
            if not self._streaming:
                cam.stream_on()
                self._streaming = True

            # Retry loop for capture
            for i in range(self.retrieve_retry_count):
                try:
                    # Trigger if in trigger mode
                    if self.triggermode == "trigger":
                        if cam.TriggerSoftware.is_implemented():
                            cam.TriggerSoftware.send_command()

                    # Retrieve image with timeout
                    raw_image = cam.data_stream[0].get_image(timeout=self.timeout_ms)

                    if raw_image is None:
                        if i == self.retrieve_retry_count - 1:
                            raise CameraCaptureError(
                                f"Capture returned None after {self.retrieve_retry_count} attempts"
                            )
                        continue

                    # Convert to numpy array
                    numpy_image = raw_image.get_numpy_array()

                    if numpy_image is None:
                        if i == self.retrieve_retry_count - 1:
                            raise CameraCaptureError("Failed to convert raw image to numpy array")
                        continue

                    # Handle pixel format conversion
                    # gxipy returns mono images as (H, W), color as (H, W, 3)
                    if len(numpy_image.shape) == 2:
                        # Check if this is a Bayer pattern or true mono
                        pixel_format = cam.PixelFormat.get() if cam.PixelFormat.is_implemented() else None
                        pf_str = str(pixel_format) if pixel_format else ""
                        if "Bayer" in pf_str:
                            # Bayer pattern — demosaic on host side (same approach as Basler)
                            # Map Bayer pattern to OpenCV conversion code
                            if "RG" in pf_str:
                                numpy_image = cv2.cvtColor(numpy_image, cv2.COLOR_BAYER_RG2BGR)
                            elif "GR" in pf_str:
                                numpy_image = cv2.cvtColor(numpy_image, cv2.COLOR_BAYER_GR2BGR)
                            elif "GB" in pf_str:
                                numpy_image = cv2.cvtColor(numpy_image, cv2.COLOR_BAYER_GB2BGR)
                            elif "BG" in pf_str:
                                numpy_image = cv2.cvtColor(numpy_image, cv2.COLOR_BAYER_BG2BGR)
                            else:
                                numpy_image = cv2.cvtColor(numpy_image, cv2.COLOR_BAYER_RG2BGR)
                        else:
                            # True mono — convert to 3-channel for consistency
                            numpy_image = cv2.cvtColor(numpy_image, cv2.COLOR_GRAY2BGR)
                    elif numpy_image.shape[2] == 3:
                        # Check if RGB and convert to BGR
                        pixel_format = cam.PixelFormat.get() if cam.PixelFormat.is_implemented() else None
                        if pixel_format is not None and "RGB" in str(pixel_format):
                            numpy_image = cv2.cvtColor(numpy_image, cv2.COLOR_RGB2BGR)

                    return numpy_image

                except (CameraCaptureError, CameraTimeoutError):
                    if i == self.retrieve_retry_count - 1:
                        raise
                except Exception:
                    if i == self.retrieve_retry_count - 1:
                        raise
                    time.sleep(0.1)

            raise CameraCaptureError(f"Failed to capture after {self.retrieve_retry_count} attempts")

        try:
            # Run entire capture atomically on dedicated thread
            image = await self._run_blocking(
                _capture_sync,
                timeout=self._op_timeout_s + (self.timeout_ms / 1000.0) * self.retrieve_retry_count,
            )

            # Apply image enhancement if enabled (can run on any thread)
            if self.img_quality_enhancement and image is not None:
                image = await self._enhance_image(image)

            return image

        except asyncio.CancelledError:
            raise
        except (CameraConnectionError, CameraCaptureError, CameraTimeoutError):
            raise
        except Exception as e:
            self.logger.error(f"Capture failed for Daheng camera '{self.camera_name}': {str(e)}")
            raise CameraCaptureError(f"Failed to capture image from camera '{self.camera_name}': {str(e)}")

    async def _enhance_image(self, image: np.ndarray) -> np.ndarray:
        """Apply CLAHE image quality enhancement.

        Args:
            image: Input BGR image

        Returns:
            Enhanced BGR image
        """
        try:

            def _apply_clahe(img):
                lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
                l_channel, a, b = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                cl = clahe.apply(l_channel)
                enhanced_lab = cv2.merge((cl, a, b))
                return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

            return await asyncio.to_thread(_apply_clahe, image)
        except Exception as enhance_error:
            self.logger.warning(f"Image enhancement failed, using original image: {enhance_error}")
            return image

    def get_image_quality_enhancement(self) -> bool:
        """Get image quality enhancement setting."""
        return self.img_quality_enhancement

    def set_image_quality_enhancement(self, value: bool):
        """Set image quality enhancement setting."""
        self.img_quality_enhancement = value
        self.logger.debug(f"Image quality enhancement set to {value} for camera '{self.camera_name}'")

    async def get_exposure_range(self) -> List[Union[int, float]]:
        """Get the supported exposure time range in microseconds.

        Returns:
            List with [min_exposure, max_exposure] in microseconds
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _get_range():
                cam = self.camera
                if cam.ExposureTime.is_implemented():
                    return [cam.ExposureTime.get_min(), cam.ExposureTime.get_max()]
                return [1.0, 1000000.0]

            return await self._run_blocking(_get_range)
        except Exception as e:
            self.logger.warning(f"Exposure range not available for camera '{self.camera_name}': {str(e)}")
            return [1.0, 1000000.0]

    async def get_exposure(self) -> float:
        """Get current exposure time in microseconds.

        Returns:
            Current exposure time
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _get():
                cam = self.camera
                if cam.ExposureTime.is_implemented():
                    return cam.ExposureTime.get()
                return 0.0

            return await self._run_blocking(_get)
        except Exception as e:
            raise HardwareOperationError(f"Failed to get exposure for camera '{self.camera_name}': {e}") from e

    async def set_exposure(self, exposure: Union[int, float]):
        """Set the camera exposure time in microseconds.

        Args:
            exposure: Exposure time in microseconds

        Raises:
            CameraConfigurationError: If exposure value is out of range
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _set():
                cam = self.camera
                if not cam.ExposureTime.is_implemented():
                    raise CameraConfigurationError("ExposureTime feature is not implemented on this camera")

                # Disable auto exposure first
                if cam.ExposureAuto.is_implemented():
                    cam.ExposureAuto.set(gx.GxAutoEntry.OFF)

                cam.ExposureTime.set(float(exposure))

            await self._run_blocking(_set)
            self.logger.debug(f"Exposure set to {exposure} for camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            raise CameraConfigurationError(f"Failed to set exposure for camera '{self.camera_name}': {e}") from e

    async def get_gain(self) -> float:
        """Get current camera gain value.

        Returns:
            Current gain value in dB
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _get():
                cam = self.camera
                if cam.Gain.is_implemented():
                    return cam.Gain.get()
                return 0.0

            return await self._run_blocking(_get)
        except Exception as e:
            raise HardwareOperationError(f"Failed to get gain for camera '{self.camera_name}': {e}") from e

    async def get_gain_range(self) -> List[Union[int, float]]:
        """Get the supported gain range.

        Returns:
            List with [min_gain, max_gain] in dB
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _get_range():
                cam = self.camera
                if cam.Gain.is_implemented():
                    return [cam.Gain.get_min(), cam.Gain.get_max()]
                return [0.0, 24.0]

            return await self._run_blocking(_get_range)
        except Exception as e:
            self.logger.warning(f"Gain range not available for camera '{self.camera_name}': {str(e)}")
            return [0.0, 24.0]

    async def set_gain(self, gain: Union[int, float]):
        """Set camera gain.

        Args:
            gain: Gain value in dB

        Raises:
            CameraConfigurationError: If gain value is out of range
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _set():
                cam = self.camera
                if not cam.Gain.is_implemented():
                    raise CameraConfigurationError("Gain feature is not implemented on this camera")

                # Disable auto gain first
                if cam.GainAuto.is_implemented():
                    cam.GainAuto.set(gx.GxAutoEntry.OFF)

                cam.Gain.set(float(gain))

            await self._run_blocking(_set)
            self.logger.debug(f"Gain set to {gain} for camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            raise CameraConfigurationError(f"Failed to set gain for camera '{self.camera_name}': {e}") from e

    async def get_triggermode(self) -> str:
        """Get current trigger mode.

        Returns:
            Current trigger mode ("continuous" or "trigger")
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

        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _set():
                cam = self.camera
                if triggermode == "continuous":
                    if cam.TriggerMode.is_implemented():
                        cam.TriggerMode.set(gx.GxSwitchEntry.OFF)
                else:
                    if cam.TriggerMode.is_implemented():
                        cam.TriggerMode.set(gx.GxSwitchEntry.ON)
                    if cam.TriggerSource.is_implemented():
                        cam.TriggerSource.set(gx.GxTriggerSourceEntry.SOFTWARE)

            await self._run_blocking(_set)
            self.triggermode = triggermode
            self.logger.debug(f"Trigger mode set to '{triggermode}' for camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            raise CameraConfigurationError(
                f"Failed to set trigger mode for camera '{self.camera_name}': {e}"
            ) from e

    async def check_connection(self) -> bool:
        """Check if camera is connected and operational.

        Returns:
            True if connected and operational, False otherwise
        """
        if not self.initialized or self.camera is None:
            return False

        try:
            # Try a simple read operation to verify connection
            await self.get_exposure()
            return True
        except Exception as e:
            self.logger.warning(f"Connection check failed for camera '{self.camera_name}': {str(e)}")
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
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        if width <= 0 or height <= 0:
            raise CameraConfigurationError(f"Invalid ROI dimensions: {width}x{height}")
        if x < 0 or y < 0:
            raise CameraConfigurationError(f"Invalid ROI offset: ({x}, {y})")

        try:

            def _set_roi():
                cam = self.camera
                # Must stop streaming to change ROI on some models
                was_streaming = self._streaming
                if was_streaming:
                    cam.stream_off()

                if cam.OffsetX.is_implemented():
                    cam.OffsetX.set(x)
                if cam.OffsetY.is_implemented():
                    cam.OffsetY.set(y)
                if cam.Width.is_implemented():
                    cam.Width.set(width)
                if cam.Height.is_implemented():
                    cam.Height.set(height)

                if was_streaming:
                    cam.stream_on()

            await self._run_blocking(_set_roi)
            self.logger.debug(f"ROI set to ({x}, {y}, {width}, {height}) for camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            raise CameraConfigurationError(f"Failed to set ROI for camera '{self.camera_name}': {e}") from e

    async def get_ROI(self) -> Dict[str, int]:
        """Get current Region of Interest (ROI).

        Returns:
            Dictionary with ROI parameters (x, y, width, height)
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _get_roi():
                cam = self.camera
                roi = {
                    "x": cam.OffsetX.get() if cam.OffsetX.is_implemented() else 0,
                    "y": cam.OffsetY.get() if cam.OffsetY.is_implemented() else 0,
                    "width": cam.Width.get() if cam.Width.is_implemented() else 0,
                    "height": cam.Height.get() if cam.Height.is_implemented() else 0,
                }
                return roi

            return await self._run_blocking(_get_roi)
        except Exception as e:
            raise HardwareOperationError(f"Failed to get ROI for camera '{self.camera_name}': {e}") from e

    async def reset_ROI(self):
        """Reset ROI to full sensor size."""
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _reset_roi():
                cam = self.camera
                was_streaming = self._streaming
                if was_streaming:
                    cam.stream_off()

                if cam.OffsetX.is_implemented():
                    cam.OffsetX.set(0)
                if cam.OffsetY.is_implemented():
                    cam.OffsetY.set(0)
                if cam.Width.is_implemented() and cam.WidthMax.is_implemented():
                    cam.Width.set(cam.WidthMax.get())
                if cam.Height.is_implemented() and cam.HeightMax.is_implemented():
                    cam.Height.set(cam.HeightMax.get())

                if was_streaming:
                    cam.stream_on()

            await self._run_blocking(_reset_roi)
            self.logger.debug(f"ROI reset to full size for camera '{self.camera_name}'")
        except Exception as e:
            raise CameraConfigurationError(f"Failed to reset ROI for camera '{self.camera_name}': {e}") from e

    async def get_wb(self) -> str:
        """Get current white balance mode.

        Returns:
            Current white balance mode
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _get():
                cam = self.camera
                if cam.BalanceWhiteAuto.is_implemented():
                    val = cam.BalanceWhiteAuto.get()
                    if val == gx.GxAutoEntry.OFF:
                        return "off"
                    elif val == gx.GxAutoEntry.CONTINUOUS:
                        return "continuous"
                    else:
                        return "once"
                return "off"

            return await self._run_blocking(_get)
        except Exception as e:
            self.logger.warning(f"White balance not available for camera '{self.camera_name}': {str(e)}")
            return "off"

    async def set_auto_wb_once(self, value: str):
        """Set white balance mode.

        Args:
            value: White balance mode ("off", "once", "continuous")
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _set():
                cam = self.camera
                if not cam.BalanceWhiteAuto.is_implemented():
                    return
                if value == "off":
                    cam.BalanceWhiteAuto.set(gx.GxAutoEntry.OFF)
                elif value == "continuous":
                    cam.BalanceWhiteAuto.set(gx.GxAutoEntry.CONTINUOUS)
                else:
                    cam.BalanceWhiteAuto.set(gx.GxAutoEntry.ONCE)

            await self._run_blocking(_set)
            self.logger.debug(f"White balance set to '{value}' for camera '{self.camera_name}'")
        except Exception as e:
            self.logger.warning(f"Failed to set white balance for camera '{self.camera_name}': {str(e)}")

    async def get_wb_range(self) -> List[str]:
        """Get available white balance modes.

        Returns:
            List of available white balance modes
        """
        return ["off", "once", "continuous"]

    # ── Color Transformation ──

    async def get_color_transformation(self) -> bool:
        """Get current color transformation enable state."""
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
        try:
            def _get():
                cam = self.camera
                if cam.ColorTransformationEnable.is_implemented():
                    return cam.ColorTransformationEnable.get()
                return False
            return await self._run_blocking(_get)
        except Exception as e:
            self.logger.warning(f"Color transformation not available for camera '{self.camera_name}': {e}")
            return False

    async def set_color_transformation(self, enabled: bool):
        """Enable or disable color transformation.

        Args:
            enabled: True to enable, False to disable
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
        try:
            def _set():
                cam = self.camera
                if cam.ColorTransformationEnable.is_implemented():
                    cam.ColorTransformationEnable.set(enabled)
                    pass
            await self._run_blocking(_set)
            self.logger.info(f"Color transformation set to {enabled} for camera '{self.camera_name}'")
        except Exception as e:
            self.logger.warning(f"Failed to set color transformation for camera '{self.camera_name}': {e}")

    # ── Light Source Preset ──

    async def get_light_source_preset(self) -> str:
        """Get current light source preset."""
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
        try:
            def _get():
                cam = self.camera
                if cam.LightSourcePreset.is_implemented():
                    _val, desc = cam.LightSourcePreset.get()
                    return desc
                return "OFF"
            return await self._run_blocking(_get)
        except Exception as e:
            self.logger.warning(f"Light source preset not available for camera '{self.camera_name}': {e}")
            return "OFF"

    async def set_light_source_preset(self, preset: str):
        """Set light source preset.

        Args:
            preset: One of 'OFF', 'CUSTOM', 'DAYLIGHT_6500K', 'DAYLIGHT_5000K',
                    'COOL_WHITE_FLUORESCENCE', 'INCA'
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
        preset_map = {
            "OFF": 0, "CUSTOM": 1, "DAYLIGHT_6500K": 2, "DAYLIGHT_5000K": 3,
            "COOL_WHITE_FLUORESCENCE": 4, "INCA": 5,
        }
        value = preset_map.get(preset.upper(), 0)
        try:
            def _set():
                cam = self.camera
                if cam.LightSourcePreset.is_implemented():
                    cam.LightSourcePreset.set(value)
            await self._run_blocking(_set)
            self.logger.debug(f"Light source preset set to '{preset}' for camera '{self.camera_name}'")
        except Exception as e:
            self.logger.warning(f"Failed to set light source preset for camera '{self.camera_name}': {e}")

    # ── Balance Ratio (R/G/B) ──

    async def get_balance_ratios(self) -> Dict[str, float]:
        """Get current R/G/B balance ratios.

        Returns:
            Dict with 'red', 'green', 'blue' ratio values
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
        try:
            def _get():
                cam = self.camera
                ratios = {}
                for channel, selector in [("red", 0), ("green", 1), ("blue", 2)]:
                    cam.BalanceRatioSelector.set(selector)
                    ratios[channel] = cam.BalanceRatio.get()
                return ratios
            return await self._run_blocking(_get)
        except Exception as e:
            self.logger.warning(f"Balance ratios not available for camera '{self.camera_name}': {e}")
            return {"red": 1.0, "green": 1.0, "blue": 1.0}

    async def set_balance_ratios(self, red: float = None, green: float = None, blue: float = None):
        """Set R/G/B balance ratios.

        Args:
            red: Red channel ratio
            green: Green channel ratio
            blue: Blue channel ratio
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
        try:
            def _set():
                cam = self.camera
                if red is not None:
                    cam.BalanceRatioSelector.set(0)
                    cam.BalanceRatio.set(red)
                if green is not None:
                    cam.BalanceRatioSelector.set(1)
                    cam.BalanceRatio.set(green)
                if blue is not None:
                    cam.BalanceRatioSelector.set(2)
                    cam.BalanceRatio.set(blue)
            await self._run_blocking(_set)
            self.logger.debug(f"Balance ratios set (R={red}, G={green}, B={blue}) for camera '{self.camera_name}'")
        except Exception as e:
            self.logger.warning(f"Failed to set balance ratios for camera '{self.camera_name}': {e}")

    # ── User Set (Save/Load/Default) ──

    async def user_set_save(self, user_set: str = "UserSet0"):
        """Save current parameters to a user set on the camera.

        Args:
            user_set: 'Default', 'UserSet0', or 'UserSet1'
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
        set_map = {"Default": 0, "UserSet0": 1, "UserSet1": 2}
        value = set_map.get(user_set, 1)
        try:
            def _save():
                cam = self.camera
                cam.UserSetSelector.set(value)
                cam.UserSetSave.send_command()
            await self._run_blocking(_save)
            self.logger.info(f"Saved parameters to '{user_set}' for camera '{self.camera_name}'")
        except Exception as e:
            raise CameraConfigurationError(f"Failed to save user set '{user_set}': {e}") from e

    async def user_set_load(self, user_set: str = "UserSet0"):
        """Load parameters from a user set on the camera.

        Args:
            user_set: 'Default', 'UserSet0', or 'UserSet1'
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
        set_map = {"Default": 0, "UserSet0": 1, "UserSet1": 2}
        value = set_map.get(user_set, 1)
        try:
            def _load():
                cam = self.camera
                cam.UserSetSelector.set(value)
                cam.UserSetLoad.send_command()
            await self._run_blocking(_load)
            self.logger.info(f"Loaded parameters from '{user_set}' for camera '{self.camera_name}'")
        except Exception as e:
            raise CameraConfigurationError(f"Failed to load user set '{user_set}': {e}") from e

    async def user_set_default(self, user_set: str = "UserSet0"):
        """Set which user set loads on camera startup.

        Args:
            user_set: 'Default', 'UserSet0', or 'UserSet1'
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
        set_map = {"Default": 0, "UserSet0": 1, "UserSet1": 2}
        value = set_map.get(user_set, 1)
        try:
            def _set_default():
                cam = self.camera
                cam.UserSetDefault.set(value)
            await self._run_blocking(_set_default)
            self.logger.info(f"Startup user set set to '{user_set}' for camera '{self.camera_name}'")
        except Exception as e:
            raise CameraConfigurationError(f"Failed to set default user set '{user_set}': {e}") from e

    async def get_user_set_default(self) -> str:
        """Get which user set loads on camera startup."""
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")
        try:
            def _get():
                cam = self.camera
                _val, desc = cam.UserSetDefault.get()
                return desc
            return await self._run_blocking(_get)
        except Exception as e:
            self.logger.warning(f"User set default not available for camera '{self.camera_name}': {e}")
            return "DEFAULT"

    async def get_pixel_format_range(self) -> List[str]:
        """Get available pixel formats.

        Returns:
            List of available pixel format names
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _get():
                cam = self.camera
                if cam.PixelFormat.is_implemented():
                    entries = cam.PixelFormat.get_range()
                    return [str(e) for e in entries] if entries else []
                return []

            return await self._run_blocking(_get)
        except Exception:
            return ["Mono8", "BGR8", "RGB8"]

    async def get_current_pixel_format(self) -> str:
        """Get current pixel format.

        Returns:
            Current pixel format name
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _get():
                cam = self.camera
                if cam.PixelFormat.is_implemented():
                    return str(cam.PixelFormat.get())
                return self.default_pixel_format

            return await self._run_blocking(_get)
        except Exception:
            return self.default_pixel_format

    async def set_pixel_format(self, pixel_format: str):
        """Set pixel format.

        Args:
            pixel_format: Pixel format to set

        Raises:
            CameraConfigurationError: If pixel format is not supported
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:

            def _set():
                cam = self.camera
                if not cam.PixelFormat.is_implemented():
                    raise CameraConfigurationError("PixelFormat feature is not implemented on this camera")

                was_streaming = self._streaming
                if was_streaming:
                    cam.stream_off()

                # Map format names to gxipy enum values
                _entry = gx.GxPixelFormatEntry
                format_map = {
                    # Mono formats
                    "Mono8": _entry.MONO8,
                    "Mono10": _entry.MONO10,
                    "Mono12": _entry.MONO12,
                    "Mono14": _entry.MONO14,
                    "Mono16": _entry.MONO16,
                    # Bayer formats
                    "BayerRG8": _entry.BAYER_RG8,
                    "BayerRG10": _entry.BAYER_RG10,
                    "BayerRG12": _entry.BAYER_RG12,
                    "BayerRG16": _entry.BAYER_RG16,
                    "BayerGB8": _entry.BAYER_GB8,
                    "BayerGB12": _entry.BAYER_GB12,
                    "BayerGR8": _entry.BAYER_GR8,
                    "BayerGR12": _entry.BAYER_GR12,
                    "BayerBG8": _entry.BAYER_BG8,
                    "BayerBG12": _entry.BAYER_BG12,
                    # Color formats
                    "RGB8": _entry.RGB8,
                    "BGR8": _entry.BGR8,
                    "RGBA8": _entry.RGBA8,
                    "BGRA8": _entry.BGRA8,
                    # YUV formats
                    "YUV422_8": _entry.YUV422_8,
                    "YUV422_8_UYVY": _entry.YCBCR422_8,
                    "YUV444_8": _entry.YUV444_8,
                    "YUV411_8": _entry.YUV411_8,
                }

                gx_format = format_map.get(pixel_format)
                if gx_format is not None:
                    cam.PixelFormat.set(gx_format)
                else:
                    # Try setting directly as integer or string
                    cam.PixelFormat.set(pixel_format)

                if was_streaming:
                    cam.stream_on()

            await self._run_blocking(_set)
            self.logger.debug(f"Pixel format set to '{pixel_format}' for camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            raise CameraConfigurationError(
                f"Failed to set pixel format for camera '{self.camera_name}': {e}"
            ) from e

    async def import_config(self, config_path: str):
        """Import camera configuration from JSON file.

        Args:
            config_path: Path to configuration JSON file

        Raises:
            CameraConfigurationError: If configuration file is not found or invalid
        """
        import json

        try:
            if not os.path.exists(config_path):
                raise CameraConfigurationError(f"Configuration file not found: {config_path}")

            with open(config_path, "r") as f:
                config_data = json.load(f)

            if "exposure_time" in config_data:
                await self.set_exposure(config_data["exposure_time"])
            if "gain" in config_data:
                await self.set_gain(config_data["gain"])
            if "trigger_mode" in config_data:
                await self.set_triggermode(config_data["trigger_mode"])
            if "white_balance" in config_data:
                await self.set_auto_wb_once(config_data["white_balance"])

            self.logger.debug(f"Configuration imported from '{config_path}' for camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            raise CameraConfigurationError(f"Failed to import config from '{config_path}': {str(e)}")

    async def export_config(self, config_path: str):
        """Export camera configuration to JSON file.

        Args:
            config_path: Path to save configuration file
        """
        import json

        try:
            config_data = {
                "camera_type": "daheng",
                "camera_name": self.camera_name,
                "timestamp": time.time(),
                "exposure_time": await self.get_exposure(),
                "gain": await self.get_gain(),
                "trigger_mode": self.triggermode,
                "white_balance": await self.get_wb(),
                "pixel_format": await self.get_current_pixel_format(),
                "image_enhancement": self.img_quality_enhancement,
                "retrieve_retry_count": self.retrieve_retry_count,
                "timeout_ms": self.timeout_ms,
            }

            os.makedirs(os.path.dirname(config_path), exist_ok=True)

            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            self.logger.debug(f"Configuration exported to '{config_path}' for camera '{self.camera_name}'")
        except Exception as e:
            self.logger.error(f"Failed to export config to '{config_path}': {str(e)}")

    async def set_capture_timeout(self, timeout_ms: int):
        """Set capture timeout in milliseconds.

        Args:
            timeout_ms: Timeout value in milliseconds

        Raises:
            ValueError: If timeout_ms is negative
        """
        if timeout_ms < 0:
            raise ValueError(f"Timeout must be non-negative, got {timeout_ms}")
        self.timeout_ms = timeout_ms
        self.logger.debug(f"Set capture timeout to {timeout_ms}ms for camera '{self.camera_name}'")

    async def get_capture_timeout(self) -> int:
        """Get current capture timeout in milliseconds.

        Returns:
            Current timeout value in milliseconds
        """
        return self.timeout_ms

    async def close(self):
        """Close the camera and release resources.

        Raises:
            CameraConnectionError: If camera closure fails
        """
        if self.camera is not None:
            try:
                camera = self.camera
                self.camera = None
                self.initialized = False

                def _close():
                    try:
                        if self._streaming:
                            camera.stream_off()
                            self._streaming = False
                    except Exception as e:
                        self.logger.warning(f"Error stopping stream for camera '{self.camera_name}': {str(e)}")

                    try:
                        camera.close_device()
                    except Exception as e:
                        self.logger.warning(f"Error closing camera '{self.camera_name}': {str(e)}")

                await self._run_blocking(_close)
                self.logger.info(f"Daheng camera '{self.camera_name}' closed")

            except Exception as e:
                self.logger.error(f"Error in camera cleanup for '{self.camera_name}': {str(e)}")
                raise CameraConnectionError(f"Failed to close camera '{self.camera_name}': {str(e)}")
            finally:
                await self._cleanup_executor()
