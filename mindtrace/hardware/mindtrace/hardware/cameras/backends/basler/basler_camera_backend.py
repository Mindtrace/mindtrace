"""Basler Camera Backend Module"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

try:
    from pypylon import genicam, pylon  # type: ignore

    PYPYLON_AVAILABLE = True
except ImportError:  # pragma: no cover
    PYPYLON_AVAILABLE = False
    pylon = None
    genicam = None

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


class BaslerCameraBackend(CameraBackend):
    """Basler Camera Backend Implementation

    This class provides a comprehensive implementation for Basler cameras using the pypylon SDK. It supports advanced
    camera features including trigger modes, exposure control, ROI settings, and image quality enhancement.

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

    Usage::

        from mindtrace.hardware.cameras.backends.basler import BaslerCameraBackend

        # Get available cameras
        cameras = BaslerCameraBackend.get_available_cameras()

        # Initialize camera
        camera = BaslerCameraBackend("camera_name", img_quality_enhancement=True)
        success, cam_obj, remote_obj = await camera.initialize()  # Initialize first

        if success:
            # Configure and capture
            await camera.set_exposure(20000)
            await camera.set_triggermode("continuous")
            image = await camera.capture()
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
        The class uses a comprehensive exception hierarchy for precise error reporting:
        - SDKNotAvailableError: pypylon SDK not installed
        - CameraNotFoundError: Camera not detected or accessible
        - CameraInitializationError: Failed to initialize camera
        - CameraConfigurationError: Invalid configuration parameters
        - CameraConnectionError: Connection issues
        - CameraCaptureError: Image acquisition failures
        - CameraTimeoutError: Operation timeout
        - HardwareOperationError: General hardware operation failures

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
        **backend_kwargs,
    ):
        """Initialize Basler camera with configurable parameters.

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
                "3. Ensure camera drivers are properly installed",
            )
        else:
            assert pylon is not None, "pypylon SDK is available but pylon is not initialized"

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
        self.converter = None
        self.grabbing_mode = pylon.GrabStrategy_LatestImageOnly
        self.triggermode = self.camera_config.cameras.trigger_mode

        # Derived operation timeout for non-capture SDK calls
        self._op_timeout_s = max(1.0, float(self.timeout_ms) / 1000.0)

        # Thread executor and event loop for _sdk method
        self._loop = None
        self._sdk_executor = None

        self.logger.info(f"Basler camera '{self.camera_name}' initialized successfully")

    async def _sdk(self, func, *args, timeout: Optional[float] = None, **kwargs):
        """Run a potentially blocking pypylon call on a dedicated thread with timeout.

        Args:
            func: Callable to execute
            *args: Positional args for the callable
            timeout: Optional timeout (seconds). Defaults to self._op_timeout_s
            **kwargs: Keyword args for the callable

        Returns:
            Result of the callable

        Raises:
            CameraTimeoutError: If operation times out
            HardwareOperationError: If operation fails
        """
        import concurrent.futures

        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        if self._sdk_executor is None:
            self._sdk_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix=f"pypylon-{self.camera_name}"
            )

        def _call():
            return func(*args, **kwargs)

        fut = self._loop.run_in_executor(self._sdk_executor, _call)
        try:
            return await asyncio.wait_for(fut, timeout=timeout or self._op_timeout_s)
        except asyncio.TimeoutError as e:
            raise CameraTimeoutError(
                f"Pypylon operation timed out after {timeout or self._op_timeout_s:.2f}s for camera '{self.camera_name}'"
            ) from e
        except Exception as e:
            raise HardwareOperationError(f"Pypylon operation failed for camera '{self.camera_name}': {e}") from e

    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """Get available Basler cameras.

        Args:
            include_details: If True, return detailed information

        Returns:
            List of camera names (user-defined names preferred, serial numbers as fallback) or dict with details

        Raises:
            SDKNotAvailableError: If Basler SDK is not available
            HardwareOperationError: If camera discovery fails
        """
        if not PYPYLON_AVAILABLE:
            raise SDKNotAvailableError("pypylon", "Basler SDK (pypylon) is not available for camera discovery")
        else:
            assert pylon is not None, "pypylon SDK is available but pylon is not initialized"

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
                        "user_defined_name": user_defined_name,
                    }

            return camera_details if include_details else available_cameras

        except Exception as e:
            raise HardwareOperationError(f"Failed to discover Basler cameras: {str(e)}")

    async def initialize(self) -> Tuple[bool, Any, Any]:
        """Initialize the camera connection.

        This searches for the camera by name, serial number, or IP and establishes
        a connection if found.

        Returns:
            Tuple of (success status, camera object, None)

        Raises:
            CameraNotFoundError: If no cameras found or specified camera not found
            CameraInitializationError: If camera initialization fails
            CameraConnectionError: If camera connection fails
        """
        if not PYPYLON_AVAILABLE:
            raise SDKNotAvailableError("pypylon", "Basler SDK (pypylon) is not available for camera discovery")
        else:
            assert pylon is not None, "pypylon SDK is available but pylon is not initialized"
        try:
            # Prepare dedicated single-thread executor for SDK calls
            import concurrent.futures

            self._loop = asyncio.get_running_loop()
            # Create only once
            if not hasattr(self, "_sdk_executor") or self._sdk_executor is None:
                self._sdk_executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix=f"pypylon-{self.camera_name}"
                )

            all_devices = await self._sdk(pylon.TlFactory.GetInstance().EnumerateDevices, timeout=self._op_timeout_s)
            if len(all_devices) == 0:
                raise CameraNotFoundError("No Basler cameras found")

            camera_found = False
            for device in all_devices:
                if device.GetSerialNumber() == self.camera_name or device.GetUserDefinedName() == self.camera_name:
                    camera_found = True
                    try:

                        def _create_and_open():
                            cam = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateDevice(device))
                            cam.Open()
                            return cam

                        camera = await self._sdk(_create_and_open, timeout=self._op_timeout_s)

                        if device.GetSerialNumber() == self.camera_name and device.GetUserDefinedName():
                            self.camera_name = device.GetUserDefinedName()
                            self.logger.debug(
                                f"Camera found by serial number, using user-defined name: '{self.camera_name}'"
                            )

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
                available_cameras = [
                    f"{device.GetSerialNumber()} ({device.GetUserDefinedName()})" for device in all_devices
                ]
                raise CameraNotFoundError(
                    f"Camera '{self.camera_name}' not found. Available cameras: {available_cameras}"
                )

        except (CameraNotFoundError, CameraConnectionError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error initializing Basler camera '{self.camera_name}': {str(e)}")
            raise CameraInitializationError(f"Unexpected error initializing camera '{self.camera_name}': {str(e)}")

    async def _ensure_open(self):
        """Ensure camera is open.

        Raises:
            CameraConnectionError: If camera cannot be opened
        """
        if self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not available")

        try:
            if not await self._sdk(self.camera.IsOpen, timeout=self._op_timeout_s):
                await self._sdk(self.camera.Open, timeout=self._op_timeout_s)
        except Exception as e:
            raise CameraConnectionError(f"Failed to ensure camera '{self.camera_name}' is open: {e}") from e

    async def _ensure_grabbing(self):
        """Ensure camera is grabbing images.

        Raises:
            CameraConnectionError: If camera cannot start grabbing
        """
        if self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not available")

        try:
            await self._ensure_open()
            if not await self._sdk(self.camera.IsGrabbing, timeout=self._op_timeout_s):
                await self._sdk(self.camera.StartGrabbing, self.grabbing_mode, timeout=self._op_timeout_s)
        except Exception as e:
            raise CameraConnectionError(f"Failed to ensure camera '{self.camera_name}' is grabbing: {e}") from e

    async def _ensure_stopped_grabbing(self):
        """Ensure camera has stopped grabbing images.

        Raises:
            CameraConnectionError: If camera cannot stop grabbing
        """
        if self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not available")

        try:
            if await self._sdk(self.camera.IsGrabbing, timeout=self._op_timeout_s):
                await self._sdk(self.camera.StopGrabbing, timeout=self._op_timeout_s)
        except Exception as e:
            raise CameraConnectionError(f"Failed to ensure camera '{self.camera_name}' stopped grabbing: {e}") from e

    @asynccontextmanager
    async def _grabbing_suspended(self):
        """Context manager that temporarily suspends grabbing.

        Useful for configuration operations that require grabbing to be stopped.
        """
        was_grabbing = False
        try:
            if self.camera is not None:
                was_grabbing = await self._sdk(self.camera.IsGrabbing, timeout=self._op_timeout_s)
                if was_grabbing:
                    await self._ensure_stopped_grabbing()
            yield
        finally:
            if was_grabbing and self.camera is not None:
                await self._ensure_grabbing()

    async def _configure_camera(self):
        """Configure initial camera settings.

        Raises:
            CameraConfigurationError: If camera configuration fails
        """
        if not PYPYLON_AVAILABLE:
            raise SDKNotAvailableError("pypylon", "Basler SDK (pypylon) is not available for camera discovery")
        else:
            assert pylon is not None, "pypylon SDK is available but pylon is not initialized"
        try:
            self.converter = pylon.ImageFormatConverter()
            self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

            await self._ensure_open()

            await self._sdk(self.camera.MaxNumBuffer.SetValue, self.buffer_count, timeout=self._op_timeout_s)

            self.logger.debug(f"Basler camera '{self.camera_name}' configured with buffer_count={self.buffer_count}")

        except Exception as e:
            self.logger.error(f"Failed to configure Basler camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to configure camera '{self.camera_name}': {str(e)}")

    async def get_image_quality_enhancement(self) -> bool:
        """Get image quality enhancement setting."""
        return self.img_quality_enhancement

    async def set_image_quality_enhancement(self, value: bool):
        """Set image quality enhancement setting."""
        self.img_quality_enhancement = value
        self.logger.debug(f"Image quality enhancement set to {value} for camera '{self.camera_name}'")

    async def get_exposure_range(self) -> List[Union[int, float]]:
        """Get the supported exposure time range in microseconds.

        Returns:
            List with [min_exposure, max_exposure] in microseconds

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            HardwareOperationError: If exposure range retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            await self._ensure_open()

            min_value = await self._sdk(self.camera.ExposureTime.GetMin, timeout=self._op_timeout_s)
            max_value = await self._sdk(self.camera.ExposureTime.GetMax, timeout=self._op_timeout_s)

            return [min_value, max_value]
        except Exception as e:
            self.logger.warning(f"Exposure range not available for camera '{self.camera_name}': {str(e)}")
            # Return reasonable defaults if exposure feature is not available
            return [1.0, 1000000.0]  # 1 μs to 1 second

    async def get_exposure(self) -> float:
        """Get current exposure time in microseconds.

        Returns:
            Current exposure time

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            HardwareOperationError: If exposure retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            await self._ensure_open()

            exposure = await self._sdk(self.camera.ExposureTime.GetValue, timeout=self._op_timeout_s)
            return exposure
        except Exception as e:
            self.logger.warning(f"Exposure not available for camera '{self.camera_name}': {str(e)}")
            # Return reasonable default if exposure feature is not available
            return 20000.0  # 20ms default

    async def set_exposure(self, exposure: Union[int, float]):
        """Set the camera exposure time in microseconds.

        Args:
            exposure_value: Exposure time in microseconds

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
                    f"Exposure {exposure} outside valid range [{min_exp}, {max_exp}] for camera '{self.camera_name}'"
                )

            await self._ensure_open()

            await self._sdk(self.camera.ExposureTime.SetValue, exposure, timeout=self._op_timeout_s)

            actual_exposure = await self._sdk(self.camera.ExposureTime.GetValue, timeout=self._op_timeout_s)
            if not (abs(actual_exposure - exposure) < 0.01 * max(1.0, float(exposure))):
                raise HardwareOperationError(
                    f"Exposure verification failed for camera '{self.camera_name}': requested={exposure}, actual={actual_exposure}"
                )

        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Exposure setting failed for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set exposure: {str(e)}")

    async def get_triggermode(self) -> str:
        """Get current trigger mode.

        Returns:
            "continuous" or "trigger"

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            HardwareOperationError: If trigger mode retrieval fails
        """
        if not self.initialized or self.camera is None:
            return "continuous"

        try:
            await self._ensure_open()

            async with self._grabbing_suspended():
                trigger_enabled = (
                    await self._sdk(self.camera.TriggerMode.GetValue, timeout=self._op_timeout_s)
                ) == "On"
                trigger_source = (
                    await self._sdk(self.camera.TriggerSource.GetValue, timeout=self._op_timeout_s)
                ) == "Software"

                self.triggermode = "trigger" if (trigger_enabled and trigger_source) else "continuous"
                return self.triggermode

        except Exception as e:
            self.logger.error(f"Error getting trigger mode for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get trigger mode: {str(e)}")

    async def set_triggermode(self, triggermode: str = "continuous"):
        """Set the camera's trigger mode for image acquisition.

        Args:
            triggermode: Trigger mode ("continuous" or "trigger")

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
            await self._ensure_open()

            async with self._grabbing_suspended():
                if triggermode == "continuous":
                    await self._sdk(self.camera.TriggerMode.SetValue, "Off", timeout=self._op_timeout_s)
                else:
                    await self._sdk(self.camera.TriggerSelector.SetValue, "FrameStart", timeout=self._op_timeout_s)
                    await self._sdk(self.camera.TriggerMode.SetValue, "On", timeout=self._op_timeout_s)
                    await self._sdk(self.camera.TriggerSource.SetValue, "Software", timeout=self._op_timeout_s)

                self.triggermode = triggermode

            self.logger.debug(f"Trigger mode set to '{triggermode}' for camera '{self.camera_name}'")

        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Error setting trigger mode for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set trigger mode: {str(e)}")

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
        else:
            assert pylon is not None, "camera is initialized but pylon is not available"
        try:
            await self._ensure_open()

            await self._ensure_grabbing()

            for i in range(self.retrieve_retry_count):
                if i > 0:
                    self.logger.debug(
                        f"Retrying capture {i + 1} of {self.retrieve_retry_count} for camera '{self.camera_name}'"
                    )

                try:
                    if self.triggermode == "trigger":
                        await self._sdk(self.camera.TriggerSoftware.Execute, timeout=self._op_timeout_s)

                    grab_result = await self._sdk(
                        self.camera.RetrieveResult,
                        self.timeout_ms,
                        pylon.TimeoutHandling_ThrowException,
                        timeout=self._op_timeout_s + (self.timeout_ms / 1000.0),
                    )

                    if await self._sdk(grab_result.GrabSucceeded, timeout=self._op_timeout_s):
                        image_converted = await self._sdk(
                            self.converter.Convert, grab_result, timeout=self._op_timeout_s
                        )
                        image = await self._sdk(image_converted.GetArray, timeout=self._op_timeout_s)

                        if self.img_quality_enhancement and image is not None:
                            image = await self._enhance_image(image)

                        await self._sdk(grab_result.Release, timeout=self._op_timeout_s)
                        return image
                    else:
                        error_desc = await self._sdk(grab_result.GetErrorDescription, timeout=self._op_timeout_s)
                        self.logger.warning(f"Grab failed for camera '{self.camera_name}': {error_desc}")
                        await self._sdk(grab_result.Release, timeout=self._op_timeout_s)

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
                f"Failed to capture image after {self.retrieve_retry_count} attempts for camera '{self.camera_name}'"
            )

        except (CameraConnectionError, CameraCaptureError, CameraTimeoutError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during capture for camera '{self.camera_name}': {str(e)}")
            raise CameraCaptureError(f"Unexpected capture error for camera '{self.camera_name}': {str(e)}")

    async def _enhance_image(self, image: np.ndarray) -> np.ndarray:
        """Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) enhancement.

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
                length, a, b = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                cl = clahe.apply(length)
                enhanced_lab = cv2.merge((cl, a, b))
                enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
                return enhanced_img

            return await asyncio.to_thread(enhance)
        except Exception as e:
            self.logger.error(f"Image enhancement failed for camera '{self.camera_name}': {str(e)}")
            raise CameraCaptureError(f"Image enhancement failed: {str(e)}")

    async def check_connection(self) -> bool:
        """Check if camera is connected and operational.

        Returns:
            True if connected and operational, False otherwise
        """
        if not self.initialized:
            return False

        try:
            img = await self.capture()
            return img is not None and img.shape[0] > 0 and img.shape[1] > 0
        except Exception as e:
            self.logger.warning(f"Connection check failed for camera '{self.camera_name}': {str(e)}")
            return False

    async def import_config(self, config_path: str):
        """Import camera configuration from common JSON format.

        Args:
            config_path: Path to configuration file

        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If configuration import fails
        """
        if self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
        else:
            assert genicam is not None, "camera is initialized but genicam is not available"

        if config_path is None or not os.path.exists(config_path):
            raise CameraConfigurationError(f"Configuration file not found: {config_path}")

        try:
            import json

            with open(config_path, "r") as f:
                config_data = json.load(f)

            await self._ensure_open()

            success_count = 0
            total_settings = 0

            async with self._grabbing_suspended():
                # Set exposure time
                if "exposure_time" in config_data:
                    total_settings += 1
                    try:
                        if hasattr(self.camera, "ExposureTime") and self.camera.ExposureTime.GetAccessMode() in [
                            genicam.RW,
                            genicam.WO,
                        ]:
                            await self._sdk(
                                self.camera.ExposureTime.SetValue,
                                float(config_data["exposure_time"]),
                                timeout=self._op_timeout_s,
                            )
                            success_count += 1
                    except Exception as e:
                        self.logger.warning(f"Could not set exposure time for camera '{self.camera_name}': {e}")

                # Set gain
                if "gain" in config_data:
                    total_settings += 1
                    try:
                        if hasattr(self.camera, "Gain") and self.camera.Gain.GetAccessMode() in [
                            genicam.RW,
                            genicam.WO,
                        ]:
                            await self._sdk(
                                self.camera.Gain.SetValue, float(config_data["gain"]), timeout=self._op_timeout_s
                            )
                            success_count += 1
                    except Exception as e:
                        self.logger.warning(f"Could not set gain for camera '{self.camera_name}': {e}")

                # Set trigger mode
                if "trigger_mode" in config_data:
                    total_settings += 1
                    try:
                        if hasattr(self.camera, "TriggerMode") and self.camera.TriggerMode.GetAccessMode() in [
                            genicam.RW,
                            genicam.WO,
                        ]:
                            if config_data["trigger_mode"] == "continuous":
                                await self._sdk(self.camera.TriggerMode.SetValue, "Off", timeout=self._op_timeout_s)
                            else:
                                if hasattr(self.camera, "TriggerSelector"):
                                    await self._sdk(
                                        self.camera.TriggerSelector.SetValue, "FrameStart", timeout=self._op_timeout_s
                                    )
                                await self._sdk(self.camera.TriggerMode.SetValue, "On", timeout=self._op_timeout_s)
                                if hasattr(self.camera, "TriggerSource"):
                                    await self._sdk(
                                        self.camera.TriggerSource.SetValue, "Software", timeout=self._op_timeout_s
                                    )
                            self.triggermode = config_data["trigger_mode"]
                            success_count += 1
                    except Exception as e:
                        self.logger.warning(f"Could not set trigger mode for camera '{self.camera_name}': {e}")

                # Set white balance
                if "white_balance" in config_data:
                    total_settings += 1
                    try:
                        if hasattr(
                            self.camera, "BalanceWhiteAuto"
                        ) and self.camera.BalanceWhiteAuto.GetAccessMode() in [
                            genicam.RW,
                            genicam.WO,
                        ]:
                            wb_mode = config_data["white_balance"]
                            if wb_mode == "off":
                                await self._sdk(
                                    self.camera.BalanceWhiteAuto.SetValue, "Off", timeout=self._op_timeout_s
                                )
                            elif wb_mode == "once":
                                await self._sdk(
                                    self.camera.BalanceWhiteAuto.SetValue, "Once", timeout=self._op_timeout_s
                                )
                            elif wb_mode == "continuous":
                                await self._sdk(
                                    self.camera.BalanceWhiteAuto.SetValue, "Continuous", timeout=self._op_timeout_s
                                )
                            success_count += 1
                    except Exception as e:
                        self.logger.warning(f"Could not set white balance for camera '{self.camera_name}': {e}")

                # Set ROI
                if "roi" in config_data:
                    roi = config_data["roi"]
                    roi_success = 0
                    total_settings += 1

                    try:
                        if hasattr(self.camera, "Width") and self.camera.Width.GetAccessMode() in [
                            genicam.RW,
                            genicam.WO,
                        ]:
                            await self._sdk(
                                self.camera.Width.SetValue, int(roi.get("width", 1920)), timeout=self._op_timeout_s
                            )
                            roi_success += 1
                    except Exception as e:
                        self.logger.warning(f"Could not set ROI Width for camera '{self.camera_name}': {e}")

                    try:
                        if hasattr(self.camera, "Height") and self.camera.Height.GetAccessMode() in [
                            genicam.RW,
                            genicam.WO,
                        ]:
                            await self._sdk(
                                self.camera.Height.SetValue, int(roi.get("height", 1080)), timeout=self._op_timeout_s
                            )
                            roi_success += 1
                    except Exception as e:
                        self.logger.warning(f"Could not set ROI Height for camera '{self.camera_name}': {e}")

                    try:
                        if hasattr(self.camera, "OffsetX") and self.camera.OffsetX.GetAccessMode() in [
                            genicam.RW,
                            genicam.WO,
                        ]:
                            await self._sdk(
                                self.camera.OffsetX.SetValue, int(roi.get("x", 0)), timeout=self._op_timeout_s
                            )
                            roi_success += 1
                    except Exception as e:
                        self.logger.warning(f"Could not set ROI OffsetX for camera '{self.camera_name}': {e}")

                    try:
                        if hasattr(self.camera, "OffsetY") and self.camera.OffsetY.GetAccessMode() in [
                            genicam.RW,
                            genicam.WO,
                        ]:
                            await self._sdk(
                                self.camera.OffsetY.SetValue, int(roi.get("y", 0)), timeout=self._op_timeout_s
                            )
                            roi_success += 1
                    except Exception as e:
                        self.logger.warning(f"Could not set ROI OffsetY for camera '{self.camera_name}': {e}")

                    if roi_success > 0:
                        success_count += 1

                # Set pixel format
                if "pixel_format" in config_data:
                    total_settings += 1
                    try:
                        if hasattr(self.camera, "PixelFormat") and self.camera.PixelFormat.GetAccessMode() in [
                            genicam.RW,
                            genicam.WO,
                        ]:
                            available_formats = await self.get_pixel_format_range()
                            pixel_format = config_data["pixel_format"]
                            if pixel_format in available_formats:
                                await self._sdk(
                                    self.camera.PixelFormat.SetValue, pixel_format, timeout=self._op_timeout_s
                                )
                                success_count += 1
                    except Exception as e:
                        self.logger.warning(f"Could not set pixel format for camera '{self.camera_name}': {e}")

                # Apply other settings
                if "image_enhancement" in config_data:
                    self.img_quality_enhancement = config_data["image_enhancement"]
                    success_count += 1
                    total_settings += 1

                if "retrieve_retry_count" in config_data:
                    self.retrieve_retry_count = config_data["retrieve_retry_count"]
                    success_count += 1
                    total_settings += 1

                if "timeout_ms" in config_data:
                    self.timeout_ms = config_data["timeout_ms"]
                    success_count += 1
                    total_settings += 1

            self.logger.debug(
                f"Configuration imported from '{config_path}' for camera '{self.camera_name}': "
                f"{success_count}/{total_settings} settings applied successfully"
            )

        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Error importing configuration for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to import configuration: {str(e)}")

    async def export_config(self, config_path: str):
        """Export current camera configuration to common JSON format.

        Args:
            config_path: Path where to save configuration file

        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If configuration export fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
        else:
            assert genicam is not None, "camera is initialized but genicam is not available"

        try:
            import json

            os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)

            await self._ensure_open()

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
                "pixel_format": "BayerRG8",
            }

            # Get current camera settings with fallbacks
            exposure_time = defaults["exposure_time"]
            try:
                exposure_time = await self._sdk(self.camera.ExposureTime.GetValue, timeout=self._op_timeout_s)
            except Exception as e:
                self.logger.warning(f"Could not get exposure time for camera '{self.camera_name}': {e}")

            gain = defaults["gain"]
            try:
                if hasattr(self.camera, "Gain"):
                    gain = await self._sdk(self.camera.Gain.GetValue, timeout=self._op_timeout_s)
            except Exception as e:
                self.logger.warning(f"Could not get gain for camera '{self.camera_name}': {e}")

            trigger_mode = defaults["trigger_mode"]
            try:
                trigger_enabled = await self._sdk(self.camera.TriggerMode.GetValue, timeout=self._op_timeout_s) == "On"
                trigger_source = (
                    await self._sdk(self.camera.TriggerSource.GetValue, timeout=self._op_timeout_s) == "Software"
                )
                trigger_mode = "trigger" if (trigger_enabled and trigger_source) else "continuous"
            except Exception as e:
                self.logger.warning(f"Could not get trigger mode for camera '{self.camera_name}': {e}")

            white_balance = defaults["white_balance"]
            try:
                if (
                    self.camera.BalanceWhiteAuto.GetAccessMode() == genicam.RO
                    or self.camera.BalanceWhiteAuto.GetAccessMode() == genicam.RW
                ):
                    wb_auto = await self._sdk(self.camera.BalanceWhiteAuto.GetValue, timeout=self._op_timeout_s)
                    white_balance = wb_auto.lower()
            except Exception as e:
                self.logger.warning(f"Could not get white balance for camera '{self.camera_name}': {e}")

            # Get image dimensions and ROI
            width = defaults["width"]
            height = defaults["height"]
            try:
                width = int(await self._sdk(self.camera.Width.GetValue, timeout=self._op_timeout_s))
                height = int(await self._sdk(self.camera.Height.GetValue, timeout=self._op_timeout_s))
            except Exception as e:
                self.logger.warning(f"Could not get image dimensions for camera '{self.camera_name}': {e}")

            roi_x = defaults["roi_x"]
            roi_y = defaults["roi_y"]
            try:
                roi_x = int(await self._sdk(self.camera.OffsetX.GetValue, timeout=self._op_timeout_s))
                roi_y = int(await self._sdk(self.camera.OffsetY.GetValue, timeout=self._op_timeout_s))
            except Exception as e:
                self.logger.warning(f"Could not get ROI offsets for camera '{self.camera_name}': {e}")

            pixel_format = defaults["pixel_format"]
            try:
                pixel_format = await self._sdk(self.camera.PixelFormat.GetValue, timeout=self._op_timeout_s)
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
                "buffer_count": getattr(self, "buffer_count", 25),
            }

            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            self.logger.debug(
                f"Configuration exported to '{config_path}' for camera '{self.camera_name}' using common JSON format"
            )

        except Exception as e:
            self.logger.error(f"Error exporting configuration for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to export configuration: {str(e)}")

    async def set_ROI(self, x: int, y: int, width: int, height: int):
        """Set the Region of Interest (ROI) for image acquisition.

        Args:
            x: X offset from sensor top-left
            y: Y offset from sensor top-left
            width: ROI width
            height: ROI height

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
            await self._ensure_open()

            async with self._grabbing_suspended():
                # Check bounds against camera capabilities before setting
                max_width = await self._sdk(self.camera.Width.GetMax, timeout=self._op_timeout_s)
                max_height = await self._sdk(self.camera.Height.GetMax, timeout=self._op_timeout_s)
                max_offset_x = await self._sdk(self.camera.OffsetX.GetMax, timeout=self._op_timeout_s)
                max_offset_y = await self._sdk(self.camera.OffsetY.GetMax, timeout=self._op_timeout_s)

                if width > max_width or height > max_height:
                    raise CameraConfigurationError(
                        f"ROI dimensions {width}x{height} out of range (max {max_width}x{max_height})"
                    )
                if x > max_offset_x or y > max_offset_y:
                    raise CameraConfigurationError(
                        f"ROI offsets ({x}, {y}) out of range (max {max_offset_x}, {max_offset_y})"
                    )

                x_inc = await self._sdk(self.camera.OffsetX.GetInc, timeout=self._op_timeout_s)
                y_inc = await self._sdk(self.camera.OffsetY.GetInc, timeout=self._op_timeout_s)
                width_inc = await self._sdk(self.camera.Width.GetInc, timeout=self._op_timeout_s)
                height_inc = await self._sdk(self.camera.Height.GetInc, timeout=self._op_timeout_s)

                x = (x // x_inc) * x_inc
                y = (y // y_inc) * y_inc
                width = (width // width_inc) * width_inc
                height = (height // height_inc) * height_inc

                await self._sdk(self.camera.Width.SetValue, width, timeout=self._op_timeout_s)
                await self._sdk(self.camera.Height.SetValue, height, timeout=self._op_timeout_s)
                await self._sdk(self.camera.OffsetX.SetValue, x, timeout=self._op_timeout_s)
                await self._sdk(self.camera.OffsetY.SetValue, y, timeout=self._op_timeout_s)

            self.logger.debug(f"ROI set to ({x}, {y}, {width}, {height}) for camera '{self.camera_name}'")

        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Error setting ROI for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set ROI: {str(e)}")

    async def get_ROI(self) -> Dict[str, int]:
        """Get current Region of Interest settings.

        Returns:
            Dictionary with x, y, width, height

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If ROI retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            roi = {
                "x": await self._sdk(self.camera.OffsetX.GetValue, timeout=self._op_timeout_s),
                "y": await self._sdk(self.camera.OffsetY.GetValue, timeout=self._op_timeout_s),
                "width": await self._sdk(self.camera.Width.GetValue, timeout=self._op_timeout_s),
                "height": await self._sdk(self.camera.Height.GetValue, timeout=self._op_timeout_s),
            }

            return roi

        except Exception as e:
            self.logger.error(f"Error getting ROI for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get ROI: {str(e)}")

    async def reset_ROI(self):
        """Reset ROI to maximum sensor area.

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If ROI reset fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            async with self._grabbing_suspended():
                await self._sdk(self.camera.OffsetX.SetValue, 0, timeout=self._op_timeout_s)
                await self._sdk(self.camera.OffsetY.SetValue, 0, timeout=self._op_timeout_s)

                max_width = await self._sdk(self.camera.Width.GetMax, timeout=self._op_timeout_s)
                max_height = await self._sdk(self.camera.Height.GetMax, timeout=self._op_timeout_s)

                width_inc = await self._sdk(self.camera.Width.GetInc, timeout=self._op_timeout_s)
                height_inc = await self._sdk(self.camera.Height.GetInc, timeout=self._op_timeout_s)
                max_width = (max_width // width_inc) * width_inc
                max_height = (max_height // height_inc) * height_inc

                await self._sdk(self.camera.Width.SetValue, max_width, timeout=self._op_timeout_s)
                await self._sdk(self.camera.Height.SetValue, max_height, timeout=self._op_timeout_s)

            self.logger.debug(f"ROI reset to maximum for camera '{self.camera_name}'")

        except Exception as e:
            self.logger.error(f"Error resetting ROI for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to reset ROI: {str(e)}")

    async def set_gain(self, gain: float):
        """Set the camera's gain value.

        Args:
            gain: Gain value (camera-specific range)

        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If gain value is out of range
            HardwareOperationError: If gain setting fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            min_gain, max_gain = await self.get_gain_range()

            if gain < min_gain or gain > max_gain:
                raise CameraConfigurationError(
                    f"Gain {gain} outside valid range [{min_gain}, {max_gain}] for camera '{self.camera_name}'"
                )

            await self._ensure_open()

            await self._sdk(self.camera.Gain.SetValue, gain, timeout=self._op_timeout_s)
            self.logger.debug(f"Gain set to {gain} for camera '{self.camera_name}'")

        except (CameraConnectionError, CameraConfigurationError):
            raise  # Re-raise these specific errors
        except Exception as e:
            raise HardwareOperationError(f"Failed to set gain for camera '{self.camera_name}': {str(e)}") from e

    async def get_gain(self) -> float:
        """Get current camera gain.

        Returns:
            Current gain value

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If gain retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            gain = await self._sdk(self.camera.Gain.GetValue, timeout=self._op_timeout_s)
            return gain

        except Exception as e:
            self.logger.warning(f"Gain not available for camera '{self.camera_name}': {str(e)}")
            # Return reasonable default if gain feature is not available
            return 1.0  # Unity gain default

    async def get_gain_range(self) -> List[Union[int, float]]:
        """Get camera gain range.

        Returns:
            List containing [min_gain, max_gain]

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If gain range retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            min_gain = await self._sdk(self.camera.Gain.GetMin, timeout=self._op_timeout_s)
            max_gain = await self._sdk(self.camera.Gain.GetMax, timeout=self._op_timeout_s)
            return [min_gain, max_gain]

        except Exception as e:
            self.logger.warning(f"Gain range not available for camera '{self.camera_name}': {str(e)}")
            # Return reasonable defaults if gain feature is not available
            return [1.0, 16.0]  # Common gain range

    # Network-related functionality for GigE cameras
    async def set_bandwidth_limit(self, limit_mbps: Optional[float]):
        """Set GigE camera bandwidth limit in Mbps."""
        if not self.initialized or not self.camera:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            if hasattr(self.camera, "DeviceLinkThroughputLimitMode"):
                if limit_mbps is not None and hasattr(self.camera, "DeviceLinkThroughputLimit"):
                    # Enable bandwidth limiting and set limit
                    await self._sdk(
                        self.camera.DeviceLinkThroughputLimitMode.SetValue, "On", timeout=self._op_timeout_s
                    )
                    # Convert Mbps to bytes per second
                    limit_bps = int(limit_mbps * 1024 * 1024 / 8)
                    await self._sdk(
                        self.camera.DeviceLinkThroughputLimit.SetValue, limit_bps, timeout=self._op_timeout_s
                    )
                    self.logger.debug(f"Set bandwidth limit to {limit_mbps} Mbps for camera '{self.camera_name}'")
                elif limit_mbps is None:
                    # Disable bandwidth limiting
                    await self._sdk(
                        self.camera.DeviceLinkThroughputLimitMode.SetValue, "Off", timeout=self._op_timeout_s
                    )
                    self.logger.debug(f"Disabled bandwidth limit for camera '{self.camera_name}'")
            else:
                self.logger.error(f"Bandwidth limiting not supported for camera '{self.camera_name}'")
                raise NotImplementedError(f"Bandwidth limiting not supported for camera '{self.camera_name}'")

        except Exception as e:
            self.logger.error(f"Error setting bandwidth limit for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set bandwidth limit: {str(e)}")

    async def get_bandwidth_limit(self) -> float:
        """Get current bandwidth limit in Mbps."""
        if not self.initialized or not self.camera:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            if hasattr(self.camera, "DeviceLinkThroughputLimitMode"):
                mode = await self._sdk(self.camera.DeviceLinkThroughputLimitMode.GetValue, timeout=self._op_timeout_s)
                if mode == "Off":
                    return 0.0  # No limit

                if hasattr(self.camera, "DeviceLinkThroughputLimit"):
                    limit_bps = await self._sdk(
                        self.camera.DeviceLinkThroughputLimit.GetValue, timeout=self._op_timeout_s
                    )
                    # Convert bytes per second to Mbps
                    limit_mbps = (limit_bps * 8) / (1024 * 1024)
                    return float(limit_mbps)

            return 0.0  # No limit or not supported

        except Exception as e:
            self.logger.error(f"Error getting bandwidth limit for camera '{self.camera_name}': {str(e)}")
            raise RuntimeError(f"Failed to get bandwidth limit: {str(e)}")

    async def set_packet_size(self, size: int):
        """Set GigE packet size for network optimization."""
        if not self.initialized or not self.camera:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            if hasattr(self.camera, "GevSCPSPacketSize"):
                await self._sdk(self.camera.GevSCPSPacketSize.SetValue, size, timeout=self._op_timeout_s)
                self.logger.debug(f"Set packet size to {size} bytes for camera '{self.camera_name}'")
            else:
                self.logger.error(f"Packet size control not supported for camera '{self.camera_name}'")
                raise NotImplementedError(f"Packet size control not supported for camera '{self.camera_name}'")

        except Exception as e:
            self.logger.error(f"Error setting packet size for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set packet size: {str(e)}")

    async def get_packet_size(self) -> int:
        """Get current packet size."""
        if not self.initialized or not self.camera:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            if hasattr(self.camera, "GevSCPSPacketSize"):
                size = await self._sdk(self.camera.GevSCPSPacketSize.GetValue, timeout=self._op_timeout_s)
                return int(size)
            else:
                raise NotImplementedError(f"Packet size query not supported for camera '{self.camera_name}'")

        except Exception as e:
            self.logger.error(f"Error getting packet size for camera '{self.camera_name}': {str(e)}")
            raise RuntimeError(f"Failed to get packet size: {str(e)}")

    async def set_inter_packet_delay(self, delay_ticks: int):
        """Set inter-packet delay for network traffic control."""
        if not self.initialized or not self.camera:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            if hasattr(self.camera, "GevSCPD"):
                await self._sdk(self.camera.GevSCPD.SetValue, delay_ticks, timeout=self._op_timeout_s)
                self.logger.debug(f"Set inter-packet delay to {delay_ticks} ticks for camera '{self.camera_name}'")
            else:
                self.logger.error(f"Inter-packet delay control not supported for camera '{self.camera_name}'")
                raise NotImplementedError(f"Inter-packet delay control not supported for camera '{self.camera_name}'")

        except Exception as e:
            self.logger.error(f"Error setting inter-packet delay for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set inter-packet delay: {str(e)}")

    async def get_inter_packet_delay(self) -> int:
        """Get current inter-packet delay."""
        if not self.initialized or not self.camera:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            if hasattr(self.camera, "GevSCPD"):
                delay = await self._sdk(self.camera.GevSCPD.GetValue, timeout=self._op_timeout_s)
                return int(delay)
            else:
                raise NotImplementedError(f"Inter-packet delay query not supported for camera '{self.camera_name}'")

        except Exception as e:
            self.logger.error(f"Error getting inter-packet delay for camera '{self.camera_name}': {str(e)}")
            raise RuntimeError(f"Failed to get inter-packet delay: {str(e)}")

    async def get_wb_range(self) -> List[str]:
        """Get available white balance modes.

        Returns:
            List of available white balance modes
        """
        return ["off", "once", "continuous"]

    async def get_width_range(self) -> List[int]:
        """Get camera width range.

        Returns:
            List containing [min_width, max_width]

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If width range retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            min_width = await self._sdk(self.camera.Width.GetMin, timeout=self._op_timeout_s)
            max_width = await self._sdk(self.camera.Width.GetMax, timeout=self._op_timeout_s)
            return [min_width, max_width]

        except Exception as e:
            self.logger.error(f"Error getting width range for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get width range: {str(e)}")

    async def get_height_range(self) -> List[int]:
        """Get camera height range.

        Returns:
            List containing [min_height, max_height]

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If height range retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            min_height = await self._sdk(self.camera.Height.GetMin, timeout=self._op_timeout_s)
            max_height = await self._sdk(self.camera.Height.GetMax, timeout=self._op_timeout_s)
            return [min_height, max_height]

        except Exception as e:
            self.logger.error(f"Error getting height range for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get height range: {str(e)}")

    async def get_pixel_format_range(self) -> List[str]:
        """Get available pixel formats.

        Returns:
            List of available pixel formats

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If pixel format range retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
        else:
            assert genicam is not None, "camera is initialized but genicam is not available"

        try:
            await self._ensure_open()

            # Get available pixel formats from camera
            available_formats = []
            pixel_format_entries = await self._sdk(self.camera.PixelFormat.GetEntries, timeout=self._op_timeout_s)
            for entry in pixel_format_entries:
                access_mode = await self._sdk(entry.GetAccessMode, timeout=self._op_timeout_s)
                if access_mode == genicam.RW or access_mode == genicam.RO:
                    symbolic_name = await self._sdk(entry.GetSymbolic, timeout=self._op_timeout_s)
                    available_formats.append(symbolic_name)

            return available_formats if available_formats else ["BGR8", "RGB8", "Mono8"]

        except Exception as e:
            self.logger.error(f"Error getting pixel format range for camera '{self.camera_name}': {str(e)}")
            return ["BGR8", "RGB8", "Mono8", "BayerRG8", "BayerGB8", "BayerGR8", "BayerBG8"]

    async def get_current_pixel_format(self) -> str:
        """Get current pixel format.

        Returns:
            Current pixel format

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If pixel format retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            pixel_format = await self._sdk(self.camera.PixelFormat.GetValue, timeout=self._op_timeout_s)
            return pixel_format

        except Exception as e:
            self.logger.error(f"Error getting current pixel format for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get current pixel format: {str(e)}")

    async def set_pixel_format(self, pixel_format: str):
        """Set pixel format.

        Args:
            pixel_format: Pixel format to set

        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If pixel format is invalid
            HardwareOperationError: If pixel format setting fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_open()

            # Check if pixel format is available
            available_formats = await self.get_pixel_format_range()
            if pixel_format not in available_formats:
                raise CameraConfigurationError(
                    f"Pixel format '{pixel_format}' not supported. Available formats: {available_formats}"
                )

            # Use the grabbing suspension context manager for thread-safe pixel format change
            async with self._grabbing_suspended():
                await self._sdk(self.camera.PixelFormat.SetValue, pixel_format, timeout=self._op_timeout_s)

            self.logger.debug(f"Pixel format set to '{pixel_format}' for camera '{self.camera_name}'")

        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Error setting pixel format for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set pixel format: {str(e)}")

    async def get_wb(self) -> str:
        """Get the current white balance auto setting.

        Returns:
            White balance auto setting ("off", "once", "continuous")

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If white balance retrieval fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
        else:
            assert genicam is not None, "camera is initialized but genicam is not available"

        try:
            was_open = self.camera.IsOpen()
            if not was_open:
                self.camera.Open()

            if (
                self.camera.BalanceWhiteAuto.GetAccessMode() == genicam.RO
                or self.camera.BalanceWhiteAuto.GetAccessMode() == genicam.RW
            ):
                wb_auto = await self._sdk(self.camera.BalanceWhiteAuto.GetValue, timeout=self._op_timeout_s)
                return wb_auto.lower()
            else:
                self.logger.warning(f"BalanceWhiteAuto feature not available on camera '{self.camera_name}'")
                return "off"

        except Exception as e:
            self.logger.error(f"Error getting white balance for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get white balance: {str(e)}")

    async def set_auto_wb_once(self, value: str):
        """Set the white balance auto mode.

        Args:
            value: White balance mode ("off", "once", "continuous")

        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If white balance mode is invalid
            HardwareOperationError: If white balance setting fails
        """
        if not self.initialized or self.camera is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
        else:
            assert genicam is not None, "camera is initialized but genicam is not available"

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
                self.logger.error(f"BalanceWhiteAuto feature not writable on camera '{self.camera_name}'")
                raise HardwareOperationError(f"BalanceWhiteAuto feature not writable on camera '{self.camera_name}'")

            if value == "off":
                await self._sdk(self.camera.BalanceWhiteAuto.SetValue, "Off", timeout=self._op_timeout_s)
                target_mode = "Off"
            elif value == "once":
                await self._sdk(self.camera.BalanceWhiteAuto.SetValue, "Once", timeout=self._op_timeout_s)
                target_mode = "Once"
            elif value == "continuous":
                await self._sdk(self.camera.BalanceWhiteAuto.SetValue, "Continuous", timeout=self._op_timeout_s)
                target_mode = "Continuous"
            else:
                raise CameraConfigurationError(
                    f"Invalid white balance mode '{value}' for camera '{self.camera_name}'. "
                    "Must be 'off', 'once', or 'continuous'"
                )

            actual_mode = await self._sdk(self.camera.BalanceWhiteAuto.GetValue, timeout=self._op_timeout_s)
            if actual_mode == target_mode:
                self.logger.debug(f"White balance mode set to '{actual_mode}' for camera '{self.camera_name}'")
            else:
                self.logger.error(
                    f"Failed to set white balance mode for camera '{self.camera_name}'. "
                    f"Target: {target_mode}, Actual: {actual_mode}"
                )
                raise HardwareOperationError(
                    f"Failed to set white balance mode for camera '{self.camera_name}'. "
                    f"Target: {target_mode}, Actual: {actual_mode}"
                )

        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Error setting white balance for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set white balance: {str(e)}")

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

                try:
                    if await self._sdk(camera.IsGrabbing, timeout=self._op_timeout_s):
                        await self._sdk(camera.StopGrabbing, timeout=self._op_timeout_s)
                except Exception as e:
                    self.logger.warning(f"Error stopping grab for camera '{self.camera_name}': {str(e)}")

                try:
                    if await self._sdk(camera.IsOpen, timeout=self._op_timeout_s):
                        await self._sdk(camera.Close, timeout=self._op_timeout_s)
                except Exception as e:
                    self.logger.warning(f"Error closing camera '{self.camera_name}': {str(e)}")

                self.logger.info(f"Basler camera '{self.camera_name}' closed")

                # Shutdown executor if present
                try:
                    if hasattr(self, "_sdk_executor") and self._sdk_executor is not None:
                        self._sdk_executor.shutdown(wait=False, cancel_futures=True)
                        self._sdk_executor = None
                except Exception:
                    pass

            except Exception as e:
                self.logger.error(f"Error in camera cleanup for '{self.camera_name}': {str(e)}")
                raise CameraConnectionError(f"Failed to close camera '{self.camera_name}': {str(e)}")
