"""Synchronous stereo camera interface.

This module provides a synchronous wrapper around AsyncStereoCamera, following
the same pattern as the regular Camera class.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Optional

from mindtrace.core import Mindtrace
from mindtrace.hardware.stereo_cameras.core.async_stereo_camera import AsyncStereoCamera
from mindtrace.hardware.stereo_cameras.core.models import (
    PointCloudData,
    StereoCalibrationData,
    StereoGrabResult,
)


class StereoCamera(Mindtrace):
    """Synchronous wrapper around AsyncStereoCamera.

    All operations are executed on a background event loop. This provides
    a simple synchronous API for stereo camera operations.
    """

    def __init__(
        self,
        async_camera: Optional[AsyncStereoCamera] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        name: Optional[str] = None,
        **kwargs,
    ):
        """Create a synchronous stereo camera wrapper.

        Args:
            async_camera: Existing AsyncStereoCamera instance
            loop: Event loop to use for async operations
            name: Camera identifier. Format: "BaslerStereoAce:serial_number"
                 If None, opens first available Stereo ace camera.
            **kwargs: Additional arguments passed to Mindtrace

        Examples:
            >>> # Simple usage - opens first available
            >>> camera = StereoCamera()

            >>> # Open specific camera
            >>> camera = StereoCamera(name="BaslerStereoAce:40644640")

            >>> # Use existing async camera
            >>> async_cam = await AsyncStereoCamera.open()
            >>> sync_cam = StereoCamera(async_camera=async_cam, loop=loop)
        """
        super().__init__(**kwargs)
        self._owns_loop_thread = False
        self._loop_thread: Optional[threading.Thread] = None

        if async_camera is None or loop is None:
            # Create background event loop in dedicated thread
            self._loop = asyncio.new_event_loop()

            def _run_loop():
                asyncio.set_event_loop(self._loop)
                self._loop.run_forever()

            self._loop_thread = threading.Thread(target=_run_loop, name="StereoCameraLoop", daemon=True)
            self._loop_thread.start()
            self._owns_loop_thread = True

            # Create AsyncStereoCamera on the running loop
            async def _make() -> AsyncStereoCamera:
                return await AsyncStereoCamera.open(name)

            self._backend = self._submit(_make())
        else:
            self._backend = async_camera
            self._loop = loop

    # Helpers
    def _submit(self, coro):
        """Submit coroutine to event loop and wait for result."""
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    # Properties
    @property
    def name(self) -> str:
        """Get camera name.

        Returns:
            Camera name in format "Backend:serial_number"
        """
        return self._backend.name

    @property
    def calibration(self) -> Optional[StereoCalibrationData]:
        """Get calibration data.

        Returns:
            StereoCalibrationData if available, None otherwise
        """
        return self._backend.calibration

    @property
    def is_open(self) -> bool:
        """Check if camera is open.

        Returns:
            True if camera is open, False otherwise
        """
        return self._backend.is_open

    # Lifecycle
    def close(self) -> None:
        """Close camera and release resources.

        Examples:
            >>> camera = StereoCamera()
            >>> # ... use camera ...
            >>> camera.close()
        """
        self._submit(self._backend.close())

        if self._owns_loop_thread and self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._loop_thread:
                self._loop_thread.join(timeout=2)

    # Capture operations
    def capture(
        self,
        enable_intensity: bool = True,
        enable_disparity: bool = True,
        calibrate_disparity: bool = True,
        timeout_ms: int = 20000,
    ) -> StereoGrabResult:
        """Capture multi-component stereo data.

        Args:
            enable_intensity: Whether to capture intensity image
            enable_disparity: Whether to capture disparity map
            calibrate_disparity: Whether to apply calibration to disparity
            timeout_ms: Capture timeout in milliseconds

        Returns:
            StereoGrabResult containing captured data

        Raises:
            CameraConnectionError: If camera not opened
            CameraCaptureError: If capture fails

        Examples:
            >>> camera = StereoCamera()
            >>> result = camera.capture()
            >>> print(f"Intensity: {result.intensity.shape}")
            >>> print(f"Disparity: {result.disparity.shape}")
            >>> camera.close()
        """
        return self._submit(
            self._backend.capture(
                enable_intensity=enable_intensity,
                enable_disparity=enable_disparity,
                calibrate_disparity=calibrate_disparity,
                timeout_ms=timeout_ms,
            )
        )

    def capture_point_cloud(
        self, include_colors: bool = True, remove_outliers: bool = False, downsample_factor: int = 1
    ) -> PointCloudData:
        """Capture and generate 3D point cloud.

        Args:
            include_colors: Whether to include color information from intensity
            remove_outliers: Whether to remove statistical outliers
            downsample_factor: Downsampling factor (1 = no downsampling)

        Returns:
            PointCloudData with 3D points and optional colors

        Raises:
            CameraConnectionError: If camera not opened
            CameraCaptureError: If capture fails
            CameraConfigurationError: If calibration not available

        Examples:
            >>> camera = StereoCamera()
            >>> point_cloud = camera.capture_point_cloud()
            >>> print(f"Points: {point_cloud.num_points}")
            >>> point_cloud.save_ply("output.ply")
            >>> camera.close()
        """
        return self._submit(
            self._backend.capture_point_cloud(
                include_colors=include_colors, remove_outliers=remove_outliers, downsample_factor=downsample_factor
            )
        )

    # Configuration
    def configure(self, **params) -> None:
        """Configure camera parameters.

        Args:
            **params: Parameter name-value pairs

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If configuration fails

        Examples:
            >>> camera = StereoCamera()
            >>> camera.configure(ExposureTime=15000, Gain=2.0)
            >>> camera.close()
        """
        self._submit(self._backend.configure(**params))

    def set_depth_range(self, min_depth: float, max_depth: float) -> None:
        """Set depth measurement range in meters.

        Args:
            min_depth: Minimum depth (e.g., 0.3 meters)
            max_depth: Maximum depth (e.g., 5.0 meters)

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> camera = StereoCamera()
            >>> camera.set_depth_range(0.5, 3.0)
            >>> camera.close()
        """
        self._submit(self._backend.set_depth_range(min_depth, max_depth))

    def set_illumination_mode(self, mode: str) -> None:
        """Set illumination mode.

        Args:
            mode: 'AlwaysActive' (low latency) or 'AlternateActive' (clean intensity)

        Raises:
            CameraConfigurationError: If invalid mode or configuration fails

        Examples:
            >>> camera = StereoCamera()
            >>> camera.set_illumination_mode("AlternateActive")
            >>> camera.close()
        """
        self._submit(self._backend.set_illumination_mode(mode))

    def set_binning(self, horizontal: int = 2, vertical: int = 2) -> None:
        """Enable binning for latency reduction.

        Binning reduces network transfer and computation.

        Args:
            horizontal: Horizontal binning factor (typically 2)
            vertical: Vertical binning factor (typically 2)

        Note:
            When using binning for low latency, consider also setting
            depth quality to "Full" using set_depth_quality("Full").

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> camera = StereoCamera()
            >>> camera.set_binning(2, 2)
            >>> camera.set_depth_quality("Full")  # Recommended for low latency
            >>> camera.close()
        """
        self._submit(self._backend.set_binning(horizontal, vertical))

    def set_depth_quality(self, quality: str) -> None:
        """Set depth quality level.

        Args:
            quality: Depth quality setting. Common values:
                    - "Full": Highest quality, recommended with binning
                    - "Normal": Standard quality
                    - "Low": Lower quality, faster processing

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> camera = StereoCamera()
            >>> # Low latency configuration
            >>> camera.set_binning(2, 2)
            >>> camera.set_depth_quality("Full")
            >>> camera.close()
        """
        self._submit(self._backend.set_depth_quality(quality))

    def set_pixel_format(self, format: str) -> None:
        """Set pixel format for intensity component.

        Args:
            format: Pixel format ("RGB8", "Mono8", etc.)

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If format not available or configuration fails

        Examples:
            >>> camera = StereoCamera()
            >>> camera.set_pixel_format("Mono8")  # Force grayscale
            >>> camera.close()
        """
        self._submit(self._backend.set_pixel_format(format))

    def set_exposure_time(self, microseconds: float) -> None:
        """Set exposure time in microseconds.

        Args:
            microseconds: Exposure time in microseconds (e.g., 5000 = 5ms)

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> camera = StereoCamera()
            >>> camera.set_exposure_time(5000)  # 5ms exposure
            >>> camera.close()
        """
        self._submit(self._backend.set_exposure_time(microseconds))

    def set_gain(self, gain: float) -> None:
        """Set camera gain.

        Args:
            gain: Gain value (typically 0.0 to 24.0, camera-dependent)

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> camera = StereoCamera()
            >>> camera.set_gain(2.0)
            >>> camera.close()
        """
        self._submit(self._backend.set_gain(gain))

    def get_exposure_time(self) -> float:
        """Get current exposure time in microseconds.

        Returns:
            Current exposure time in microseconds

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> camera = StereoCamera()
            >>> exposure = camera.get_exposure_time()
            >>> print(f"Exposure: {exposure}μs")
            >>> camera.close()
        """
        return self._submit(self._backend.get_exposure_time())

    def get_gain(self) -> float:
        """Get current camera gain.

        Returns:
            Current gain value

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> camera = StereoCamera()
            >>> gain = camera.get_gain()
            >>> print(f"Gain: {gain}")
            >>> camera.close()
        """
        return self._submit(self._backend.get_gain())

    def get_depth_quality(self) -> str:
        """Get current depth quality setting.

        Returns:
            Current depth quality level (e.g., "Full", "Normal", "Low")

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> camera = StereoCamera()
            >>> quality = camera.get_depth_quality()
            >>> print(f"Quality: {quality}")
            >>> camera.close()
        """
        return self._submit(self._backend.get_depth_quality())

    def get_pixel_format(self) -> str:
        """Get current pixel format.

        Returns:
            Current pixel format (e.g., "RGB8", "Mono8", "Coord3D_C16")

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> camera = StereoCamera()
            >>> format = camera.get_pixel_format()
            >>> print(f"Format: {format}")
            >>> camera.close()
        """
        return self._submit(self._backend.get_pixel_format())

    def get_binning(self) -> tuple[int, int]:
        """Get current binning settings.

        Returns:
            Tuple of (horizontal_binning, vertical_binning)

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> camera = StereoCamera()
            >>> h_bin, v_bin = camera.get_binning()
            >>> print(f"Binning: {h_bin}x{v_bin}")
            >>> camera.close()
        """
        return self._submit(self._backend.get_binning())

    def get_illumination_mode(self) -> str:
        """Get current illumination mode.

        Returns:
            Current illumination mode ("AlwaysActive" or "AlternateActive")

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> camera = StereoCamera()
            >>> mode = camera.get_illumination_mode()
            >>> print(f"Illumination: {mode}")
            >>> camera.close()
        """
        return self._submit(self._backend.get_illumination_mode())

    def get_depth_range(self) -> tuple[float, float]:
        """Get current depth measurement range in meters.

        Returns:
            Tuple of (min_depth, max_depth) in meters

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> camera = StereoCamera()
            >>> min_d, max_d = camera.get_depth_range()
            >>> print(f"Range: {min_d}m - {max_d}m")
            >>> camera.close()
        """
        return self._submit(self._backend.get_depth_range())

    def enable_software_trigger(self) -> None:
        """Enable software triggering mode.

        After enabling, use start_grabbing(), then execute_trigger() to capture frames on demand.

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> camera = StereoCamera()
            >>> camera.enable_software_trigger()
            >>> camera.start_grabbing()  # Start grabbing first!
            >>> for i in range(10):
            ...     camera.execute_trigger()
            ...     result = camera.capture()
            >>> camera.close()
        """
        self._submit(self._backend.enable_software_trigger())

    def start_grabbing(self) -> None:
        """Start grabbing frames.

        Must be called after enable_software_trigger() and before execute_trigger().

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> camera = StereoCamera()
            >>> camera.enable_software_trigger()
            >>> camera.start_grabbing()
            >>> for i in range(10):
            ...     camera.execute_trigger()
            ...     result = camera.capture()
            >>> camera.close()
        """
        self._submit(self._backend.start_grabbing())

    def execute_trigger(self) -> None:
        """Execute software trigger.

        Triggers a frame capture when in software trigger mode.
        Note: start_grabbing() must be called first after enabling software trigger.

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If trigger execution fails

        Examples:
            >>> camera = StereoCamera()
            >>> camera.enable_software_trigger()
            >>> camera.start_grabbing()
            >>> camera.execute_trigger()
            >>> result = camera.capture()
            >>> camera.close()
        """
        self._submit(self._backend.execute_trigger())

    # Context manager support
    def __enter__(self) -> "StereoCamera":
        """Context manager entry.

        Examples:
            >>> with StereoCamera() as camera:
            ...     result = camera.capture()
            ...     print(result.intensity.shape)
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def __repr__(self) -> str:
        """String representation."""
        status = "open" if self.is_open else "closed"
        return f"StereoCamera(name={self.name}, status={status})"
