from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2

from mindtrace.core import Mindtrace
from mindtrace.hardware.cameras.backends.camera_backend import CameraBackend
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
    CameraTimeoutError,
)
from mindtrace.hardware.core.utils import convert_image_format, validate_output_format


class AsyncCamera(Mindtrace):
    """Unified async camera interface that wraps backend-specific camera instances."""

    def __init__(self, camera: CameraBackend, name: str, **kwargs):
        super().__init__(**kwargs)
        self._backend = camera
        self._full_name = name
        self._lock = asyncio.Lock()

        parts = name.split(":", 1)
        self._backend_name = parts[0]
        self._device_name = parts[1] if len(parts) > 1 else name

        self.logger.debug(
            f"AsyncCamera created: name={self._full_name}, backend={self._backend}, device={self._device_name}"
        )

    @classmethod
    async def open(cls, name: Optional[str] = None, **kwargs) -> "AsyncCamera":
        """Create and initialize an AsyncCamera with sensible defaults.

        If no name is provided, probes OpenCV and uses the first available device (e.g., ``OpenCV:opencv_camera_0``),
        rather than assuming index 0 is present.

        Args:
            name: Optional full name in the form ``Backend:device_name``.

        Returns:
            An initialized AsyncCamera instance.

        Raises:
            CameraInitializationError: If the backend cannot be initialized
            CameraConnectionError: If the device cannot be opened
        """
        if name is None:
            # Discover first available OpenCV device
            try:
                from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import (
                    OpenCVCameraBackend,
                )

                names = OpenCVCameraBackend.get_available_cameras(include_details=False)
                if not names:
                    raise CameraNotFoundError("No OpenCV cameras available for default open")
                target = f"OpenCV:{names[0]}"
            except Exception as e:
                raise CameraInitializationError(f"Failed to discover default OpenCV camera: {e}")
        else:
            target = name
        parts = target.split(":", 1)
        backend_name = parts[0]
        device_name = parts[1] if len(parts) > 1 else target

        backend: CameraBackend
        try:
            if backend_name.lower() == "opencv":
                from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import (
                    OpenCVCameraBackend,
                )

                backend = OpenCVCameraBackend(device_name)
            elif backend_name.lower() == "basler":
                try:
                    from mindtrace.hardware.cameras.backends.basler import BASLER_AVAILABLE, BaslerCameraBackend

                    if BASLER_AVAILABLE:
                        backend = BaslerCameraBackend(device_name)
                    else:
                        raise ImportError("Real Basler backend not available, pypylon not installed")
                except ImportError:
                    # Fall back to mock if real backend unavailable
                    from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import (
                        MockBaslerCameraBackend,
                    )

                    backend = MockBaslerCameraBackend(device_name)
            elif backend_name.lower() in {"mockbasler", "mock_basler"}:
                from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import (
                    MockBaslerCameraBackend,
                )

                backend = MockBaslerCameraBackend(device_name)
            elif backend_name.lower() == "genicam":
                from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import (
                    GenICamCameraBackend,
                )

                backend = GenICamCameraBackend(device_name)
            else:
                raise CameraInitializationError(
                    f"Unsupported backend '{backend_name}'. Try 'OpenCV:opencv_camera_0', 'GenICam:camera_id', or a mock Basler."
                )

            ok, _, _ = await backend.initialize()
            if not ok:
                raise CameraInitializationError(f"Failed to initialize camera '{target}'")
            return cls(backend, name=target, **kwargs)
        except (CameraInitializationError, CameraConnectionError):
            raise
        except Exception as e:
            raise CameraInitializationError(f"Failed to open camera '{target}': {e}")

    @property
    def name(self) -> str:
        """Full camera name including backend prefix.

        Returns:
            The full name in the form "Backend:device_name".
        """
        return self._full_name

    @property
    def backend_name(self) -> str:
        """Backend identifier string.

        Returns:
            The backend name (e.g., "Basler", "OpenCV").
        """
        return self._backend_name

    @property
    def backend(self) -> CameraBackend:
        """Backend instance implementing the camera SDK.

        Returns:
            The concrete backend object implementing `CameraBackend`.
        """
        return self._backend

    @property
    def device_name(self) -> str:
        """Device identifier without backend prefix.

        Returns:
            The device name (e.g., camera serial or index).
        """
        return self._device_name

    @property
    def is_connected(self) -> bool:
        """Connection status flag.

        Returns:
            True if the underlying backend is initialized/open, otherwise False.
        """
        return self._backend.initialized

    # Async context manager support
    async def __aenter__(self) -> "AsyncCamera":
        parent_aenter = getattr(super(), "__aenter__", None)
        if callable(parent_aenter):
            res = await parent_aenter()  # type: ignore[misc]
            return res if res is not None else self
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            await self._backend.close()
        finally:
            parent_aexit = getattr(super(), "__aexit__", None)
            if callable(parent_aexit):
                return await parent_aexit(exc_type, exc, tb)  # type: ignore[misc]
            return False

    async def capture(self, save_path: Optional[str] = None, output_format: str = "pil") -> Any:
        """Capture an image from the camera with retry logic.

        Args:
            save_path: Optional path to save the captured image (written as-is, typically RGB uint8).
            output_format: Output format for the returned image ("numpy" or "pil").

        Returns:
            The captured image as numpy array or PIL.Image depending on output_format.

        Raises:
            CameraCaptureError: If image capture ultimately fails after retries.
            CameraConnectionError: If the camera connection fails during capture.
            CameraTimeoutError: If the capture exceeds the configured timeout.
            RuntimeError: For unexpected errors after exhausting retries.
            ValueError: If output_format is not supported.
            ImportError: If PIL is required but not available.
        """
        # Validate output format early
        output_format = validate_output_format(output_format)

        async with self._lock:
            retry_count = self._backend.retrieve_retry_count
            self.logger.debug(
                f"Starting capture for '{self._full_name}' with up to {retry_count} attempts, save_path={save_path!r}, output_format={output_format!r}"
            )
            for attempt in range(retry_count):
                try:
                    image = await self._backend.capture()
                    if image is not None:
                        if save_path:
                            dirname = os.path.dirname(save_path)
                            if dirname:
                                os.makedirs(dirname, exist_ok=True)
                            cv2.imwrite(save_path, image)
                            self.logger.debug(f"Saved captured image to '{save_path}'")

                        self.logger.debug(
                            f"Capture successful for '{self._full_name}' on attempt {attempt + 1}/{retry_count}"
                        )
                        # Convert image to requested format before returning
                        return convert_image_format(image, output_format)
                    raise CameraCaptureError(f"Capture returned None for camera '{self._full_name}'")
                except CameraCaptureError as e:
                    delay = 0.1 * (2**attempt)
                    self.logger.warning(
                        f"Capture retry {attempt + 1}/{retry_count} for camera '{self._full_name}': {e}"
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(delay)
                    else:
                        self.logger.error(
                            f"Capture failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                        raise CameraCaptureError(
                            f"Capture failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                except CameraConnectionError as e:
                    delay = 0.5 * (2**attempt)
                    self.logger.warning(
                        f"Network retry {attempt + 1}/{retry_count} for camera '{self._full_name}': {e}"
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(delay)
                    else:
                        self.logger.error(
                            f"Connection failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                        raise CameraConnectionError(
                            f"Connection failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                except CameraTimeoutError as e:
                    delay = 0.3 * (2**attempt)
                    self.logger.warning(
                        f"Timeout retry {attempt + 1}/{retry_count} for camera '{self._full_name}': {e}"
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(delay)
                    else:
                        self.logger.error(
                            f"Timeout failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                        raise CameraTimeoutError(
                            f"Timeout failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                except (CameraNotFoundError, CameraInitializationError, CameraConfigurationError) as e:
                    self.logger.error(f"Non-retryable error for camera '{self._full_name}': {e}")
                    raise
                except Exception as e:
                    delay = 0.2 * (2**attempt)
                    self.logger.warning(
                        f"Unexpected error retry {attempt + 1}/{retry_count} for camera '{self._full_name}': {e}"
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(delay)
                    else:
                        self.logger.error(
                            f"Unexpected error failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                        raise RuntimeError(
                            f"Failed to capture image from camera '{self._full_name}' after {retry_count} attempts: {e}"
                        )
            raise RuntimeError(f"Failed to capture image from camera '{self._full_name}' after {retry_count} attempts")

    async def configure(self, **settings):
        """Configure multiple camera settings atomically.

        Args:
            **settings: Supported keys include exposure, gain, roi=(x, y, w, h), trigger_mode,
                pixel_format, white_balance, image_enhancement, capture_timeout.

        Raises:
            CameraConfigurationError: If a provided value is invalid for the backend.
            CameraConnectionError: If the camera cannot be configured.
        """
        async with self._lock:
            self.logger.debug(f"Configuring camera '{self._full_name}' with settings: {settings}")
            # Handle both "exposure" and "exposure_time" for backwards compatibility and user convenience
            if "exposure_time" in settings:
                await self._backend.set_exposure(settings["exposure_time"])
            elif "exposure" in settings:
                await self._backend.set_exposure(settings["exposure"])
            if "gain" in settings:
                await self._backend.set_gain(settings["gain"])
            if "roi" in settings:
                x, y, w, h = settings["roi"]
                await self._backend.set_ROI(x, y, w, h)
            if "trigger_mode" in settings:
                await self._backend.set_triggermode(settings["trigger_mode"])
            if "pixel_format" in settings:
                await self._backend.set_pixel_format(settings["pixel_format"])
            if "white_balance" in settings:
                await self._backend.set_auto_wb_once(settings["white_balance"])
            if "image_enhancement" in settings:
                await self._backend.set_image_quality_enhancement(settings["image_enhancement"])
            # Handle both "capture_timeout" and "timeout_ms" for backwards compatibility
            if "capture_timeout" in settings:
                await self._backend.set_capture_timeout(settings["capture_timeout"])
            elif "timeout_ms" in settings:
                await self._backend.set_capture_timeout(settings["timeout_ms"])
            self.logger.debug(f"Configuration completed for camera '{self._full_name}'")
            return True

    async def set_exposure(self, exposure: Union[int, float]):
        """Set the camera exposure.

        Args:
            exposure: Exposure value appropriate for the backend.
        """
        async with self._lock:
            await self._backend.set_exposure(exposure)
            return True

    async def get_exposure(self) -> float:
        """Get the current exposure value.

        Returns:
            The current exposure as a float.
        """
        return await self._backend.get_exposure()

    async def get_exposure_range(self) -> Tuple[float, float]:
        """Get the valid exposure range.

        Returns:
            A tuple of (min_exposure, max_exposure).
        """
        range_list = await self._backend.get_exposure_range()
        return range_list[0], range_list[1]

    async def set_gain(self, gain: Union[int, float]):
        """Set the camera gain.

        Args:
            gain: Gain value to apply.
        """
        await self._backend.set_gain(gain)
        return True

    async def get_gain(self) -> float:
        """Get the current camera gain.

        Returns:
            The current gain as a float.
        """
        return await self._backend.get_gain()

    async def get_gain_range(self) -> Tuple[float, float]:
        """Get the valid gain range.

        Returns:
            A tuple of (min_gain, max_gain).
        """
        range_list = await self._backend.get_gain_range()
        return range_list[0], range_list[1]

    async def set_capture_timeout(self, timeout_ms: int):
        """Set capture timeout in milliseconds.

        Args:
            timeout_ms: Timeout value in milliseconds

        Raises:
            ValueError: If timeout_ms is negative
        """
        await self._backend.set_capture_timeout(timeout_ms)
        return True

    async def get_capture_timeout(self) -> int:
        """Get current capture timeout in milliseconds.

        Returns:
            Current timeout value in milliseconds
        """
        return await self._backend.get_capture_timeout()

    async def set_roi(self, x: int, y: int, width: int, height: int):
        """Set the Region of Interest (ROI).

        Args:
            x: Top-left x pixel.
            y: Top-left y pixel.
            width: ROI width in pixels.
            height: ROI height in pixels.
        """
        await self._backend.set_ROI(x, y, width, height)

    async def get_roi(self) -> Dict[str, int]:
        """Get the current ROI.

        Returns:
            A dict with keys x, y, width, height.
        """
        return await self._backend.get_ROI()

    async def reset_roi(self):
        """Reset the ROI to full frame if supported."""
        await self._backend.reset_ROI()

    async def set_trigger_mode(self, mode: str):
        """Set the trigger mode.

        Args:
            mode: Trigger mode string (backend-specific).
        """
        async with self._lock:
            await self._backend.set_triggermode(mode)

    async def get_trigger_mode(self) -> str:
        """Get the current trigger mode.

        Returns:
            Trigger mode string.
        """
        return await self._backend.get_triggermode()

    async def set_pixel_format(self, format: str):
        """Set the output pixel format if supported.

        Args:
            format: Pixel format string.
        """
        await self._backend.set_pixel_format(format)

    async def get_pixel_format(self) -> str:
        """Get the current output pixel format.

        Returns:
            Pixel format string.
        """
        return await self._backend.get_current_pixel_format()

    async def get_available_pixel_formats(self) -> List[str]:
        """List supported pixel formats.

        Returns:
            A list of pixel format strings.
        """
        return await self._backend.get_pixel_format_range()

    async def set_white_balance(self, mode: str):
        """Set white balance mode.

        Args:
            mode: White balance mode (e.g., "auto", "manual").
        """
        async with self._lock:
            await self._backend.set_auto_wb_once(mode)

    async def get_white_balance(self) -> str:
        """Get the current white balance mode.

        Returns:
            White balance mode string.
        """
        return await self._backend.get_wb()

    async def get_available_white_balance_modes(self) -> List[str]:
        """List supported white balance modes.

        Returns:
            A list of mode strings.
        """
        return await self._backend.get_wb_range()

    async def set_image_enhancement(self, enabled: bool):
        """Enable or disable image enhancement pipeline.

        Args:
            enabled: True to enable, False to disable.
        """
        await self._backend.set_image_quality_enhancement(enabled)

    async def get_image_enhancement(self) -> bool:
        """Check whether image enhancement is enabled.

        Returns:
            True if enabled, otherwise False.
        """
        return await self._backend.get_image_quality_enhancement()

    async def save_config(self, path: str) -> bool:
        """Export current camera configuration to a file via backend.

        Args:
            path: Destination file path (backend-specific JSON).

        Returns:
            bool: True if export succeeds, raises exception on failure.
        """
        async with self._lock:
            await self._backend.export_config(path)
            return True

    async def load_config(self, path: str) -> bool:
        """Import camera configuration from a file via backend.

        Args:
            path: Configuration file path (backend-specific JSON).

        Returns:
            bool: True if import succeeds, raises exception on failure.
        """
        async with self._lock:
            await self._backend.import_config(path)
            return True

    async def check_connection(self):
        """Check whether the backend connection is healthy."""
        return await self._backend.check_connection()

    # GigE Network Performance Methods

    async def get_packet_size(self) -> int:
        """Get GigE packet size in bytes.

        Returns:
            Packet size in bytes (typically 1500 standard or 9000 jumbo frames).

        Raises:
            NotImplementedError: If camera doesn't support packet size control.
        """
        return await self._backend.get_packet_size()

    async def set_packet_size(self, size: int):
        """Set GigE packet size for network optimization.

        Args:
            size: Packet size in bytes (1476-16000).
        """
        async with self._lock:
            await self._backend.set_packet_size(size)

    async def get_inter_packet_delay(self) -> int:
        """Get inter-packet delay in ticks.

        Returns:
            Delay in ticks (0-65535, higher = slower transmission).

        Raises:
            NotImplementedError: If camera doesn't support inter-packet delay control.
        """
        return await self._backend.get_inter_packet_delay()

    async def set_inter_packet_delay(self, delay_ticks: int):
        """Set inter-packet delay for network traffic control.

        Args:
            delay_ticks: Delay in ticks (0-65535).
        """
        async with self._lock:
            await self._backend.set_inter_packet_delay(delay_ticks)

    async def get_bandwidth_limit(self) -> float:
        """Get bandwidth limit in Mbps.

        Returns:
            Bandwidth limit in Mbps, or unlimited if not set.

        Raises:
            NotImplementedError: If camera doesn't support bandwidth limiting.
        """
        return await self._backend.get_bandwidth_limit()

    async def set_bandwidth_limit(self, limit_mbps: Optional[float]):
        """Set bandwidth limit for GigE camera.

        Args:
            limit_mbps: Bandwidth limit in Mbps (None for unlimited).
        """
        async with self._lock:
            await self._backend.set_bandwidth_limit(limit_mbps)

    # Camera Capability and Range Query Methods

    async def get_trigger_modes(self) -> List[str]:
        """Get available trigger modes for the camera.

        Returns:
            List of supported trigger mode names. Returns default modes if backend doesn't support query.

        Raises:
            CameraError: If communication with camera fails.
        """
        try:
            return await self._backend.get_trigger_modes()
        except (NotImplementedError, AttributeError):
            # Return sensible defaults for cameras without trigger mode query capability
            return ["continuous", "triggered"]

    async def get_bandwidth_limit_range(self) -> Optional[Tuple[float, float]]:
        """Get bandwidth limit range for GigE cameras.

        Returns:
            Tuple of (min_mbps, max_mbps) for GigE cameras, None for non-GigE cameras.

        Raises:
            CameraError: If communication with camera fails.
        """
        try:
            range_list = await self._backend.get_bandwidth_limit_range()
            return (float(range_list[0]), float(range_list[1]))
        except (NotImplementedError, AttributeError):
            return None

    async def get_packet_size_range(self) -> Optional[Tuple[int, int]]:
        """Get packet size range for GigE cameras.

        Returns:
            Tuple of (min_bytes, max_bytes) for GigE cameras, None for non-GigE cameras.

        Raises:
            CameraError: If communication with camera fails.
        """
        try:
            range_list = await self._backend.get_packet_size_range()
            return (int(range_list[0]), int(range_list[1]))
        except (NotImplementedError, AttributeError):
            return None

    async def get_inter_packet_delay_range(self) -> Optional[Tuple[int, int]]:
        """Get inter-packet delay range for GigE cameras.

        Returns:
            Tuple of (min_ticks, max_ticks) for GigE cameras, None for non-GigE cameras.

        Raises:
            CameraError: If communication with camera fails.
        """
        try:
            range_list = await self._backend.get_inter_packet_delay_range()
            return (int(range_list[0]), int(range_list[1]))
        except (NotImplementedError, AttributeError):
            return None

    async def get_width_range(self) -> Optional[Tuple[int, int]]:
        """Get sensor width range for ROI configuration.

        Returns:
            Tuple of (min_width, max_width) if supported, None otherwise.

        Raises:
            CameraError: If communication with camera fails.
        """
        try:
            range_list = await self._backend.get_width_range()
            return (int(range_list[0]), int(range_list[1]))
        except (NotImplementedError, AttributeError):
            return None

    async def get_height_range(self) -> Optional[Tuple[int, int]]:
        """Get sensor height range for ROI configuration.

        Returns:
            Tuple of (min_height, max_height) if supported, None otherwise.

        Raises:
            CameraError: If communication with camera fails.
        """
        try:
            range_list = await self._backend.get_height_range()
            return (int(range_list[0]), int(range_list[1]))
        except (NotImplementedError, AttributeError):
            return None

    async def is_exposure_control_supported(self) -> bool:
        """Check if camera supports exposure control.

        Returns:
            True if exposure control is supported, False otherwise.
        """
        try:
            return await self._backend.is_exposure_control_supported()
        except (NotImplementedError, AttributeError):
            # Assume exposure control is supported unless explicitly not supported
            return True

    async def supports_feature(self, feature: str) -> bool:
        """Check if camera supports a specific feature.

        Args:
            feature: Feature name to check. Supported values:
                - 'bandwidth_limit': GigE bandwidth limiting
                - 'packet_size': GigE packet size control
                - 'inter_packet_delay': GigE inter-packet delay
                - 'exposure_control': Exposure time control
                - 'trigger_modes': Trigger mode support
                - 'width_range': Width range query
                - 'height_range': Height range query

        Returns:
            True if feature is supported and functional, False otherwise.
        """
        feature_checks = {
            "bandwidth_limit": self.get_bandwidth_limit_range,
            "packet_size": self.get_packet_size_range,
            "inter_packet_delay": self.get_inter_packet_delay_range,
            "width_range": self.get_width_range,
            "height_range": self.get_height_range,
            "exposure_control": self.is_exposure_control_supported,
            "trigger_modes": self.get_trigger_modes,
        }

        check_method = feature_checks.get(feature)
        if not check_method:
            return False

        try:
            result = await check_method()
            # For range methods, None means not supported
            # For boolean methods, False means not supported
            # For list methods, empty list means not supported
            if result is None:
                return False
            if isinstance(result, bool):
                return result
            if isinstance(result, (list, tuple)) and len(result) == 0:
                return False
            return True
        except Exception:
            return False

    async def get_sensor_info(self) -> Dict[str, Any]:
        """Get basic sensor information for diagnostics.

        Returns:
            A dict with fields: name, backend, device_name, connected.
        """
        return {
            "name": self._full_name,
            "backend": self._backend,
            "device_name": self._device_name,
            "connected": self.is_connected,
        }

    async def capture_hdr(
        self,
        save_path_pattern: Optional[str] = None,
        exposure_levels: Union[int, List[float]] = 3,
        exposure_multiplier: float = 2.0,
        return_images: bool = True,
        output_format: str = "pil",
    ) -> Dict[str, Any]:
        """Capture a bracketed HDR sequence and optionally return images.

        Args:
            save_path_pattern: Optional path pattern containing "{exposure}" placeholder.
            exposure_levels: Number of exposure steps (int) or explicit exposure values (List[float]).
            exposure_multiplier: Multiplier between consecutive exposure steps (used when exposure_levels is int).
            return_images: If True, returns list of captured images; otherwise returns success bool.
            output_format: Output format for returned images ("numpy" or "pil").

        Returns:
            Dictionary containing HDR capture results with keys:
            - success: bool - Whether capture succeeded
            - images: List[Any] - Captured images if return_images is True (format depends on output_format)
            - image_paths: List[str] - Saved file paths if save_path_pattern provided
            - exposure_levels: List[float] - Actual exposure values used
            - successful_captures: int - Number of successful captures

        Raises:
            CameraCaptureError: If no images could be captured successfully.
            ValueError: If output_format is not supported.
            ImportError: If PIL is required but not available.
        """
        # Validate output format early
        output_format = validate_output_format(output_format)

        async with self._lock:
            try:
                # Calculate or use provided exposure values
                if isinstance(exposure_levels, list):
                    # Use explicit exposure values
                    exposures = sorted(exposure_levels)
                    self.logger.info(f"Using explicit exposure values: {exposures}")
                else:
                    # Calculate exposure bracket based on count and multiplier
                    original_exposure = await self._backend.get_exposure()
                    exposure_range = await self._backend.get_exposure_range()
                    min_exposure, max_exposure = exposure_range[0], exposure_range[1]
                    base_exposure = original_exposure
                    exposures = []
                    for i in range(exposure_levels):
                        center_index = (exposure_levels - 1) / 2
                        multiplier = exposure_multiplier ** (i - center_index)
                        exposure = base_exposure * multiplier
                        exposure = max(min_exposure, min(max_exposure, exposure))
                        exposures.append(exposure)
                    exposures = sorted(list(set(exposures)))
                self.logger.info(
                    f"Starting HDR capture for camera '{self._full_name}' with {len(exposures)} exposure levels: {exposures}, output_format={output_format!r}"
                )
                captured_images = []
                image_paths = []
                successful_captures = 0
                for i, exposure in enumerate(exposures):
                    try:
                        await self._backend.set_exposure(exposure)

                        await asyncio.sleep(0.1)
                        save_path = None
                        if save_path_pattern:
                            save_path = save_path_pattern.format(exposure=int(exposure))
                        image = await self._backend.capture()
                        if image is not None:
                            if save_path and save_path.strip():
                                save_dir = os.path.dirname(save_path)
                                if save_dir:
                                    os.makedirs(save_dir, exist_ok=True)
                                cv2.imwrite(save_path, image)
                                image_paths.append(save_path)
                            if return_images:
                                # Convert image to requested format before adding to results
                                converted_image = convert_image_format(image, output_format)
                                captured_images.append(converted_image)
                            successful_captures += 1
                            self.logger.debug(
                                f"HDR capture {i + 1}/{len(exposures)} successful at exposure {exposure}μs"
                            )
                        else:
                            self.logger.warning(f"HDR capture {i + 1}/{len(exposures)} failed at exposure {exposure}μs")
                    except Exception as e:
                        self.logger.warning(
                            f"HDR capture {i + 1}/{len(exposures)} failed at exposure {exposure}μs: {e}"
                        )
                        continue
                try:
                    await self._backend.set_exposure(original_exposure)
                    self.logger.debug(f"Restored original exposure {original_exposure}μs")
                except Exception as e:
                    self.logger.warning(f"Failed to restore original exposure: {e}")
                if successful_captures == 0:
                    raise CameraCaptureError(
                        f"HDR capture failed - no successful captures from camera '{self._full_name}'"
                    )
                if successful_captures < len(exposures):
                    self.logger.warning(
                        f"HDR capture partially successful: {successful_captures}/{len(exposures)} captures succeeded"
                    )
                self.logger.info(
                    f"HDR capture completed for camera '{self._full_name}': {successful_captures}/{len(exposures)} successful"
                )

                # Return structured HDR result
                return {
                    "success": successful_captures > 0,
                    "images": captured_images if return_images else None,
                    "image_paths": image_paths if image_paths else None,
                    "exposure_levels": exposures,
                    "successful_captures": successful_captures,
                }
            except (CameraCaptureError, CameraConnectionError, CameraConfigurationError):
                raise
            except Exception as e:
                self.logger.error(f"HDR capture failed for camera '{self._full_name}': {e}")
                raise CameraCaptureError(f"HDR capture failed for camera '{self._full_name}': {str(e)}")

    # Backend-specific method delegation for GenICam compatibility
    async def get_ROI(self) -> Dict[str, int]:
        """Get Region of Interest (backend-specific method)."""
        async with self._lock:
            return await self._backend.get_ROI()

    async def set_ROI(self, x: int, y: int, width: int, height: int):
        """Set Region of Interest (backend-specific method)."""
        async with self._lock:
            return await self._backend.set_ROI(x, y, width, height)

    async def reset_ROI(self):
        """Reset Region of Interest (backend-specific method)."""
        async with self._lock:
            return await self._backend.reset_ROI()

    async def get_wb(self) -> str:
        """Get white balance mode (backend-specific method)."""
        async with self._lock:
            return await self._backend.get_wb()

    async def set_auto_wb_once(self, value: str):
        """Execute automatic white balance once (backend-specific method)."""
        async with self._lock:
            return await self._backend.set_auto_wb_once(value)

    async def get_wb_range(self) -> List[str]:
        """Get available white balance modes (backend-specific method)."""
        async with self._lock:
            return await self._backend.get_wb_range()

    async def export_config(self, config_path: str):
        """Export camera configuration (backend-specific method)."""
        async with self._lock:
            return await self._backend.export_config(config_path)

    async def import_config(self, config_path: str):
        """Import camera configuration (backend-specific method)."""
        async with self._lock:
            return await self._backend.import_config(config_path)

    async def close(self):
        """Close the camera and release resources."""
        async with self._lock:
            self.logger.info(f"Closing camera '{self._full_name}'")
            await self._backend.close()
            self.logger.debug(f"Camera '{self._full_name}' closed")
