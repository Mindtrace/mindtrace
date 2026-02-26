"""Abstract base class for stereo camera backends.

This module defines the async interface that all stereo camera backends must implement
to ensure consistent behavior across different stereo camera types and manufacturers.

Following the same architectural pattern as CameraBackend for consistency.
"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from mindtrace.core import MindtraceABC
from mindtrace.hardware.core.exceptions import (
    CameraConnectionError,
    CameraTimeoutError,
    HardwareOperationError,
)
from mindtrace.hardware.stereo_cameras.core.models import (
    PointCloudData,
    StereoCalibrationData,
    StereoGrabResult,
)

T = TypeVar("T")


class StereoCameraBackend(MindtraceABC):
    """Abstract base class for all stereo camera implementations.

    This class defines the async interface that all stereo camera backends must implement
    to ensure consistent behavior across different stereo camera types and manufacturers.
    Uses async-first design consistent with CameraBackend and PLC backends.

    Attributes:
        serial_number: Unique identifier for the camera
        calibration: Factory calibration parameters
        is_open: Camera connection status

    Implementation Guide:
        - Offload blocking SDK calls from async methods:
          Use ``asyncio.to_thread`` for simple cases or ``loop.run_in_executor`` with a per-instance
          single-thread executor when the SDK requires thread affinity.
        - Thread affinity:
          Many vendor SDKs are safest when all calls originate from one OS thread. Prefer a dedicated
          single-thread executor created during ``initialize()`` and shut down in ``close()`` to
          serialize SDK access without blocking the event loop.
        - Timeouts and cancellation:
          Prefer SDK-native timeouts where available. Otherwise, wrap awaited futures with
          ``asyncio.wait_for`` to bound runtime. Note that cancelling an await does not stop the
          underlying thread function; design idempotent/short tasks when possible.
        - Event loop hygiene:
          Never call blocking functions (e.g., long SDK calls, ``time.sleep``) directly in async
          methods. Replace sleeps with ``await asyncio.sleep`` or run blocking work in the executor.
        - Sync helpers:
          Lightweight getters/setters that do not touch hardware may remain synchronous. If a
          "getter" calls into the SDK, route it through the executor to avoid blocking.
        - Errors:
          Map SDK-specific exceptions to the domain exceptions in ``mindtrace.hardware.core.exceptions``
          with clear, contextual messages.
        - Cleanup:
          Ensure resources (device handles, executors, buffers) are released in ``close()``.
          ``__aenter__/__aexit__`` already call ``initialize``/``close`` for async contexts.

    Example Implementation:
        >>> class MyStereoCameraBackend(StereoCameraBackend):
        ...     async def initialize(self) -> bool:
        ...         # Connect to camera, load calibration
        ...         return True
        ...
        ...     async def capture(self, ...) -> StereoGrabResult:
        ...         # Capture stereo data
        ...         return StereoGrabResult(...)
    """

    def __init__(
        self,
        serial_number: Optional[str] = None,
        op_timeout_s: float = 30.0,
    ):
        """Initialize base stereo camera backend.

        Args:
            serial_number: Unique identifier for the camera (auto-discovered if None)
            op_timeout_s: Default timeout in seconds for SDK operations
        """
        super().__init__()

        self.serial_number = serial_number
        self._op_timeout_s = op_timeout_s
        self._is_open = False
        self._calibration: Optional[StereoCalibrationData] = None

        self.logger.debug(
            f"StereoCameraBackend base initialized: serial_number={self.serial_number}, "
            f"op_timeout_s={self._op_timeout_s}"
        )

    async def _run_blocking(
        self, func: Callable[..., T], *args: Any, timeout: Optional[float] = None, **kwargs: Any
    ) -> T:
        """Run a blocking SDK call in threadpool with timeout.

        This is a utility method that subclasses can use to safely execute blocking
        SDK calls without blocking the event loop.

        Args:
            func: The blocking function to call
            *args: Positional arguments for the function
            timeout: Optional timeout override (uses self._op_timeout_s if not provided)
            **kwargs: Keyword arguments for the function

        Returns:
            The result of the function call

        Raises:
            CameraTimeoutError: If operation times out
            HardwareOperationError: If operation fails
        """
        effective_timeout = timeout if timeout is not None else self._op_timeout_s
        try:
            return await asyncio.wait_for(asyncio.to_thread(func, *args, **kwargs), timeout=effective_timeout)
        except asyncio.TimeoutError as e:
            raise CameraTimeoutError(f"Stereo camera operation timed out after {effective_timeout:.2f}s") from e
        except Exception as e:
            # Re-raise domain exceptions as-is
            if isinstance(e, (CameraTimeoutError, HardwareOperationError)):
                raise
            raise HardwareOperationError(f"Stereo camera operation failed: {e}") from e

    # =========================================================================
    # Abstract Methods - Must be implemented by subclasses
    # =========================================================================

    @staticmethod
    @abstractmethod
    def discover() -> List[str]:
        """Discover available stereo cameras.

        Returns:
            List of serial numbers or identifiers for available cameras

        Raises:
            SDKNotAvailableError: If required SDK is not available
        """
        raise NotImplementedError

    @classmethod
    async def discover_async(cls) -> List[str]:
        """Async wrapper for discover() - runs discovery in threadpool.

        Default implementation runs discover() in a thread. Override if your SDK
        provides native async discovery.

        Returns:
            List of serial numbers for available cameras
        """
        return await asyncio.to_thread(cls.discover)

    @staticmethod
    def discover_detailed() -> List[Dict[str, str]]:
        """Discover cameras with detailed information.

        Returns:
            List of dictionaries containing camera information (serial_number, model, etc.)
        """
        # Default implementation returns basic info from discover()
        return [{"serial_number": sn} for sn in StereoCameraBackend.discover()]

    @classmethod
    async def discover_detailed_async(cls) -> List[Dict[str, str]]:
        """Async wrapper for discover_detailed()."""
        return await asyncio.to_thread(cls.discover_detailed)

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize camera connection and load calibration.

        This method should:
        1. Connect to the camera hardware
        2. Load factory calibration parameters
        3. Apply default configuration

        Returns:
            True if initialization successful

        Raises:
            CameraNotFoundError: If camera cannot be found
            CameraInitializationError: If camera initialization fails
            CameraConnectionError: If camera connection fails
        """
        raise NotImplementedError

    @abstractmethod
    async def capture(
        self,
        timeout_ms: int = 20000,
        enable_intensity: bool = True,
        enable_disparity: bool = True,
        calibrate_disparity: bool = True,
    ) -> StereoGrabResult:
        """Capture stereo data with multiple components.

        Args:
            timeout_ms: Capture timeout in milliseconds
            enable_intensity: Whether to capture intensity/texture image
            enable_disparity: Whether to capture disparity map
            calibrate_disparity: Whether to apply calibration to raw disparity

        Returns:
            StereoGrabResult containing captured data

        Raises:
            CameraConnectionError: If camera not opened
            CameraCaptureError: If capture fails
            CameraTimeoutError: If capture times out
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close camera and release resources.

        This method should:
        1. Stop any ongoing acquisition
        2. Release hardware handles
        3. Clean up executors/threads if used
        """
        raise NotImplementedError

    # =========================================================================
    # Abstract Properties - Must be implemented by subclasses
    # =========================================================================

    @property
    @abstractmethod
    def name(self) -> str:
        """Get camera name in format 'BackendType:serial_number'."""
        raise NotImplementedError

    @property
    def is_open(self) -> bool:
        """Check if camera is open."""
        return self._is_open

    @property
    def calibration(self) -> Optional[StereoCalibrationData]:
        """Get calibration data."""
        return self._calibration

    # =========================================================================
    # Optional Methods - Default implementations provided
    # =========================================================================

    async def get_calibration(self) -> StereoCalibrationData:
        """Get factory calibration parameters from camera.

        Returns:
            StereoCalibrationData with factory calibration

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If calibration cannot be read
        """
        if self._calibration is None:
            raise CameraConnectionError("Calibration not loaded - ensure camera is initialized")
        return self._calibration

    async def capture_point_cloud(
        self,
        include_colors: bool = True,
        downsample_factor: int = 1,
    ) -> PointCloudData:
        """Capture and generate 3D point cloud.

        Default implementation captures stereo data and generates point cloud
        using calibration parameters. Override for backend-specific optimization.

        Args:
            include_colors: Whether to include color information
            downsample_factor: Downsampling factor (1 = no downsampling)

        Returns:
            PointCloudData with 3D points and optional attributes

        Raises:
            CameraConnectionError: If camera not opened
            CameraCaptureError: If capture fails
            CameraConfigurationError: If calibration not available
        """
        self.logger.warning(
            f"capture_point_cloud not optimized for {self.__class__.__name__}, using default implementation"
        )
        raise NotImplementedError(f"capture_point_cloud not implemented for {self.__class__.__name__}")

    async def configure(self, **params) -> None:
        """Configure camera parameters.

        Args:
            **params: Parameter name-value pairs

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If configuration fails
        """
        self.logger.warning(f"configure not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"configure not supported by {self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # Exposure and Gain
    # -------------------------------------------------------------------------

    async def set_exposure_time(self, microseconds: float) -> None:
        """Set exposure time in microseconds."""
        self.logger.warning(f"set_exposure_time not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"set_exposure_time not supported by {self.__class__.__name__}")

    async def get_exposure_time(self) -> float:
        """Get current exposure time in microseconds."""
        self.logger.warning(f"get_exposure_time not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"get_exposure_time not supported by {self.__class__.__name__}")

    async def set_gain(self, gain: float) -> None:
        """Set camera gain."""
        self.logger.warning(f"set_gain not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"set_gain not supported by {self.__class__.__name__}")

    async def get_gain(self) -> float:
        """Get current camera gain."""
        self.logger.warning(f"get_gain not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"get_gain not supported by {self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # Depth Configuration (Stereo-specific)
    # -------------------------------------------------------------------------

    async def set_depth_range(self, min_depth: float, max_depth: float) -> None:
        """Set depth measurement range in meters."""
        self.logger.warning(f"set_depth_range not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"set_depth_range not supported by {self.__class__.__name__}")

    async def get_depth_range(self) -> Tuple[float, float]:
        """Get current depth measurement range in meters."""
        self.logger.warning(f"get_depth_range not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"get_depth_range not supported by {self.__class__.__name__}")

    async def set_depth_quality(self, quality: str) -> None:
        """Set depth quality level (e.g., 'Full', 'Normal', 'Low')."""
        self.logger.warning(f"set_depth_quality not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"set_depth_quality not supported by {self.__class__.__name__}")

    async def get_depth_quality(self) -> str:
        """Get current depth quality level."""
        self.logger.warning(f"get_depth_quality not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"get_depth_quality not supported by {self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # Illumination and Binning (Stereo-specific)
    # -------------------------------------------------------------------------

    async def set_illumination_mode(self, mode: str) -> None:
        """Set illumination mode ('AlwaysActive' or 'AlternateActive')."""
        self.logger.warning(f"set_illumination_mode not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"set_illumination_mode not supported by {self.__class__.__name__}")

    async def get_illumination_mode(self) -> str:
        """Get current illumination mode."""
        self.logger.warning(f"get_illumination_mode not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"get_illumination_mode not supported by {self.__class__.__name__}")

    async def set_binning(self, horizontal: int = 2, vertical: int = 2) -> None:
        """Enable binning for latency reduction."""
        self.logger.warning(f"set_binning not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"set_binning not supported by {self.__class__.__name__}")

    async def get_binning(self) -> Tuple[int, int]:
        """Get current binning settings (horizontal, vertical)."""
        self.logger.warning(f"get_binning not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"get_binning not supported by {self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # Pixel Format
    # -------------------------------------------------------------------------

    async def set_pixel_format(self, format: str) -> None:
        """Set pixel format for intensity component."""
        self.logger.warning(f"set_pixel_format not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"set_pixel_format not supported by {self.__class__.__name__}")

    async def get_pixel_format(self) -> str:
        """Get current pixel format."""
        self.logger.warning(f"get_pixel_format not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"get_pixel_format not supported by {self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # Trigger Control
    # -------------------------------------------------------------------------

    async def set_trigger_mode(self, mode: str) -> None:
        """Set trigger mode ('continuous' or 'trigger')."""
        self.logger.warning(f"set_trigger_mode not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"set_trigger_mode not supported by {self.__class__.__name__}")

    async def get_trigger_mode(self) -> str:
        """Get current trigger mode."""
        self.logger.warning(f"get_trigger_mode not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"get_trigger_mode not supported by {self.__class__.__name__}")

    async def get_trigger_modes(self) -> List[str]:
        """Get available trigger modes."""
        return ["continuous", "trigger"]

    async def start_grabbing(self) -> None:
        """Start grabbing frames (required before execute_trigger in trigger mode)."""
        self.logger.warning(f"start_grabbing not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"start_grabbing not supported by {self.__class__.__name__}")

    async def execute_trigger(self) -> None:
        """Execute software trigger."""
        self.logger.warning(f"execute_trigger not implemented for {self.__class__.__name__}")
        raise NotImplementedError(f"execute_trigger not supported by {self.__class__.__name__}")

    # =========================================================================
    # Context Manager Support
    # =========================================================================

    async def __aenter__(self) -> "StereoCameraBackend":
        """Async context manager entry - initializes the camera."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - closes the camera."""
        await self.close()

    # =========================================================================
    # Lifecycle Helpers
    # =========================================================================

    def __del__(self) -> None:
        """Destructor - warn if camera not properly closed."""
        try:
            if hasattr(self, "_is_open") and self._is_open:
                if hasattr(self, "logger"):
                    self.logger.warning(
                        f"StereoCameraBackend '{getattr(self, 'serial_number', 'unknown')}' "
                        f"destroyed without proper cleanup. Use 'async with camera' or call "
                        f"'await camera.close()' for proper cleanup."
                    )
        except Exception:
            pass

    def __repr__(self) -> str:
        """String representation."""
        status = "open" if self._is_open else "closed"
        return f"{self.__class__.__name__}(serial_number={self.serial_number}, status={status})"
