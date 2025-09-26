from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Dict, List, Optional, Tuple, Union

from mindtrace.core import Mindtrace
from mindtrace.hardware.cameras.core.async_camera import AsyncCamera


class Camera(Mindtrace):
    """Synchronous facade over `AsyncCamera`.

    All operations are executed on a background event loop (owned by the sync CameraManager).
    """

    def __init__(
        self,
        async_camera: Optional[AsyncCamera] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        name: Optional[str] = None,
        **kwargs,
    ):
        """Create a sync Camera facade.

        If no async_camera/loop is supplied, a default OpenCV camera is created under the hood using a private
        background loop, targeting ``OpenCV:opencv_camera_0``.
        """
        super().__init__(**kwargs)
        self._owns_loop_thread = False
        self._loop_thread: Optional[threading.Thread] = None

        if async_camera is None or loop is None:
            # Create background event loop in a dedicated thread
            self._loop = asyncio.new_event_loop()

            def _run_loop():
                asyncio.set_event_loop(self._loop)
                self._loop.run_forever()

            self._loop_thread = threading.Thread(target=_run_loop, name="CameraLoop", daemon=True)
            self._loop_thread.start()
            self._owns_loop_thread = True

            # Create AsyncCamera on the running loop
            async def _make() -> AsyncCamera:
                return await AsyncCamera.open(name)

            self._backend = self._submit(_make())
        else:
            self._backend = async_camera
            self._loop = loop

    # Helpers
    def _submit(self, coro):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    def _call_in_loop(self, func, *args, **kwargs):
        """Execute a synchronous function in the event loop thread.

        This is a dormant utility method for future backend operations that require synchronous execution in the loop
        thread context. Currently unused but provides infrastructure for scenarios such as:
        - Backend hardware reset operations
        - Synchronous driver initialization
        - Thread-affine resource management
        - Hardware-specific sync operations (temperature sensors, diagnostics, etc.)

        Args:
            func: Synchronous function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            The result of func(*args, **kwargs) executed in the loop thread

        Raises:
            Any exception raised by func is propagated to the caller

        Note:
            Complements _submit() which handles coroutines. Use this for synchronous functions that must run in the
            event loop thread for thread safety.
        """
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
        return self._backend.name

    @property
    def backend_name(self) -> str:
        """Backend identifier string.

        Returns:
            The backend name (e.g., "Basler", "OpenCV").
        """
        return self._backend.backend_name

    @property
    def backend(self):
        """Backend instance implementing the camera SDK.

        Returns:
            The concrete backend object implementing `CameraBackend`.
        """
        return self._backend.backend

    @property
    def device_name(self) -> str:
        """Device identifier without backend prefix.

        Returns:
            The device name (e.g., camera serial or index).
        """
        return self._backend.device_name

    @property
    def is_connected(self) -> bool:
        """Connection status flag.

        Returns:
            True if the underlying backend is initialized/open, otherwise False.
        """
        return self._backend.is_connected

    # Sync methods delegating to async
    def capture(
        self, save_path: Optional[str] = None, upload_to_gcs: bool = False, output_format: str = "numpy"
    ) -> Any:
        """Capture an image from the camera.

        Args:
            save_path: Optional path to save the captured image.
            upload_to_gcs: Upload captured image to Google Cloud Storage.
            output_format: Output format for the returned image ("numpy" or "pil").

        Returns:
            The captured image as numpy array or PIL.Image depending on output_format.

        Raises:
            CameraCaptureError: If capture fails after retries.
            CameraConnectionError: On connection issues during capture.
            CameraTimeoutError: If capture times out.
            ValueError: If output_format is not supported.
            ImportError: If PIL is required but not available.
        """
        return self._submit(self._backend.capture(save_path, upload_to_gcs=upload_to_gcs, output_format=output_format))

    def configure(self, **settings):
        """Configure multiple camera settings atomically.

        Args:
            **settings: Supported keys include exposure, gain, roi=(x, y, w, h), trigger_mode, pixel_format,
                white_balance, image_enhancement.

        Raises:
            CameraConfigurationError: If a provided value is invalid for the backend.
            CameraConnectionError: If the camera cannot be configured.
        """
        self._submit(self._backend.configure(**settings))

    def set_exposure(self, exposure: Union[int, float]):
        """Set the camera exposure.

        Args:
            exposure: Exposure value appropriate for the backend.

        Raises:
            CameraConfigurationError: If exposure setting fails.
        """
        self._submit(self._backend.set_exposure(exposure))

    def get_exposure(self) -> float:
        """Get the current exposure value.

        Returns:
            The current exposure as a float.
        """
        return self._submit(self._backend.get_exposure())

    def get_exposure_range(self) -> Tuple[float, float]:
        """Get the valid exposure range.

        Returns:
            A tuple of (min_exposure, max_exposure).
        """
        return self._submit(self._backend.get_exposure_range())

    # Backend sync ops routed through loop for thread safety
    def set_gain(self, gain: Union[int, float]):
        """Set the camera gain.

        Args:
            gain: Gain value to apply.

        Raises:
            CameraConfigurationError: If gain setting fails.
        """
        self._submit(self._backend.set_gain(gain))

    def get_gain(self) -> float:
        """Get the current camera gain.

        Returns:
            The current gain as a float.
        """
        return self._submit(self._backend.get_gain())

    def get_gain_range(self) -> Tuple[float, float]:
        """Get the valid gain range.

        Returns:
            A tuple of (min_gain, max_gain).
        """
        return self._submit(self._backend.get_gain_range())

    def set_roi(self, x: int, y: int, width: int, height: int):
        """Set the Region of Interest (ROI).

        Args:
            x: Top-left x pixel.
            y: Top-left y pixel.
            width: ROI width in pixels.
            height: ROI height in pixels.

        Raises:
            CameraConfigurationError: If ROI setting fails.
        """
        self._submit(self._backend.set_roi(x, y, width, height))

    def get_roi(self) -> Dict[str, int]:
        """Get the current ROI.

        Returns:
            A dict with keys x, y, width, height.
        """
        return self._submit(self._backend.get_roi())

    def reset_roi(self):
        """Reset the ROI to full frame if supported."""
        self._submit(self._backend.reset_roi())

    def set_trigger_mode(self, mode: str) -> bool:
        """Set the trigger mode.

        Args:
            mode: Trigger mode string (backend-specific).

        Returns:
            True on success, otherwise False.
        """
        return self._submit(self._backend.set_trigger_mode(mode))

    def get_trigger_mode(self) -> str:
        """Get the current trigger mode.

        Returns:
            Trigger mode string.
        """
        return self._submit(self._backend.get_trigger_mode())

    def set_pixel_format(self, format: str):
        """Set the output pixel format if supported.

        Args:
            format: Pixel format string.

        Raises:
            CameraConfigurationError: If pixel format setting fails.
        """
        self._submit(self._backend.set_pixel_format(format))

    def get_pixel_format(self) -> str:
        """Get the current output pixel format.

        Returns:
            Pixel format string.
        """
        return self._submit(self._backend.get_pixel_format())

    def get_available_pixel_formats(self) -> List[str]:
        """List supported pixel formats.

        Returns:
            A list of pixel format strings.
        """
        return self._submit(self._backend.get_available_pixel_formats())

    def set_white_balance(self, mode: str):
        """Set white balance mode.

        Args:
            mode: White balance mode (e.g., "auto", "manual").

        Raises:
            CameraConfigurationError: If white balance setting fails.
        """
        self._submit(self._backend.set_white_balance(mode))

    def get_white_balance(self) -> str:
        """Get the current white balance mode.

        Returns:
            White balance mode string.
        """
        return self._submit(self._backend.get_white_balance())

    def get_available_white_balance_modes(self) -> List[str]:
        """List supported white balance modes.

        Returns:
            A list of mode strings.
        """
        return self._submit(self._backend.get_available_white_balance_modes())

    def set_image_enhancement(self, enabled: bool):
        """Enable or disable image enhancement pipeline.

        Args:
            enabled: True to enable, False to disable.

        Raises:
            CameraConfigurationError: If image enhancement setting fails.
        """
        self._submit(self._backend.set_image_enhancement(enabled))

    def get_image_enhancement(self) -> bool:
        """Check whether image enhancement is enabled.

        Returns:
            True if enabled, otherwise False.
        """
        return self._submit(self._backend.get_image_enhancement())

    def save_config(self, path: str):
        """Export current camera configuration to a file via backend.

        Args:
            path: Destination file path (backend-specific JSON).
        """
        self._submit(self._backend.save_config(path))

    def load_config(self, path: str):
        """Import camera configuration from a file via backend.

        Args:
            path: Configuration file path (backend-specific JSON).
        """
        self._submit(self._backend.load_config(path))

    def check_connection(self) -> bool:
        """Check whether the backend connection is healthy.

        Returns:
            True if healthy, otherwise False.
        """
        return self._submit(self._backend.check_connection())

    def get_sensor_info(self) -> Dict[str, Any]:
        """Get basic sensor information for diagnostics.

        Returns:
            A dict with fields: name, backend, device_name, connected.
        """
        return self._submit(self._backend.get_sensor_info())

    def capture_hdr(
        self,
        save_path_pattern: Optional[str] = None,
        exposure_levels: int = 3,
        exposure_multiplier: float = 2.0,
        return_images: bool = True,
        upload_to_gcs: bool = False,
        output_format: str = "numpy",
    ) -> Dict[str, Any]:
        """Capture a bracketed HDR sequence and optionally return images.

        Args:
            save_path_pattern: Optional path pattern containing "{exposure}" placeholder.
            exposure_levels: Number of exposure steps to capture.
            exposure_multiplier: Multiplier between consecutive exposure steps.
            return_images: If True, returns list of captured images; otherwise returns success bool.
            upload_to_gcs: Upload HDR sequence to Google Cloud Storage.
            output_format: Output format for returned images ("numpy" or "pil").

        Returns:
            Dictionary containing HDR capture results with keys:
            - success: bool - Whether capture succeeded
            - images: List[Any] - Captured images if return_images is True (format depends on output_format)
            - image_paths: List[str] - Saved file paths if save_path_pattern provided
            - exposure_levels: List[float] - Actual exposure values used
            - successful_captures: int - Number of successful captures
            - gcs_urls: List[str] - GCS URLs if uploaded

        Raises:
            CameraCaptureError: If no images could be captured successfully.
            ValueError: If output_format is not supported.
            ImportError: If PIL is required but not available.
        """
        return self._submit(
            self._backend.capture_hdr(
                save_path_pattern=save_path_pattern,
                exposure_levels=exposure_levels,
                exposure_multiplier=exposure_multiplier,
                return_images=return_images,
                upload_to_gcs=upload_to_gcs,
                output_format=output_format,
            )
        )

    def close(self) -> None:
        """Close the camera and release resources."""
        try:
            return self._submit(self._backend.close())
        finally:
            # If we own a private loop, shut it down
            if self._owns_loop_thread and self._loop is not None:
                try:
                    self._loop.call_soon_threadsafe(self._loop.stop)
                except Exception:
                    pass
                if self._loop_thread is not None:
                    try:
                        self._loop_thread.join(timeout=1.0)
                    except Exception:
                        pass
                try:
                    self._loop.close()
                except Exception:
                    pass

    # Context manager support
    def __enter__(self) -> "Camera":
        parent_enter = getattr(super(), "__enter__", None)
        if callable(parent_enter):
            res = parent_enter()
            return res if res is not None else self
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.close()
        finally:
            parent_exit = getattr(super(), "__exit__", None)
            if callable(parent_exit):
                return parent_exit(exc_type, exc, tb)
            return False
