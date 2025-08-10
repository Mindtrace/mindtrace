from __future__ import annotations

import asyncio
from concurrent.futures import Future
from typing import Any, Dict, List, Optional, Tuple, Union

from mindtrace.core import Mindtrace
from mindtrace.hardware.cameras.core.async_camera import AsyncCamera


class Camera(Mindtrace):
    """Synchronous facade over `AsyncCamera`.

    All operations are executed on a background event loop (owned by the sync CameraManager).
    """

    def __init__(self, async_camera: Optional[AsyncCamera] = None, loop: Optional[asyncio.AbstractEventLoop] = None, name: Optional[str] = None, **kwargs):
        """Create a sync Camera facade.

        If no async_camera/loop is supplied, a default OpenCV camera is created under the hood using a private 
        background loop, targeting ``OpenCV:opencv_camera_0``.
        """
        super().__init__(**kwargs)
        if async_camera is None or loop is None:
            # Build a private background loop and default OpenCV camera
            private_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(private_loop)
            async def _make() -> AsyncCamera:
                return await AsyncCamera.open(name)
            async_cam = private_loop.run_until_complete(_make())
            self._camera = async_cam
            self._loop = private_loop
        else:
            self._camera = async_camera
            self._loop = loop

    # Helpers
    def _submit(self, coro):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    def _call_in_loop(self, func, *args, **kwargs):
        result_future: Future = Future()

        def _run():
            try:
                result_future.set_result(func(*args, **kwargs))
            except Exception as e:
                result_future.set_exception(e)

        self._loop.call_soon_threadsafe(_run)
        return result_future.result()

    # Properties
    @property
    def name(self) -> str:
        """Full camera name including backend prefix.

        Returns:
            The full name in the form "Backend:device_name".
        """
        return self._camera.name

    @property
    def backend(self) -> str:
        """Backend identifier.

        Returns:
            The backend name (e.g., "Basler", "OpenCV").
        """
        return self._camera.backend

    @property
    def device_name(self) -> str:
        """Device identifier without backend prefix.

        Returns:
            The device name (e.g., camera serial or index).
        """
        return self._camera.device_name

    @property
    def is_connected(self) -> bool:
        """Connection status flag.

        Returns:
            True if the underlying backend is initialized/open, otherwise False.
        """
        return self._camera.is_connected

    # Sync methods delegating to async
    def capture(self, save_path: Optional[str] = None) -> Any:
        """Capture an image from the camera.

        Args:
            save_path: Optional path to save the captured image.

        Returns:
            The captured image (typically a numpy array in RGB/BGR depending on backend).

        Raises:
            CameraCaptureError: If capture fails after retries.
            CameraConnectionError: On connection issues during capture.
            CameraTimeoutError: If capture times out.
        """
        return self._submit(self._camera.capture(save_path))

    def configure(self, **settings) -> bool:
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
        return self._submit(self._camera.configure(**settings))

    def set_exposure(self, exposure: Union[int, float]) -> bool:
        """Set the camera exposure.

        Args:
            exposure: Exposure value appropriate for the backend.

        Returns:
            True on success, otherwise False.
        """
        return self._submit(self._camera.set_exposure(exposure))

    def get_exposure(self) -> float:
        """Get the current exposure value.

        Returns:
            The current exposure as a float.
        """
        return self._submit(self._camera.get_exposure())

    def get_exposure_range(self) -> Tuple[float, float]:
        """Get the valid exposure range.

        Returns:
            A tuple of (min_exposure, max_exposure).
        """
        return self._submit(self._camera.get_exposure_range())

    # Backend sync ops routed through loop for thread safety
    def set_gain(self, gain: Union[int, float]) -> bool:
        """Set the camera gain.

        Args:
            gain: Gain value to apply.

        Returns:
            True on success, otherwise False.
        """
        return self._call_in_loop(self._camera.set_gain, gain)

    def get_gain(self) -> float:
        """Get the current camera gain.

        Returns:
            The current gain as a float.
        """
        return self._call_in_loop(self._camera.get_gain)

    def get_gain_range(self) -> Tuple[float, float]:
        """Get the valid gain range.

        Returns:
            A tuple of (min_gain, max_gain).
        """
        return self._call_in_loop(self._camera.get_gain_range)

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
        return self._call_in_loop(self._camera.set_roi, x, y, width, height)

    def get_roi(self) -> Dict[str, int]:
        """Get the current ROI.

        Returns:
            A dict with keys x, y, width, height.
        """
        return self._call_in_loop(self._camera.get_roi)

    def reset_roi(self) -> bool:
        """Reset the ROI to full frame if supported.

        Returns:
            True on success, otherwise False.
        """
        return self._call_in_loop(self._camera.reset_roi)

    def set_trigger_mode(self, mode: str) -> bool:
        """Set the trigger mode.

        Args:
            mode: Trigger mode string (backend-specific).

        Returns:
            True on success, otherwise False.
        """
        return self._submit(self._camera.set_trigger_mode(mode))

    def get_trigger_mode(self) -> str:
        """Get the current trigger mode.

        Returns:
            Trigger mode string.
        """
        return self._submit(self._camera.get_trigger_mode())

    def set_pixel_format(self, format: str) -> bool:
        """Set the output pixel format if supported.

        Args:
            format: Pixel format string.

        Returns:
            True on success, otherwise False.
        """
        return self._call_in_loop(self._camera.set_pixel_format, format)

    def get_pixel_format(self) -> str:
        """Get the current output pixel format.

        Returns:
            Pixel format string.
        """
        return self._call_in_loop(self._camera.get_pixel_format)

    def get_available_pixel_formats(self) -> List[str]:
        """List supported pixel formats.

        Returns:
            A list of pixel format strings.
        """
        return self._call_in_loop(self._camera.get_available_pixel_formats)

    def set_white_balance(self, mode: str) -> bool:
        """Set white balance mode.

        Args:
            mode: White balance mode (e.g., "auto", "manual").

        Returns:
            True on success, otherwise False.
        """
        return self._submit(self._camera.set_white_balance(mode))

    def get_white_balance(self) -> str:
        """Get the current white balance mode.

        Returns:
            White balance mode string.
        """
        return self._submit(self._camera.get_white_balance())

    def get_available_white_balance_modes(self) -> List[str]:
        """List supported white balance modes.

        Returns:
            A list of mode strings.
        """
        return self._call_in_loop(self._camera.get_available_white_balance_modes)

    def set_image_enhancement(self, enabled: bool) -> bool:
        """Enable or disable image enhancement pipeline.

        Args:
            enabled: True to enable, False to disable.

        Returns:
            True on success, otherwise False.
        """
        return self._call_in_loop(self._camera.set_image_enhancement, enabled)

    def get_image_enhancement(self) -> bool:
        """Check whether image enhancement is enabled.

        Returns:
            True if enabled, otherwise False.
        """
        return self._call_in_loop(self._camera.get_image_enhancement)

    def save_config(self, path: str) -> bool:
        """Export current camera configuration to a file via backend.

        Args:
            path: Destination file path (backend-specific JSON).

        Returns:
            True on success, otherwise False.
        """
        return self._submit(self._camera.save_config(path))

    def load_config(self, path: str) -> bool:
        """Import camera configuration from a file via backend.

        Args:
            path: Configuration file path (backend-specific JSON).

        Returns:
            True on success, otherwise False.
        """
        return self._submit(self._camera.load_config(path))

    def check_connection(self) -> bool:
        """Check whether the backend connection is healthy.

        Returns:
            True if healthy, otherwise False.
        """
        return self._submit(self._camera.check_connection())

    def get_sensor_info(self) -> Dict[str, Any]:
        """Get basic sensor information for diagnostics.

        Returns:
            A dict with fields: name, backend, device_name, connected.
        """
        return self._submit(self._camera.get_sensor_info())

    def capture_hdr(
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
        return self._submit(
            self._camera.capture_hdr(
                save_path_pattern=save_path_pattern,
                exposure_levels=exposure_levels,
                exposure_multiplier=exposure_multiplier,
                return_images=return_images,
            )
        )

    def close(self) -> None:
        """Close the camera and release resources."""
        try:
            return self._submit(self._camera.close())
        finally:
            # If we own a private loop, shut it down
            try:
                if self._loop and self._loop.is_running() is False:
                    self._loop.stop()
            except Exception:
                pass
            try:
                if self._loop:
                    self._loop.close()
            except Exception:
                pass 
