"""Async 3D scanner interface providing high-level scanning operations."""

from __future__ import annotations

from typing import Optional

from mindtrace.core import Mindtrace
from mindtrace.hardware.core.exceptions import CameraConnectionError
from mindtrace.hardware.scanners_3d.core.models import (
    PointCloudData,
    ScannerCapabilities,
    ScannerConfiguration,
    ScanResult,
)


class AsyncScanner3D(Mindtrace):
    """Async 3D scanner interface.

    Provides high-level 3D scanning operations including multi-component capture
    and point cloud generation.

    Usage:
        >>> scanner = await AsyncScanner3D.open()
        >>> result = await scanner.capture()
        >>> print(result.range_shape)
        >>> await scanner.close()
    """

    def __init__(self, backend):
        """Initialize async 3D scanner.

        Args:
            backend: Backend instance (e.g., PhotoneoBackend)
        """
        super().__init__()
        self._backend = backend

    @classmethod
    async def open(cls, name: Optional[str] = None) -> "AsyncScanner3D":
        """Open and initialize a 3D scanner.

        Args:
            name: Scanner identifier. Format: "Photoneo:serial_number"
                 If None, opens first available scanner.

        Returns:
            Initialized AsyncScanner3D instance

        Raises:
            CameraNotFoundError: If scanner not found
            CameraConnectionError: If connection fails

        Examples:
            >>> scanner = await AsyncScanner3D.open()
            >>> scanner = await AsyncScanner3D.open("Photoneo:ABC123")
        """
        # Parse name to extract backend type and serial number
        backend_type = "Photoneo"
        serial_number = None

        if name:
            if ":" in name:
                parts = name.split(":", 1)
                backend_type = parts[0]
                serial_number = parts[1] if len(parts) > 1 else None
            else:
                serial_number = name

        # Create appropriate backend
        if backend_type.lower() == "photoneo":
            from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
                PhotoneoBackend,
            )

            backend = PhotoneoBackend(serial_number=serial_number)
        else:
            raise ValueError(f"Unknown scanner backend type: {backend_type}")

        # Initialize
        success = await backend.initialize()
        if not success:
            raise CameraConnectionError(f"Failed to open scanner: {name or 'first available'}")

        return cls(backend)

    # Lifecycle
    async def close(self) -> None:
        """Close scanner and release resources."""
        await self._backend.close()

    # Capture operations
    async def capture(
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
            >>> result = await scanner.capture()
            >>> print(f"Range: {result.range_shape}")
            >>> print(f"Intensity: {result.intensity_shape}")
        """
        return await self._backend.capture(
            timeout_ms=timeout_ms,
            enable_range=enable_range,
            enable_intensity=enable_intensity,
            enable_confidence=enable_confidence,
            enable_normal=enable_normal,
            enable_color=enable_color,
        )

    async def capture_point_cloud(
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
            >>> point_cloud = await scanner.capture_point_cloud()
            >>> print(f"Points: {point_cloud.num_points}")
            >>> point_cloud.save_ply("output.ply")
        """
        point_cloud = await self._backend.capture_point_cloud(
            include_colors=include_colors,
            include_confidence=include_confidence,
            timeout_ms=timeout_ms,
        )

        if downsample_factor > 1:
            point_cloud = point_cloud.downsample(downsample_factor)

        return point_cloud

    # Configuration
    async def get_capabilities(self) -> ScannerCapabilities:
        """Get scanner capabilities and available settings.

        Returns:
            ScannerCapabilities with available options and ranges

        Examples:
            >>> caps = await scanner.get_capabilities()
            >>> print(f"Coding qualities: {caps.coding_qualities}")
        """
        return await self._backend.get_capabilities()

    async def get_configuration(self) -> ScannerConfiguration:
        """Get current scanner configuration.

        Returns:
            ScannerConfiguration with current settings

        Examples:
            >>> config = await scanner.get_configuration()
            >>> print(f"Exposure: {config.exposure_time}ms")
        """
        return await self._backend.get_configuration()

    async def set_configuration(self, config: ScannerConfiguration) -> None:
        """Apply scanner configuration.

        Only non-None values in the configuration will be applied.

        Args:
            config: Configuration to apply

        Examples:
            >>> config = ScannerConfiguration(exposure_time=15.0, coding_quality=CodingQuality.HIGH)
            >>> await scanner.set_configuration(config)
        """
        await self._backend.set_configuration(config)

    async def set_exposure_time(self, milliseconds: float) -> None:
        """Set exposure time in milliseconds.

        Args:
            milliseconds: Exposure time in milliseconds

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> await scanner.set_exposure_time(10.24)  # 10.24ms exposure
        """
        await self._backend.set_exposure_time(milliseconds)

    async def get_exposure_time(self) -> float:
        """Get current exposure time in milliseconds.

        Returns:
            Current exposure time in milliseconds

        Raises:
            CameraConnectionError: If scanner not opened

        Examples:
            >>> exposure = await scanner.get_exposure_time()
            >>> print(f"Exposure: {exposure}ms")
        """
        return await self._backend.get_exposure_time()

    async def set_trigger_mode(self, mode: str) -> None:
        """Set trigger mode.

        Args:
            mode: Trigger mode ("Continuous", "Software", or "Hardware")

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> await scanner.set_trigger_mode("Software")
        """
        await self._backend.set_trigger_mode(mode)

    async def get_trigger_mode(self) -> str:
        """Get current trigger mode.

        Returns:
            "Continuous", "Software", or "Hardware"

        Raises:
            CameraConnectionError: If scanner not opened

        Examples:
            >>> mode = await scanner.get_trigger_mode()
            >>> print(f"Mode: {mode}")
        """
        return await self._backend.get_trigger_mode()

    # Properties
    @property
    def name(self) -> str:
        """Get scanner name."""
        return self._backend.name

    @property
    def is_open(self) -> bool:
        """Check if scanner is open."""
        return self._backend.is_open

    def __repr__(self) -> str:
        """String representation."""
        status = "open" if self.is_open else "closed"
        return f"AsyncScanner3D(name={self.name}, status={status})"
