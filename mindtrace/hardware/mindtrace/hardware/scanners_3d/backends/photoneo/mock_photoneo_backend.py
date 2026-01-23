"""Mock Photoneo backend for testing without hardware."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

import numpy as np

from mindtrace.hardware.core.exceptions import (
    CameraConnectionError,
    CameraNotFoundError,
)
from mindtrace.hardware.scanners_3d.backends.scanner_3d_backend import Scanner3DBackend
from mindtrace.hardware.scanners_3d.core.models import (
    PointCloudData,
    ScanComponent,
    ScanResult,
)


class MockPhotoneoBackend(Scanner3DBackend):
    """Mock backend for Photoneo scanners for testing.

    Generates synthetic 3D data for testing scanner integration
    without physical hardware.

    Extends Scanner3DBackend to provide consistent interface across
    different 3D scanner backends.

    Usage:
        >>> backend = MockPhotoneoBackend(serial_number="MOCK001")
        >>> await backend.initialize()
        >>> result = await backend.capture()
        >>> print(result.range_shape)
        >>> await backend.close()
    """

    # Class-level registry of mock devices
    _mock_devices: List[Dict[str, str]] = [
        {"serial_number": "MOCK001", "model": "PhoXi 3D Scanner M", "vendor": "Photoneo"},
        {"serial_number": "MOCK002", "model": "PhoXi 3D Scanner L", "vendor": "Photoneo"},
    ]

    def __init__(
        self,
        serial_number: Optional[str] = None,
        width: int = 2064,
        height: int = 1544,
        op_timeout_s: float = 30.0,
    ):
        """Initialize mock Photoneo backend.

        Args:
            serial_number: Serial number of mock device.
                          If None, uses first available mock device.
            width: Width of generated images
            height: Height of generated images
            op_timeout_s: Timeout for operations (simulated)
        """
        super().__init__(serial_number=serial_number or "MOCK001", op_timeout_s=op_timeout_s)

        self._width = width
        self._height = height
        self._exposure_time = 10000.0  # microseconds
        self._trigger_mode = "software"

    @staticmethod
    def discover() -> List[str]:
        """Discover available mock devices.

        Returns:
            List of serial numbers for mock devices
        """
        return [d["serial_number"] for d in MockPhotoneoBackend._mock_devices]

    @classmethod
    async def discover_async(cls) -> List[str]:
        """Async wrapper for discover()."""
        return cls.discover()

    @staticmethod
    def discover_detailed() -> List[Dict[str, str]]:
        """Discover mock devices with detailed information.

        Returns:
            List of dictionaries containing device information
        """
        return MockPhotoneoBackend._mock_devices.copy()

    @classmethod
    async def discover_detailed_async(cls) -> List[Dict[str, str]]:
        """Async wrapper for discover_detailed()."""
        return cls.discover_detailed()

    async def initialize(self) -> bool:
        """Initialize mock scanner connection.

        Returns:
            True if initialization successful

        Raises:
            CameraNotFoundError: If mock device not found
        """
        # Simulate connection delay
        await asyncio.sleep(0.1)

        # Find mock device
        for device in self._mock_devices:
            if device["serial_number"] == self.serial_number:
                self._device_info = device.copy()
                self._is_open = True
                self.logger.info(f"Opened mock Photoneo: {device['model']} (SN: {device['serial_number']})")
                return True

        raise CameraNotFoundError(f"Mock Photoneo '{self.serial_number}' not found")

    async def capture(
        self,
        timeout_ms: int = 10000,
        enable_range: bool = True,
        enable_intensity: bool = True,
        enable_confidence: bool = False,
        enable_normal: bool = False,
        enable_color: bool = False,
    ) -> ScanResult:
        """Capture synthetic 3D scan data.

        Args:
            timeout_ms: Capture timeout (simulated)
            enable_range: Whether to generate range data
            enable_intensity: Whether to generate intensity data
            enable_confidence: Whether to generate confidence data
            enable_normal: Whether to generate normal data
            enable_color: Whether to generate color data

        Returns:
            ScanResult with synthetic data

        Raises:
            CameraConnectionError: If not initialized
        """
        if not self._is_open:
            raise CameraConnectionError("Mock scanner not opened")

        # Simulate capture delay
        await asyncio.sleep(0.05)

        h, w = self._height, self._width

        # Generate synthetic range data (simulated depth)
        range_map = None
        if enable_range:
            # Create a synthetic depth pattern (sphere-like)
            y, x = np.ogrid[:h, :w]
            cx, cy = w // 2, h // 2
            r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            range_map = (1000 + 500 * np.cos(r / 100)).astype(np.uint16)
            # Add some invalid regions
            range_map[r > min(h, w) * 0.45] = 0

        # Generate intensity data
        intensity = None
        if enable_intensity:
            intensity = (128 + 64 * np.sin(np.arange(h)[:, None] / 50) * np.cos(np.arange(w)[None, :] / 50)).astype(
                np.uint8
            )

        # Generate confidence data
        confidence = None
        if enable_confidence:
            confidence = np.ones((h, w), dtype=np.uint8) * 200
            if range_map is not None:
                confidence[range_map == 0] = 0

        # Generate normal map (simplified)
        normal_map = None
        if enable_normal:
            normal_map = np.zeros((h, w, 3), dtype=np.float32)
            normal_map[:, :, 2] = 1.0  # All pointing Z

        # Generate color data
        color = None
        if enable_color:
            color = np.zeros((h, w, 3), dtype=np.uint8)
            color[:, :, 0] = 128  # Red channel
            color[:, :, 1] = 100  # Green channel
            color[:, :, 2] = 80  # Blue channel

        self._frame_counter += 1

        return ScanResult(
            range_map=range_map,
            intensity=intensity,
            confidence=confidence,
            normal_map=normal_map,
            color=color,
            timestamp=time.time(),
            frame_number=self._frame_counter,
            components_enabled={
                ScanComponent.RANGE: enable_range,
                ScanComponent.INTENSITY: enable_intensity,
                ScanComponent.CONFIDENCE: enable_confidence,
                ScanComponent.NORMAL: enable_normal,
                ScanComponent.COLOR: enable_color,
            },
        )

    async def capture_point_cloud(
        self,
        include_colors: bool = True,
        include_confidence: bool = False,
        timeout_ms: int = 10000,
    ) -> PointCloudData:
        """Capture and generate synthetic point cloud.

        Args:
            include_colors: Whether to include colors
            include_confidence: Whether to include confidence
            timeout_ms: Capture timeout

        Returns:
            PointCloudData with synthetic points
        """
        result = await self.capture(
            timeout_ms=timeout_ms,
            enable_range=True,
            enable_intensity=include_colors,
            enable_confidence=include_confidence,
        )

        h, w = result.range_map.shape

        # Create grid
        u, v = np.meshgrid(np.arange(w), np.arange(h))
        z = result.range_map.astype(np.float32) / 1000.0  # Convert to meters

        # Simple projection
        fx, fy = 1000.0, 1000.0  # Approximate focal length
        cx, cy = w / 2, h / 2
        x = (u - cx) * z / fx
        y = (v - cy) * z / fy

        points = np.stack([x, y, z], axis=-1).reshape(-1, 3)

        # Filter invalid
        valid = z.reshape(-1) > 0
        points = points[valid]

        # Colors
        colors = None
        if include_colors and result.has_intensity:
            intensity = result.intensity
            colors = np.stack([intensity, intensity, intensity], axis=-1)
            colors = colors.reshape(-1, 3)[valid].astype(np.float64) / 255.0

        # Confidence
        confidence = None
        if include_confidence and result.has_confidence:
            confidence = result.confidence.reshape(-1)[valid].astype(np.float64) / 255.0

        return PointCloudData(
            points=points.astype(np.float64),
            colors=colors,
            confidence=confidence,
            num_points=len(points),
            has_colors=(colors is not None),
        )

    async def close(self) -> None:
        """Close mock scanner."""
        await asyncio.sleep(0.01)  # Simulate cleanup
        self._is_open = False
        self.logger.info("Mock Photoneo scanner closed")

    # Configuration methods
    async def set_exposure_time(self, microseconds: float) -> None:
        """Set exposure time (simulated)."""
        if not self._is_open:
            raise CameraConnectionError("Mock scanner not opened")
        self._exposure_time = microseconds

    async def get_exposure_time(self) -> float:
        """Get exposure time."""
        if not self._is_open:
            raise CameraConnectionError("Mock scanner not opened")
        return self._exposure_time

    async def set_trigger_mode(self, mode: str) -> None:
        """Set trigger mode (simulated)."""
        if not self._is_open:
            raise CameraConnectionError("Mock scanner not opened")
        self._trigger_mode = mode

    async def get_trigger_mode(self) -> str:
        """Get trigger mode."""
        if not self._is_open:
            raise CameraConnectionError("Mock scanner not opened")
        return self._trigger_mode

    # Properties
    @property
    def name(self) -> str:
        """Get scanner name."""
        return f"MockPhotoneo:{self.serial_number}"

    @property
    def is_open(self) -> bool:
        """Check if scanner is open."""
        return self._is_open

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        """Get device information."""
        return self._device_info

    def __repr__(self) -> str:
        """String representation."""
        status = "open" if self._is_open else "closed"
        return f"MockPhotoneoBackend(name={self.name}, status={status})"
