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
    CameraSpace,
    CodingQuality,
    CodingStrategy,
    HardwareTriggerSignal,
    OperationMode,
    OutputTopology,
    PointCloudData,
    ScanComponent,
    ScannerCapabilities,
    ScannerConfiguration,
    ScanResult,
    TextureSource,
    TriggerMode,
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

        # Configuration state — mirrors all settings from PhotoneoBackend
        self._exposure_time: float = 10.0  # milliseconds
        self._single_pattern_exposure: float = 10.0
        self._shutter_multiplier: int = 1
        self._scan_multiplier: int = 1
        self._color_exposure: float = 10.0
        self._operation_mode: str = "Scanner"
        self._coding_strategy: str = "Normal"
        self._coding_quality: str = "High"
        self._led_power: int = 2048
        self._laser_power: int = 2048
        self._texture_source: str = "LED"
        self._camera_texture_source: str = "LED"
        self._output_topology: str = "RegularGrid"
        self._camera_space: str = "PrimaryCamera"
        self._normals_estimation_radius: int = 2
        self._max_inaccuracy: float = 3.5
        self._hole_filling: bool = False
        self._calibration_volume_only: bool = False
        self._trigger_mode: str = "Software"
        self._hardware_trigger: bool = False
        self._hardware_trigger_signal: str = "Falling"
        self._maximum_fps: float = 0.0

    # =========================================================================
    # Discovery
    # =========================================================================

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

    # =========================================================================
    # Connection Lifecycle
    # =========================================================================

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

    async def close(self) -> None:
        """Close mock scanner."""
        await asyncio.sleep(0.01)  # Simulate cleanup
        self._is_open = False
        self.logger.info("Mock Photoneo scanner closed")

    def _check_open(self) -> None:
        """Check if scanner is open, raise if not."""
        if not self._is_open:
            raise CameraConnectionError("Mock scanner not opened")

    # =========================================================================
    # Capture
    # =========================================================================

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
        self._check_open()

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

    # =========================================================================
    # Configuration Methods (Bulk)
    # =========================================================================

    async def get_capabilities(self) -> ScannerCapabilities:
        """Get mock scanner capabilities."""
        self._check_open()

        caps = ScannerCapabilities()
        caps.has_range = True
        caps.has_intensity = True
        caps.has_confidence = True
        caps.has_normal = True
        caps.has_color = True
        caps.operation_modes = ["Camera", "Scanner", "Mode_2D"]
        caps.coding_strategies = ["Normal", "Interreflections"]
        caps.coding_qualities = ["Ultra", "High", "Fast"]
        caps.texture_sources = ["LED", "Computed", "Laser", "Focus", "Color"]
        caps.output_topologies = ["Raw", "RegularGrid", "FullGrid"]
        caps.exposure_range = (0.01, 100.0)
        caps.led_power_range = (0, 4095)
        caps.laser_power_range = (1, 4095)
        caps.fps_range = (0.0, 100.0)
        caps.model = self._device_info.get("model", "") if self._device_info else ""
        caps.serial_number = self._device_info.get("serial_number", "") if self._device_info else ""
        return caps

    async def get_configuration(self) -> ScannerConfiguration:
        """Get current mock scanner configuration."""
        self._check_open()

        config = ScannerConfiguration()
        config.operation_mode = OperationMode(self._operation_mode)
        config.coding_strategy = CodingStrategy(self._coding_strategy)
        config.coding_quality = CodingQuality(self._coding_quality)
        config.maximum_fps = self._maximum_fps
        config.exposure_time = self._exposure_time
        config.single_pattern_exposure = self._single_pattern_exposure
        config.shutter_multiplier = self._shutter_multiplier
        config.scan_multiplier = self._scan_multiplier
        config.color_exposure = self._color_exposure
        config.led_power = self._led_power
        config.laser_power = self._laser_power
        config.texture_source = TextureSource(self._texture_source)
        config.camera_texture_source = TextureSource(self._camera_texture_source)
        config.output_topology = OutputTopology(self._output_topology)
        config.camera_space = CameraSpace(self._camera_space)
        config.normals_estimation_radius = self._normals_estimation_radius
        config.max_inaccuracy = self._max_inaccuracy
        config.calibration_volume_only = self._calibration_volume_only
        config.hole_filling = self._hole_filling

        if self._trigger_mode.lower() == "continuous":
            config.trigger_mode = TriggerMode.CONTINUOUS
        else:
            config.trigger_mode = TriggerMode.SOFTWARE

        config.hardware_trigger = self._hardware_trigger
        config.hardware_trigger_signal = HardwareTriggerSignal(self._hardware_trigger_signal)
        return config

    async def set_configuration(self, config: ScannerConfiguration) -> None:
        """Apply scanner configuration."""
        self._check_open()

        if config.operation_mode is not None:
            self._operation_mode = config.operation_mode.value
        if config.coding_strategy is not None:
            self._coding_strategy = config.coding_strategy.value
        if config.coding_quality is not None:
            self._coding_quality = config.coding_quality.value
        if config.maximum_fps is not None:
            self._maximum_fps = config.maximum_fps
        if config.exposure_time is not None:
            self._exposure_time = config.exposure_time
        if config.single_pattern_exposure is not None:
            self._single_pattern_exposure = config.single_pattern_exposure
        if config.shutter_multiplier is not None:
            self._shutter_multiplier = config.shutter_multiplier
        if config.scan_multiplier is not None:
            self._scan_multiplier = config.scan_multiplier
        if config.color_exposure is not None:
            self._color_exposure = config.color_exposure
        if config.led_power is not None:
            self._led_power = config.led_power
        if config.laser_power is not None:
            self._laser_power = config.laser_power
        if config.texture_source is not None:
            self._texture_source = config.texture_source.value
        if config.camera_texture_source is not None:
            self._camera_texture_source = config.camera_texture_source.value
        if config.output_topology is not None:
            self._output_topology = config.output_topology.value
        if config.camera_space is not None:
            self._camera_space = config.camera_space.value
        if config.normals_estimation_radius is not None:
            self._normals_estimation_radius = config.normals_estimation_radius
        if config.max_inaccuracy is not None:
            self._max_inaccuracy = config.max_inaccuracy
        if config.calibration_volume_only is not None:
            self._calibration_volume_only = config.calibration_volume_only
        if config.hole_filling is not None:
            self._hole_filling = config.hole_filling
        if config.trigger_mode is not None:
            if config.trigger_mode == TriggerMode.CONTINUOUS:
                self._trigger_mode = "Continuous"
            else:
                self._trigger_mode = "Software"
        if config.hardware_trigger is not None:
            self._hardware_trigger = config.hardware_trigger
        if config.hardware_trigger_signal is not None:
            self._hardware_trigger_signal = config.hardware_trigger_signal.value

        self.logger.info("Mock configuration applied")

    # =========================================================================
    # Individual Configuration Methods
    # =========================================================================

    # ---- Exposure ----

    async def set_exposure_time(self, milliseconds: float) -> None:
        """Set exposure time in milliseconds."""
        self._check_open()
        self._exposure_time = milliseconds

    async def get_exposure_time(self) -> float:
        """Get current exposure time in milliseconds."""
        self._check_open()
        return self._exposure_time

    async def set_shutter_multiplier(self, multiplier: int) -> None:
        """Set shutter multiplier (1-10)."""
        self._check_open()
        self._shutter_multiplier = multiplier

    async def get_shutter_multiplier(self) -> int:
        """Get current shutter multiplier."""
        self._check_open()
        return self._shutter_multiplier

    # ---- Operation Mode ----

    async def set_operation_mode(self, mode: str) -> None:
        """Set scanner operation mode."""
        self._check_open()
        self._operation_mode = mode

    async def get_operation_mode(self) -> str:
        """Get current operation mode."""
        self._check_open()
        return self._operation_mode

    async def set_coding_strategy(self, strategy: str) -> None:
        """Set structured light coding strategy."""
        self._check_open()
        self._coding_strategy = strategy

    async def get_coding_strategy(self) -> str:
        """Get current coding strategy."""
        self._check_open()
        return self._coding_strategy

    async def set_coding_quality(self, quality: str) -> None:
        """Set scan quality/speed tradeoff."""
        self._check_open()
        self._coding_quality = quality

    async def get_coding_quality(self) -> str:
        """Get current coding quality."""
        self._check_open()
        return self._coding_quality

    # ---- Lighting ----

    async def set_led_power(self, power: int) -> None:
        """Set LED illumination power (0-4095)."""
        self._check_open()
        self._led_power = power

    async def get_led_power(self) -> int:
        """Get current LED power level."""
        self._check_open()
        return self._led_power

    async def set_laser_power(self, power: int) -> None:
        """Set laser/projector power (1-4095)."""
        self._check_open()
        self._laser_power = power

    async def get_laser_power(self) -> int:
        """Get current laser power level."""
        self._check_open()
        return self._laser_power

    # ---- Texture ----

    async def set_texture_source(self, source: str) -> None:
        """Set texture/intensity data source."""
        self._check_open()
        self._texture_source = source

    async def get_texture_source(self) -> str:
        """Get current texture source."""
        self._check_open()
        return self._texture_source

    # ---- Output ----

    async def set_output_topology(self, topology: str) -> None:
        """Set point cloud output topology."""
        self._check_open()
        self._output_topology = topology

    async def get_output_topology(self) -> str:
        """Get current output topology."""
        self._check_open()
        return self._output_topology

    async def set_camera_space(self, space: str) -> None:
        """Set coordinate system reference camera."""
        self._check_open()
        self._camera_space = space

    async def get_camera_space(self) -> str:
        """Get current camera space."""
        self._check_open()
        return self._camera_space

    # ---- Processing ----

    async def set_normals_estimation_radius(self, radius: int) -> None:
        """Set radius for surface normal estimation (0-4)."""
        self._check_open()
        self._normals_estimation_radius = radius

    async def get_normals_estimation_radius(self) -> int:
        """Get current normals estimation radius."""
        self._check_open()
        return self._normals_estimation_radius

    async def set_max_inaccuracy(self, value: float) -> None:
        """Set maximum allowed inaccuracy for point filtering (0-100)."""
        self._check_open()
        self._max_inaccuracy = value

    async def get_max_inaccuracy(self) -> float:
        """Get current max inaccuracy setting."""
        self._check_open()
        return self._max_inaccuracy

    async def set_hole_filling(self, enabled: bool) -> None:
        """Enable/disable hole filling in point cloud."""
        self._check_open()
        self._hole_filling = enabled

    async def get_hole_filling(self) -> bool:
        """Get hole filling state."""
        self._check_open()
        return self._hole_filling

    async def set_calibration_volume_only(self, enabled: bool) -> None:
        """Enable/disable filtering to calibration volume only."""
        self._check_open()
        self._calibration_volume_only = enabled

    async def get_calibration_volume_only(self) -> bool:
        """Get calibration volume filtering state."""
        self._check_open()
        return self._calibration_volume_only

    # ---- Trigger ----

    async def set_trigger_mode(self, mode: str) -> None:
        """Set trigger mode ('Software', 'Hardware', 'Continuous')."""
        self._check_open()
        self._trigger_mode = mode

    async def get_trigger_mode(self) -> str:
        """Get current trigger mode."""
        self._check_open()
        return self._trigger_mode

    async def set_hardware_trigger(self, enabled: bool) -> None:
        """Enable/disable hardware trigger."""
        self._check_open()
        self._hardware_trigger = enabled

    async def get_hardware_trigger(self) -> bool:
        """Get hardware trigger state."""
        self._check_open()
        return self._hardware_trigger

    # ---- FPS ----

    async def set_maximum_fps(self, fps: float) -> None:
        """Set maximum frames per second (0-100)."""
        self._check_open()
        self._maximum_fps = fps

    async def get_maximum_fps(self) -> float:
        """Get current maximum FPS setting."""
        self._check_open()
        return self._maximum_fps

    # =========================================================================
    # Properties
    # =========================================================================

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
