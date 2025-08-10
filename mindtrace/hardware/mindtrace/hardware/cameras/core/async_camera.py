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
            elif backend_name.lower() in {"basler", "mockbasler", "mock_basler"}:
                from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import (
                    MockBaslerCameraBackend,
                )

                backend = MockBaslerCameraBackend(device_name)
            else:
                raise CameraInitializationError(
                    f"Unsupported backend '{backend_name}'. Try 'OpenCV:opencv_camera_0' or a mock Basler."
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

    async def capture(self, save_path: Optional[str] = None) -> Any:
        """Capture an image from the camera with retry logic.

        Args:
            save_path: Optional path to save the captured image (written as-is, typically RGB uint8).

        Returns:
            The captured image as a numpy array (RGB/BGR depending on backend) if successful.

        Raises:
            CameraCaptureError: If image capture ultimately fails after retries.
            CameraConnectionError: If the camera connection fails during capture.
            CameraTimeoutError: If the capture exceeds the configured timeout.
            RuntimeError: For unexpected errors after exhausting retries.
        """
        async with self._lock:
            retry_count = self._backend.retrieve_retry_count
            self.logger.debug(
                f"Starting capture for '{self._full_name}' with up to {retry_count} attempts, save_path={save_path!r}"
            )
            for attempt in range(retry_count):
                try:
                    success, image = await self._backend.capture()
                    if success and image is not None:
                        if save_path:
                            dirname = os.path.dirname(save_path)
                            if dirname:
                                os.makedirs(dirname, exist_ok=True)
                            cv2.imwrite(save_path, image)
                            self.logger.debug(f"Saved captured image to '{save_path}'")
                        self.logger.debug(
                            f"Capture successful for '{self._full_name}' on attempt {attempt + 1}/{retry_count}"
                        )
                        return image
                    raise CameraCaptureError(f"Capture returned failure for camera '{self._full_name}'")
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

    async def configure(self, **settings) -> bool:
        """Configure multiple camera settings atomically.

        Args:
            **settings: Supported keys include exposure, gain, roi=(x, y, w, h), trigger_mode,
                pixel_format, white_balance, image_enhancement.

        Returns:
            True if all settings were applied successfully, otherwise False.

        Raises:
            CameraConfigurationError: If a provided value is invalid for the backend.
            CameraConnectionError: If the camera cannot be configured.
        """
        async with self._lock:
            self.logger.debug(f"Configuring camera '{self._full_name}' with settings: {settings}")
            success = True
            if "exposure" in settings:
                success &= await self._backend.set_exposure(settings["exposure"])
            if "gain" in settings:
                success &= self._backend.set_gain(settings["gain"])
            if "roi" in settings:
                x, y, w, h = settings["roi"]
                success &= self._backend.set_ROI(x, y, w, h)
            if "trigger_mode" in settings:
                success &= await self._backend.set_triggermode(settings["trigger_mode"])
            if "pixel_format" in settings:
                success &= self._backend.set_pixel_format(settings["pixel_format"])
            if "white_balance" in settings:
                success &= await self._backend.set_auto_wb_once(settings["white_balance"])
            if "image_enhancement" in settings:
                success &= self._backend.set_image_quality_enhancement(settings["image_enhancement"])
            self.logger.debug(
                f"Configuration {'succeeded' if success else 'had failures'} for camera '{self._full_name}'"
            )
            return success

    async def set_exposure(self, exposure: Union[int, float]) -> bool:
        """Set the camera exposure.

        Args:
            exposure: Exposure value appropriate for the backend.

        Returns:
            True on success, otherwise False.
        """
        async with self._lock:
            return await self._backend.set_exposure(exposure)

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

    def set_gain(self, gain: Union[int, float]) -> bool:
        """Set the camera gain.

        Args:
            gain: Gain value to apply.

        Returns:
            True on success, otherwise False.
        """
        return self._backend.set_gain(gain)

    def get_gain(self) -> float:
        """Get the current camera gain.

        Returns:
            The current gain as a float.
        """
        return self._backend.get_gain()

    def get_gain_range(self) -> Tuple[float, float]:
        """Get the valid gain range.

        Returns:
            A tuple of (min_gain, max_gain).
        """
        range_list = self._backend.get_gain_range()
        return range_list[0], range_list[1]

    def set_roi(self, x: int, y: int, width: int, height: int) -> bool:
        """Set the Region of Interest (ROI).

        Args:
            x: Top-left x pixel.
            y: Top-left y pixel.
            width: ROI width in pixels.
            height: ROI height in pixels.

        Returns:
            True on success, otherwise False.
        """
        return self._backend.set_ROI(x, y, width, height)

    def get_roi(self) -> Dict[str, int]:
        """Get the current ROI.

        Returns:
            A dict with keys x, y, width, height.
        """
        return self._backend.get_ROI()

    def reset_roi(self) -> bool:
        """Reset the ROI to full frame if supported.

        Returns:
            True on success, otherwise False.
        """
        return self._backend.reset_ROI()

    async def set_trigger_mode(self, mode: str) -> bool:
        """Set the trigger mode.

        Args:
            mode: Trigger mode string (backend-specific).

        Returns:
            True on success, otherwise False.
        """
        async with self._lock:
            return await self._backend.set_triggermode(mode)

    async def get_trigger_mode(self) -> str:
        """Get the current trigger mode.

        Returns:
            Trigger mode string.
        """
        return await self._backend.get_triggermode()

    def set_pixel_format(self, format: str) -> bool:
        """Set the output pixel format if supported.

        Args:
            format: Pixel format string.

        Returns:
            True on success, otherwise False.
        """
        return self._backend.set_pixel_format(format)

    def get_pixel_format(self) -> str:
        """Get the current output pixel format.

        Returns:
            Pixel format string.
        """
        return self._backend.get_current_pixel_format()

    def get_available_pixel_formats(self) -> List[str]:
        """List supported pixel formats.

        Returns:
            A list of pixel format strings.
        """
        return self._backend.get_pixel_format_range()

    async def set_white_balance(self, mode: str) -> bool:
        """Set white balance mode.

        Args:
            mode: White balance mode (e.g., "auto", "manual").

        Returns:
            True on success, otherwise False.
        """
        async with self._lock:
            return await self._backend.set_auto_wb_once(mode)

    async def get_white_balance(self) -> str:
        """Get the current white balance mode.

        Returns:
            White balance mode string.
        """
        return await self._backend.get_wb()

    def get_available_white_balance_modes(self) -> List[str]:
        """List supported white balance modes.

        Returns:
            A list of mode strings.
        """
        return self._backend.get_wb_range()

    def set_image_enhancement(self, enabled: bool) -> bool:
        """Enable or disable image enhancement pipeline.

        Args:
            enabled: True to enable, False to disable.

        Returns:
            True on success, otherwise False.
        """
        return self._backend.set_image_quality_enhancement(enabled)

    def get_image_enhancement(self) -> bool:
        """Check whether image enhancement is enabled.

        Returns:
            True if enabled, otherwise False.
        """
        return self._backend.get_image_quality_enhancement()

    async def save_config(self, path: str) -> bool:
        """Export current camera configuration to a file via backend.

        Args:
            path: Destination file path (backend-specific JSON).

        Returns:
            True on success, otherwise False.
        """
        async with self._lock:
            return await self._backend.export_config(path)

    async def load_config(self, path: str) -> bool:
        """Import camera configuration from a file via backend.

        Args:
            path: Configuration file path (backend-specific JSON).

        Returns:
            True on success, otherwise False.
        """
        async with self._lock:
            return await self._backend.import_config(path)

    async def check_connection(self) -> bool:
        """Check whether the backend connection is healthy.

        Returns:
            True if healthy, otherwise False.
        """
        return await self._backend.check_connection()

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
        exposure_levels: int = 3,
        exposure_multiplier: float = 2.0,
        return_images: bool = True,
    ) -> Union[List[Any], bool]:
        """Capture a bracketed HDR sequence and optionally return images.

        Args:
            save_path_pattern: Optional path pattern containing "{exposure}" placeholder.
            exposure_levels: Number of exposure steps to capture.
            exposure_multiplier: Multiplier between consecutive exposure steps.
            return_images: If True, returns list of captured images; otherwise returns success bool.

        Returns:
            List of images if return_images is True, otherwise a boolean success flag.

        Raises:
            CameraCaptureError: If no images could be captured successfully.
        """
        async with self._lock:
            try:
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
                    f"Starting HDR capture for camera '{self._full_name}' with {len(exposures)} exposure levels: {exposures}"
                )
                captured_images = []
                successful_captures = 0
                for i, exposure in enumerate(exposures):
                    try:
                        success = await self._backend.set_exposure(exposure)
                        if not success:
                            self.logger.warning(
                                f"Failed to set exposure {exposure} for HDR capture {i + 1}/{len(exposures)}"
                            )
                            continue
                        await asyncio.sleep(0.1)
                        save_path = None
                        if save_path_pattern:
                            save_path = save_path_pattern.format(exposure=int(exposure))
                        success, image = await self._backend.capture()
                        if success and image is not None:
                            if save_path and save_path.strip():
                                save_dir = os.path.dirname(save_path)
                                if save_dir:
                                    os.makedirs(save_dir, exist_ok=True)
                                cv2.imwrite(save_path, image)
                            if return_images:
                                captured_images.append(image)
                            successful_captures += 1
                            self.logger.debug(
                                f"HDR capture {i + 1}/{len(exposures)} successful at exposure {exposure}μs"
                            )
                        else:
                            self.logger.warning(
                                f"HDR capture {i + 1}/{len(exposures)} failed at exposure {exposure}μs"
                            )
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
                if return_images:
                    return captured_images
                else:
                    return successful_captures == len(exposures)
            except (CameraCaptureError, CameraConnectionError, CameraConfigurationError):
                raise
            except Exception as e:
                self.logger.error(f"HDR capture failed for camera '{self._full_name}': {e}")
                raise CameraCaptureError(f"HDR capture failed for camera '{self._full_name}': {str(e)}")

    async def close(self):
        """Close the camera and release resources."""
        async with self._lock:
            self.logger.info(f"Closing camera '{self._full_name}'")
            await self._backend.close()
            self.logger.debug(f"Camera '{self._full_name}' closed") 