"""Abstract base class for 3D scanner backends.

This module defines the async interface that all 3D scanner backends must implement
to ensure consistent behavior across different scanner types and manufacturers
(structured light, time-of-flight, LiDAR, etc.).

Following the same architectural pattern as CameraBackend and StereoCameraBackend
for consistency across the hardware module.
"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from typing import Any, Callable, Dict, List, Optional, TypeVar

from mindtrace.core import MindtraceABC
from mindtrace.hardware.core.exceptions import (
    CameraTimeoutError,
    HardwareOperationError,
)
from mindtrace.hardware.scanners_3d.core.models import (
    PointCloudData,
    ScannerCapabilities,
    ScannerConfiguration,
    ScanResult,
)

T = TypeVar("T")


class Scanner3DBackend(MindtraceABC):
    """Abstract base class for all 3D scanner implementations.

    This class defines the async interface that all 3D scanner backends must implement
    to ensure consistent behavior across different scanner types and manufacturers.
    Supports structured light (Photoneo, Ensenso), time-of-flight, LiDAR, and other
    3D scanning technologies.

    Uses async-first design consistent with CameraBackend and StereoCameraBackend.

    Attributes:
        serial_number: Unique identifier for the scanner
        is_open: Scanner connection status

    Implementation Guide:
        - Offload blocking SDK calls from async methods:
          Use ``asyncio.to_thread`` for simple cases or ``loop.run_in_executor`` with a per-instance
          single-thread executor when the SDK requires thread affinity.
        - Thread affinity:
          Many vendor SDKs (e.g., Harvesters/GenTL) are safest when all calls originate from one
          OS thread. Prefer a dedicated single-thread executor created during ``initialize()``
          and shut down in ``close()`` to serialize SDK access without blocking the event loop.
        - Timeouts and cancellation:
          Prefer SDK-native timeouts where available. Otherwise, wrap awaited futures with
          ``asyncio.wait_for`` to bound runtime.
        - Event loop hygiene:
          Never call blocking functions directly in async methods. Replace sleeps with
          ``await asyncio.sleep`` or run blocking work in the executor.
        - Errors:
          Map SDK-specific exceptions to domain exceptions in ``mindtrace.hardware.core.exceptions``
          with clear, contextual messages.
        - Cleanup:
          Ensure resources (device handles, Harvester instances, buffers) are released in ``close()``.

    Supported Scanner Types:
        - Structured light: Photoneo PhoXi, Ensenso, Zivid
        - Time-of-flight: Various ToF sensors
        - LiDAR: Point cloud scanners
        - Other 3D sensing technologies

    Example Implementation:
        >>> class MyScanner3DBackend(Scanner3DBackend):
        ...     async def initialize(self) -> bool:
        ...         # Connect to scanner
        ...         return True
        ...
        ...     async def capture(self, ...) -> ScanResult:
        ...         # Capture 3D scan data
        ...         return ScanResult(...)
    """

    def __init__(
        self,
        serial_number: Optional[str] = None,
        op_timeout_s: float = 30.0,
    ):
        """Initialize base 3D scanner backend.

        Args:
            serial_number: Unique identifier for the scanner (auto-discovered if None)
            op_timeout_s: Default timeout in seconds for SDK operations
        """
        super().__init__()

        self.serial_number = serial_number
        self._op_timeout_s = op_timeout_s
        self._is_open = False
        self._device_info: Optional[Dict[str, Any]] = None
        self._frame_counter = 0

        self.logger.debug(
            f"Scanner3DBackend base initialized: serial_number={self.serial_number}, op_timeout_s={self._op_timeout_s}"
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
            raise CameraTimeoutError(f"3D scanner operation timed out after {effective_timeout:.2f}s") from e
        except Exception as e:
            # Re-raise domain exceptions as-is
            if isinstance(e, (CameraTimeoutError, HardwareOperationError)):
                raise
            raise HardwareOperationError(f"3D scanner operation failed: {e}") from e

    # =========================================================================
    # Abstract Methods - Must be implemented by subclasses
    # =========================================================================

    @staticmethod
    @abstractmethod
    def discover() -> List[str]:
        """Discover available 3D scanners.

        Returns:
            List of serial numbers or identifiers for available scanners

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
            List of serial numbers for available scanners
        """
        return await asyncio.to_thread(cls.discover)

    @staticmethod
    def discover_detailed() -> List[Dict[str, str]]:
        """Discover scanners with detailed information.

        Returns:
            List of dictionaries containing scanner information:
            - serial_number: Device serial number
            - model: Model name
            - vendor: Manufacturer name
            - Additional device-specific fields
        """
        # Default implementation returns basic info from discover()
        return [{"serial_number": sn} for sn in Scanner3DBackend.discover()]

    @classmethod
    async def discover_detailed_async(cls) -> List[Dict[str, str]]:
        """Async wrapper for discover_detailed()."""
        return await asyncio.to_thread(cls.discover_detailed)

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize scanner connection.

        This method should:
        1. Connect to the scanner hardware
        2. Apply default configuration
        3. Prepare for acquisition

        Returns:
            True if initialization successful

        Raises:
            CameraNotFoundError: If scanner cannot be found
            CameraConnectionError: If connection fails
            SDKNotAvailableError: If required SDK is not available
        """
        raise NotImplementedError

    @abstractmethod
    async def capture(
        self,
        timeout_ms: int = 10000,
        enable_range: bool = True,
        enable_intensity: bool = True,
        enable_confidence: bool = False,
        enable_normal: bool = False,
        enable_color: bool = False,
    ) -> ScanResult:
        """Capture 3D scan data with multiple components.

        3D scanners can output multiple data types in a single capture:
        - Range/Depth: Z-distance from scanner to surface
        - Intensity: Grayscale texture/reflectance image
        - Confidence: Per-pixel quality/confidence values
        - Normal: Surface normal vectors
        - Color: RGB texture (if color camera available)

        Args:
            timeout_ms: Capture timeout in milliseconds
            enable_range: Whether to capture range/depth data
            enable_intensity: Whether to capture intensity/texture data
            enable_confidence: Whether to capture confidence/quality data
            enable_normal: Whether to capture surface normal vectors
            enable_color: Whether to capture color texture

        Returns:
            ScanResult containing captured multi-component data

        Raises:
            CameraConnectionError: If scanner not opened
            CameraCaptureError: If capture fails
            CameraTimeoutError: If capture times out
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close scanner and release resources.

        This method should:
        1. Stop any ongoing acquisition
        2. Release hardware handles
        3. Clean up Harvester/GenTL resources
        4. Clean up executors/threads if used
        """
        raise NotImplementedError

    # =========================================================================
    # Abstract Properties - Must be implemented by subclasses
    # =========================================================================

    @property
    @abstractmethod
    def name(self) -> str:
        """Get scanner name in format 'BackendType:serial_number'."""
        raise NotImplementedError

    @property
    def is_open(self) -> bool:
        """Check if scanner is open."""
        return self._is_open

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        """Get device information dictionary."""
        return self._device_info

    # =========================================================================
    # Optional Methods - Default implementations provided
    # =========================================================================

    async def capture_point_cloud(
        self,
        include_colors: bool = True,
        include_confidence: bool = False,
        timeout_ms: int = 10000,
    ) -> PointCloudData:
        """Capture and generate 3D point cloud.

        Default implementation captures scan data and generates point cloud.
        Override for backend-specific optimization.

        Args:
            include_colors: Whether to include color/intensity information
            include_confidence: Whether to include confidence values
            timeout_ms: Capture timeout in milliseconds

        Returns:
            PointCloudData with 3D points and optional attributes

        Raises:
            CameraConnectionError: If scanner not opened
            CameraCaptureError: If capture fails
        """
        self.logger.warning(
            f"capture_point_cloud not optimized for {self.__class__.__name__}, using default implementation"
        )
        raise NotImplementedError(f"capture_point_cloud not implemented for {self.__class__.__name__}")

    # =========================================================================
    # Configuration Methods
    # =========================================================================

    async def get_capabilities(self) -> ScannerCapabilities:
        """Get scanner capabilities and available settings.

        Returns:
            ScannerCapabilities describing what features are available

        Raises:
            CameraConnectionError: If scanner not opened
        """
        raise NotImplementedError(f"get_capabilities not implemented for {self.__class__.__name__}")

    async def get_configuration(self) -> ScannerConfiguration:
        """Get current scanner configuration.

        Returns:
            ScannerConfiguration with current settings

        Raises:
            CameraConnectionError: If scanner not opened
        """
        raise NotImplementedError(f"get_configuration not implemented for {self.__class__.__name__}")

    async def set_configuration(self, config: ScannerConfiguration) -> None:
        """Apply scanner configuration.

        Only non-None values in the configuration will be applied.

        Args:
            config: Configuration to apply

        Raises:
            CameraConnectionError: If scanner not opened
            CameraConfigurationError: If configuration fails
        """
        raise NotImplementedError(f"set_configuration not implemented for {self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # Exposure Configuration
    # -------------------------------------------------------------------------

    async def set_exposure_time(self, milliseconds: float) -> None:
        """Set exposure time in milliseconds.

        Args:
            milliseconds: Exposure time in milliseconds

        Raises:
            CameraConnectionError: If scanner not opened
            CameraConfigurationError: If configuration fails
        """
        raise NotImplementedError(f"set_exposure_time not supported by {self.__class__.__name__}")

    async def get_exposure_time(self) -> float:
        """Get current exposure time in milliseconds.

        Returns:
            Current exposure time in milliseconds

        Raises:
            CameraConnectionError: If scanner not opened
        """
        raise NotImplementedError(f"get_exposure_time not supported by {self.__class__.__name__}")

    async def set_shutter_multiplier(self, multiplier: int) -> None:
        """Set shutter multiplier (1-10).

        Higher values increase exposure by capturing multiple patterns.

        Args:
            multiplier: Shutter multiplier value (1-10)
        """
        raise NotImplementedError(f"set_shutter_multiplier not supported by {self.__class__.__name__}")

    async def get_shutter_multiplier(self) -> int:
        """Get current shutter multiplier."""
        raise NotImplementedError(f"get_shutter_multiplier not supported by {self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # Operation Mode Configuration
    # -------------------------------------------------------------------------

    async def set_operation_mode(self, mode: str) -> None:
        """Set scanner operation mode.

        Args:
            mode: Operation mode ('Camera', 'Scanner', 'Mode_2D')
        """
        raise NotImplementedError(f"set_operation_mode not supported by {self.__class__.__name__}")

    async def get_operation_mode(self) -> str:
        """Get current operation mode."""
        raise NotImplementedError(f"get_operation_mode not supported by {self.__class__.__name__}")

    async def set_coding_strategy(self, strategy: str) -> None:
        """Set structured light coding strategy.

        Args:
            strategy: Coding strategy ('Normal', 'Interreflections', 'HighFrequency')
        """
        raise NotImplementedError(f"set_coding_strategy not supported by {self.__class__.__name__}")

    async def get_coding_strategy(self) -> str:
        """Get current coding strategy."""
        raise NotImplementedError(f"get_coding_strategy not supported by {self.__class__.__name__}")

    async def set_coding_quality(self, quality: str) -> None:
        """Set scan quality/speed tradeoff.

        Args:
            quality: Quality preset ('Ultra', 'High', 'Fast')
        """
        raise NotImplementedError(f"set_coding_quality not supported by {self.__class__.__name__}")

    async def get_coding_quality(self) -> str:
        """Get current coding quality."""
        raise NotImplementedError(f"get_coding_quality not supported by {self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # Lighting Configuration
    # -------------------------------------------------------------------------

    async def set_led_power(self, power: int) -> None:
        """Set LED illumination power.

        Args:
            power: LED power level (typically 0-4095)
        """
        raise NotImplementedError(f"set_led_power not supported by {self.__class__.__name__}")

    async def get_led_power(self) -> int:
        """Get current LED power level."""
        raise NotImplementedError(f"get_led_power not supported by {self.__class__.__name__}")

    async def set_laser_power(self, power: int) -> None:
        """Set laser/projector power.

        Args:
            power: Laser power level (typically 1-4095)
        """
        raise NotImplementedError(f"set_laser_power not supported by {self.__class__.__name__}")

    async def get_laser_power(self) -> int:
        """Get current laser power level."""
        raise NotImplementedError(f"get_laser_power not supported by {self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # Texture Configuration
    # -------------------------------------------------------------------------

    async def set_texture_source(self, source: str) -> None:
        """Set texture/intensity data source.

        Args:
            source: Texture source ('LED', 'Computed', 'Laser', 'Focus', 'Color')
        """
        raise NotImplementedError(f"set_texture_source not supported by {self.__class__.__name__}")

    async def get_texture_source(self) -> str:
        """Get current texture source."""
        raise NotImplementedError(f"get_texture_source not supported by {self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # Output Configuration
    # -------------------------------------------------------------------------

    async def set_output_topology(self, topology: str) -> None:
        """Set point cloud output topology.

        Args:
            topology: Output topology ('Raw', 'RegularGrid', 'FullGrid')
        """
        raise NotImplementedError(f"set_output_topology not supported by {self.__class__.__name__}")

    async def get_output_topology(self) -> str:
        """Get current output topology."""
        raise NotImplementedError(f"get_output_topology not supported by {self.__class__.__name__}")

    async def set_camera_space(self, space: str) -> None:
        """Set coordinate system reference camera.

        Args:
            space: Camera space ('PrimaryCamera', 'ColorCamera')
        """
        raise NotImplementedError(f"set_camera_space not supported by {self.__class__.__name__}")

    async def get_camera_space(self) -> str:
        """Get current camera space."""
        raise NotImplementedError(f"get_camera_space not supported by {self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # Processing Configuration
    # -------------------------------------------------------------------------

    async def set_normals_estimation_radius(self, radius: int) -> None:
        """Set radius for surface normal estimation.

        Args:
            radius: Estimation radius (typically 0-4)
        """
        raise NotImplementedError(f"set_normals_estimation_radius not supported by {self.__class__.__name__}")

    async def get_normals_estimation_radius(self) -> int:
        """Get current normals estimation radius."""
        raise NotImplementedError(f"get_normals_estimation_radius not supported by {self.__class__.__name__}")

    async def set_max_inaccuracy(self, value: float) -> None:
        """Set maximum allowed inaccuracy for point filtering.

        Args:
            value: Maximum inaccuracy (typically 0-100)
        """
        raise NotImplementedError(f"set_max_inaccuracy not supported by {self.__class__.__name__}")

    async def get_max_inaccuracy(self) -> float:
        """Get current max inaccuracy setting."""
        raise NotImplementedError(f"get_max_inaccuracy not supported by {self.__class__.__name__}")

    async def set_hole_filling(self, enabled: bool) -> None:
        """Enable/disable hole filling in point cloud.

        Args:
            enabled: Whether to enable hole filling
        """
        raise NotImplementedError(f"set_hole_filling not supported by {self.__class__.__name__}")

    async def get_hole_filling(self) -> bool:
        """Get hole filling state."""
        raise NotImplementedError(f"get_hole_filling not supported by {self.__class__.__name__}")

    async def set_calibration_volume_only(self, enabled: bool) -> None:
        """Enable/disable filtering to calibration volume only.

        Args:
            enabled: Whether to filter to calibration volume
        """
        raise NotImplementedError(f"set_calibration_volume_only not supported by {self.__class__.__name__}")

    async def get_calibration_volume_only(self) -> bool:
        """Get calibration volume filtering state."""
        raise NotImplementedError(f"get_calibration_volume_only not supported by {self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # Trigger Configuration
    # -------------------------------------------------------------------------

    async def set_trigger_mode(self, mode: str) -> None:
        """Set trigger mode.

        Args:
            mode: Trigger mode ('Software', 'Hardware', 'Continuous')
        """
        raise NotImplementedError(f"set_trigger_mode not supported by {self.__class__.__name__}")

    async def get_trigger_mode(self) -> str:
        """Get current trigger mode."""
        raise NotImplementedError(f"get_trigger_mode not supported by {self.__class__.__name__}")

    async def set_hardware_trigger(self, enabled: bool) -> None:
        """Enable/disable hardware trigger.

        Args:
            enabled: Whether to enable hardware trigger
        """
        raise NotImplementedError(f"set_hardware_trigger not supported by {self.__class__.__name__}")

    async def get_hardware_trigger(self) -> bool:
        """Get hardware trigger state."""
        raise NotImplementedError(f"get_hardware_trigger not supported by {self.__class__.__name__}")

    async def set_hardware_trigger_signal(self, signal: str) -> None:
        """Set hardware trigger signal edge.

        Args:
            signal: Trigger signal edge ('Falling', 'Rising', 'Both')
        """
        raise NotImplementedError(f"set_hardware_trigger_signal not supported by {self.__class__.__name__}")

    async def get_hardware_trigger_signal(self) -> str:
        """Get current hardware trigger signal setting."""
        raise NotImplementedError(f"get_hardware_trigger_signal not supported by {self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # FPS Configuration
    # -------------------------------------------------------------------------

    async def set_maximum_fps(self, fps: float) -> None:
        """Set maximum frames per second.

        Args:
            fps: Maximum FPS (typically 0-100)
        """
        raise NotImplementedError(f"set_maximum_fps not supported by {self.__class__.__name__}")

    async def get_maximum_fps(self) -> float:
        """Get current maximum FPS setting."""
        raise NotImplementedError(f"get_maximum_fps not supported by {self.__class__.__name__}")

    # =========================================================================
    # Context Manager Support
    # =========================================================================

    async def __aenter__(self) -> "Scanner3DBackend":
        """Async context manager entry - initializes the scanner."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - closes the scanner."""
        await self.close()

    # =========================================================================
    # Lifecycle Helpers
    # =========================================================================

    def __del__(self) -> None:
        """Destructor - warn if scanner not properly closed."""
        try:
            if hasattr(self, "_is_open") and self._is_open:
                if hasattr(self, "logger"):
                    self.logger.warning(
                        f"Scanner3DBackend '{getattr(self, 'serial_number', 'unknown')}' "
                        f"destroyed without proper cleanup. Use 'async with scanner' or call "
                        f"'await scanner.close()' for proper cleanup."
                    )
        except Exception:
            pass

    def __repr__(self) -> str:
        """String representation."""
        status = "open" if self._is_open else "closed"
        return f"{self.__class__.__name__}(serial_number={self.serial_number}, status={status})"
