"""Synchronous 3D scanner interface.

This module provides a synchronous wrapper around AsyncScanner3D, following
the same pattern as the StereoCamera class.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Optional

from mindtrace.core import Mindtrace
from mindtrace.hardware.scanners_3d.core.async_scanner_3d import AsyncScanner3D
from mindtrace.hardware.scanners_3d.core.models import (
    PointCloudData,
    ScanResult,
)


class Scanner3D(Mindtrace):
    """Synchronous wrapper around AsyncScanner3D.

    All operations are executed on a background event loop. This provides
    a simple synchronous API for 3D scanner operations.

    Usage:
        >>> scanner = Scanner3D()
        >>> result = scanner.capture()
        >>> print(result.range_shape)
        >>> scanner.close()

        >>> # Or with context manager
        >>> with Scanner3D() as scanner:
        ...     result = scanner.capture()
        ...     print(result.range_shape)
    """

    def __init__(
        self,
        async_scanner: Optional[AsyncScanner3D] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        name: Optional[str] = None,
        **kwargs,
    ):
        """Create a synchronous 3D scanner wrapper.

        Args:
            async_scanner: Existing AsyncScanner3D instance
            loop: Event loop to use for async operations
            name: Scanner identifier. Format: "Photoneo:serial_number"
                 If None, opens first available scanner.
            **kwargs: Additional arguments passed to Mindtrace

        Examples:
            >>> # Simple usage - opens first available
            >>> scanner = Scanner3D()

            >>> # Open specific scanner
            >>> scanner = Scanner3D(name="Photoneo:ABC123")

            >>> # Use existing async scanner
            >>> async_scan = await AsyncScanner3D.open()
            >>> sync_scan = Scanner3D(async_scanner=async_scan, loop=loop)
        """
        super().__init__(**kwargs)
        self._owns_loop_thread = False
        self._loop_thread: Optional[threading.Thread] = None

        if async_scanner is None or loop is None:
            # Create background event loop in dedicated thread
            self._loop = asyncio.new_event_loop()

            def _run_loop():
                asyncio.set_event_loop(self._loop)
                self._loop.run_forever()

            self._loop_thread = threading.Thread(target=_run_loop, name="Scanner3DLoop", daemon=True)
            self._loop_thread.start()
            self._owns_loop_thread = True

            # Create AsyncScanner3D on the running loop
            async def _make() -> AsyncScanner3D:
                return await AsyncScanner3D.open(name)

            self._backend = self._submit(_make())
        else:
            self._backend = async_scanner
            self._loop = loop

    # Helpers
    def _submit(self, coro):
        """Submit coroutine to event loop and wait for result."""
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    # Properties
    @property
    def name(self) -> str:
        """Get scanner name.

        Returns:
            Scanner name in format "Backend:serial_number"
        """
        return self._backend.name

    @property
    def is_open(self) -> bool:
        """Check if scanner is open.

        Returns:
            True if scanner is open, False otherwise
        """
        return self._backend.is_open

    # Lifecycle
    def close(self) -> None:
        """Close scanner and release resources.

        Examples:
            >>> scanner = Scanner3D()
            >>> # ... use scanner ...
            >>> scanner.close()
        """
        self._submit(self._backend.close())

        if self._owns_loop_thread and self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._loop_thread:
                self._loop_thread.join(timeout=2)

    # Capture operations
    def capture(
        self,
        timeout_ms: int = 10000,
        enable_range: bool = True,
        enable_intensity: bool = True,
        enable_confidence: bool = False,
        enable_normal: bool = False,
        enable_color: bool = False,
    ) -> ScanResult:
        """Capture multi-component 3D scan data.

        Args:
            timeout_ms: Capture timeout in milliseconds
            enable_range: Whether to capture range/depth data
            enable_intensity: Whether to capture intensity data
            enable_confidence: Whether to capture confidence data
            enable_normal: Whether to capture surface normals
            enable_color: Whether to capture color texture

        Returns:
            ScanResult containing captured data

        Raises:
            CameraConnectionError: If scanner not opened
            CameraCaptureError: If capture fails

        Examples:
            >>> scanner = Scanner3D()
            >>> result = scanner.capture()
            >>> print(f"Range: {result.range_shape}")
            >>> scanner.close()
        """
        return self._submit(
            self._backend.capture(
                timeout_ms=timeout_ms,
                enable_range=enable_range,
                enable_intensity=enable_intensity,
                enable_confidence=enable_confidence,
                enable_normal=enable_normal,
                enable_color=enable_color,
            )
        )

    def capture_point_cloud(
        self,
        include_colors: bool = True,
        include_confidence: bool = False,
        downsample_factor: int = 1,
        timeout_ms: int = 10000,
    ) -> PointCloudData:
        """Capture and generate 3D point cloud.

        Args:
            include_colors: Whether to include color information
            include_confidence: Whether to include confidence values
            downsample_factor: Downsampling factor (1 = no downsampling)
            timeout_ms: Capture timeout in milliseconds

        Returns:
            PointCloudData with 3D points and optional attributes

        Raises:
            CameraConnectionError: If scanner not opened
            CameraCaptureError: If capture fails

        Examples:
            >>> scanner = Scanner3D()
            >>> point_cloud = scanner.capture_point_cloud()
            >>> print(f"Points: {point_cloud.num_points}")
            >>> point_cloud.save_ply("output.ply")
            >>> scanner.close()
        """
        return self._submit(
            self._backend.capture_point_cloud(
                include_colors=include_colors,
                include_confidence=include_confidence,
                downsample_factor=downsample_factor,
                timeout_ms=timeout_ms,
            )
        )

    # Configuration
    def set_exposure_time(self, microseconds: float) -> None:
        """Set exposure time in microseconds.

        Args:
            microseconds: Exposure time in microseconds (e.g., 5000 = 5ms)

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> scanner = Scanner3D()
            >>> scanner.set_exposure_time(5000)
            >>> scanner.close()
        """
        self._submit(self._backend.set_exposure_time(microseconds))

    def get_exposure_time(self) -> float:
        """Get current exposure time in microseconds.

        Returns:
            Current exposure time in microseconds

        Raises:
            CameraConnectionError: If scanner not opened

        Examples:
            >>> scanner = Scanner3D()
            >>> exposure = scanner.get_exposure_time()
            >>> print(f"Exposure: {exposure}μs")
            >>> scanner.close()
        """
        return self._submit(self._backend.get_exposure_time())

    def set_trigger_mode(self, mode: str) -> None:
        """Set trigger mode.

        Args:
            mode: Trigger mode ("continuous" or "software")

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> scanner = Scanner3D()
            >>> scanner.set_trigger_mode("software")
            >>> scanner.close()
        """
        self._submit(self._backend.set_trigger_mode(mode))

    def get_trigger_mode(self) -> str:
        """Get current trigger mode.

        Returns:
            "continuous" or "software"

        Raises:
            CameraConnectionError: If scanner not opened

        Examples:
            >>> scanner = Scanner3D()
            >>> mode = scanner.get_trigger_mode()
            >>> print(f"Mode: {mode}")
            >>> scanner.close()
        """
        return self._submit(self._backend.get_trigger_mode())

    # Context manager support
    def __enter__(self) -> "Scanner3D":
        """Context manager entry.

        Examples:
            >>> with Scanner3D() as scanner:
            ...     result = scanner.capture()
            ...     print(result.range_shape)
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def __repr__(self) -> str:
        """String representation."""
        status = "open" if self.is_open else "closed"
        return f"Scanner3D(name={self.name}, status={status})"
