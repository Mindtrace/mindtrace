"""Photoneo PhoXi 3D scanner backend using Harvesters (GigE Vision).

This backend provides access to Photoneo structured light 3D scanners
via the GigE Vision protocol using the Harvesters library.
"""

from __future__ import annotations

import asyncio
import os
import platform
from typing import Any, Callable, Dict, List, Optional, TypeVar

import numpy as np

from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraNotFoundError,
    CameraTimeoutError,
    HardwareOperationError,
    SDKNotAvailableError,
)
from mindtrace.hardware.scanners_3d.backends.scanner_3d_backend import Scanner3DBackend
from mindtrace.hardware.scanners_3d.core.models import (
    CameraSpace,
    CodingQuality,
    CodingStrategy,
    CoordinateMap,
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

try:
    from harvesters.core import Harvester

    HARVESTERS_AVAILABLE = True
except ImportError:
    HARVESTERS_AVAILABLE = False
    Harvester = None

T = TypeVar("T")


class PhotoneoBackend(Scanner3DBackend):
    """Backend for Photoneo PhoXi 3D scanners using Harvesters.

    Photoneo PhoXi scanners are structured light 3D sensors that output
    multiple data components: Range, Intensity, Confidence, Normal, and Color.

    This backend uses GigE Vision protocol via Harvesters library with
    Matrix Vision GenTL Producer.

    Extends Scanner3DBackend to provide consistent interface across
    different 3D scanner manufacturers.

    Requirements:
        - Harvesters library: pip install harvesters
        - Matrix Vision mvIMPACT Acquire SDK with GenTL Producer
        - Photoneo PhoXi firmware version 1.13.0 or later

    Usage:
        >>> backend = PhotoneoBackend(serial_number="ABC123")
        >>> await backend.initialize()
        >>> result = await backend.capture()
        >>> print(result.range_shape)
        >>> await backend.close()
    """

    # Class-level singleton Harvester instance
    _shared_harvester: Optional[Harvester] = None
    _harvester_cti_path: Optional[str] = None
    _harvester_lock = None

    def __init__(
        self,
        serial_number: Optional[str] = None,
        cti_path: Optional[str] = None,
        op_timeout_s: float = 30.0,
        buffer_count: int = 5,
    ):
        """Initialize Photoneo backend.

        Args:
            serial_number: Serial number of specific scanner.
                          If None, opens first available Photoneo device.
            cti_path: Path to GenTL Producer (.cti file).
                     Auto-detected if None.
            op_timeout_s: Timeout in seconds for SDK operations (default 30s).
            buffer_count: Number of frame buffers for acquisition.

        Raises:
            SDKNotAvailableError: If Harvesters is not available
            CameraConfigurationError: If CTI file not found
        """
        if not HARVESTERS_AVAILABLE:
            raise SDKNotAvailableError(
                "harvesters",
                "Install Harvesters to use Photoneo scanners:\n"
                "1. Download and install Matrix Vision mvIMPACT Acquire SDK\n"
                "2. pip install harvesters\n"
                "3. Ensure GenTL Producer (.cti file) is accessible",
            )

        super().__init__(serial_number=serial_number, op_timeout_s=op_timeout_s)

        self._buffer_count = buffer_count

        # Auto-detect CTI path if not provided
        if cti_path is None:
            cti_path = self._detect_cti_path()

        if not os.path.exists(cti_path):
            raise CameraConfigurationError(f"GenTL Producer file not found: {cti_path}")

        self._cti_path = cti_path

        # Internal state
        self._harvester: Optional[Harvester] = None
        self._image_acquirer: Optional[Any] = None
        self._coordinate_map: Optional[CoordinateMap] = None

    async def _run_blocking(
        self, func: Callable[..., T], *args: Any, timeout: Optional[float] = None, **kwargs: Any
    ) -> T:
        """Run a blocking SDK call in threadpool with timeout.

        Args:
            func: The blocking function to call
            *args: Positional arguments for the function
            timeout: Optional timeout override
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
            raise CameraTimeoutError(f"Photoneo operation timed out after {effective_timeout:.2f}s") from e
        except Exception as e:
            if isinstance(
                e,
                (
                    CameraTimeoutError,
                    CameraCaptureError,
                    CameraConfigurationError,
                    CameraConnectionError,
                    CameraNotFoundError,
                ),
            ):
                raise
            raise HardwareOperationError(f"Photoneo operation failed: {e}") from e

    @staticmethod
    def _detect_cti_path() -> str:
        """Auto-detect Matrix Vision GenTL Producer path.

        Returns:
            Path to GenTL Producer (.cti) file

        Raises:
            CameraConfigurationError: If CTI file cannot be found
        """
        # Check environment variable first
        env_path = os.getenv("GENICAM_GENTL64_PATH")
        if env_path:
            # Look for .cti file in the path
            if os.path.isfile(env_path):
                return env_path
            # Check if it's a directory containing the producer
            for name in ["mvGenTLProducer.cti", "libmvGenTLProducer.cti"]:
                candidate = os.path.join(env_path, name)
                if os.path.exists(candidate):
                    return candidate

        env_path = os.getenv("GENICAM_CTI_PATH")
        if env_path and os.path.exists(env_path):
            return env_path

        system = platform.system()
        machine = platform.machine()

        # Platform-specific paths
        paths = {
            ("Linux", "x86_64"): [
                "/opt/mvIMPACT_Acquire/lib/x86_64/mvGenTLProducer.cti",
                "/opt/ImpactAcquire/lib/x86_64/mvGenTLProducer.cti",
                "/usr/lib/mvimpact-acquire/mvGenTLProducer.cti",
            ],
            ("Linux", "aarch64"): [
                "/opt/mvIMPACT_Acquire/lib/arm64/mvGenTLProducer.cti",
                "/opt/ImpactAcquire/lib/arm64/mvGenTLProducer.cti",
            ],
            ("Windows", "AMD64"): [
                r"C:\Program Files\MATRIX VISION\mvIMPACT Acquire\bin\x64\mvGenTLProducer.cti",
            ],
        }

        for path in paths.get((system, machine), []):
            if os.path.exists(path):
                return path

        raise CameraConfigurationError(
            "GenTL Producer not found. Install Matrix Vision mvIMPACT Acquire SDK "
            "and set GENICAM_GENTL64_PATH or GENICAM_CTI_PATH environment variable."
        )

    @classmethod
    def _get_shared_harvester(cls, cti_path: str) -> Harvester:
        """Get or create shared Harvester instance.

        Args:
            cti_path: Path to GenTL Producer file

        Returns:
            Shared Harvester instance
        """
        import threading

        if cls._harvester_lock is None:
            cls._harvester_lock = threading.Lock()

        with cls._harvester_lock:
            if cls._shared_harvester is None or cls._harvester_cti_path != cti_path:
                if cls._shared_harvester is not None:
                    try:
                        cls._shared_harvester.reset()
                    except Exception:
                        pass

                cls._shared_harvester = Harvester()
                cls._shared_harvester.add_file(cti_path)
                cls._shared_harvester.update()
                cls._harvester_cti_path = cti_path

            return cls._shared_harvester

    @staticmethod
    def discover() -> List[str]:
        """Discover available Photoneo devices.

        Returns:
            List of serial numbers for available Photoneo devices

        Raises:
            SDKNotAvailableError: If Harvesters is not available
        """
        if not HARVESTERS_AVAILABLE:
            raise SDKNotAvailableError("harvesters", "Harvesters not available")

        try:
            cti_path = PhotoneoBackend._detect_cti_path()
            harvester = PhotoneoBackend._get_shared_harvester(cti_path)

            # Filter for Photoneo devices
            serial_numbers = []
            for dev_info in harvester.device_info_list:
                vendor = getattr(dev_info, "vendor", "") or ""
                model = getattr(dev_info, "model", "") or ""

                # Check if it's a Photoneo device
                if "photoneo" in vendor.lower() or "phoxi" in model.lower():
                    serial = getattr(dev_info, "serial_number", None)
                    if serial:
                        serial_numbers.append(serial)

            return serial_numbers

        except CameraConfigurationError:
            return []

    @classmethod
    async def discover_async(cls) -> List[str]:
        """Async wrapper for discover().

        Returns:
            List of serial numbers for available Photoneo devices
        """
        return await asyncio.to_thread(cls.discover)

    @staticmethod
    def discover_detailed() -> List[Dict[str, str]]:
        """Discover Photoneo devices with detailed information.

        Returns:
            List of dictionaries containing device information
        """
        if not HARVESTERS_AVAILABLE:
            raise SDKNotAvailableError("harvesters", "Harvesters not available")

        try:
            cti_path = PhotoneoBackend._detect_cti_path()
            harvester = PhotoneoBackend._get_shared_harvester(cti_path)

            devices = []
            for dev_info in harvester.device_info_list:
                vendor = getattr(dev_info, "vendor", "") or ""
                model = getattr(dev_info, "model", "") or ""

                if "photoneo" in vendor.lower() or "phoxi" in model.lower():
                    devices.append(
                        {
                            "serial_number": getattr(dev_info, "serial_number", "unknown"),
                            "model": model,
                            "vendor": vendor,
                            "user_defined_name": getattr(dev_info, "user_defined_name", ""),
                        }
                    )

            return devices

        except CameraConfigurationError:
            return []

    @classmethod
    async def discover_detailed_async(cls) -> List[Dict[str, str]]:
        """Async wrapper for discover_detailed().

        Returns:
            List of dictionaries containing device information
        """
        return await asyncio.to_thread(cls.discover_detailed)

    async def initialize(self) -> bool:
        """Initialize scanner connection.

        Returns:
            True if initialization successful

        Raises:
            CameraNotFoundError: If scanner not found
            CameraConnectionError: If connection fails
        """
        try:

            def _connect():
                """Connect to scanner (blocking)."""
                self._harvester = self._get_shared_harvester(self._cti_path)

                # Find device
                target_dev = None
                for dev_info in self._harvester.device_info_list:
                    if self.serial_number:
                        serial = getattr(dev_info, "serial_number", None)
                        if serial == self.serial_number:
                            target_dev = dev_info
                            break
                    else:
                        # First available Photoneo device
                        vendor = getattr(dev_info, "vendor", "") or ""
                        model = getattr(dev_info, "model", "") or ""
                        if "photoneo" in vendor.lower() or "phoxi" in model.lower():
                            target_dev = dev_info
                            break

                if target_dev is None:
                    if self.serial_number:
                        raise CameraNotFoundError(f"Photoneo scanner '{self.serial_number}' not found")
                    else:
                        raise CameraNotFoundError("No Photoneo scanners found")

                # Create image acquirer
                serial = getattr(target_dev, "serial_number", "unknown")
                self._image_acquirer = self._harvester.create({"serial_number": serial})
                self._image_acquirer.num_buffers = self._buffer_count

                # Store device info
                self._device_info = {
                    "serial_number": serial,
                    "model": getattr(target_dev, "model", "unknown"),
                    "vendor": getattr(target_dev, "vendor", "unknown"),
                }

                return True

            await self._run_blocking(_connect)
            self._is_open = True

            # Apply default configuration
            await self._set_default_config()

            self.logger.info(
                f"Opened Photoneo scanner: {self._device_info.get('model', 'unknown')} "
                f"(SN: {self._device_info.get('serial_number', 'unknown')})"
            )

            return True

        except CameraNotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Photoneo scanner: {e}")
            raise CameraConnectionError(f"Failed to initialize: {e}") from e

    async def _set_default_config(self) -> None:
        """Set default scanner configuration."""
        try:

            def _apply_defaults():
                """Apply default configuration (blocking)."""
                if self._image_acquirer is None:
                    return

                node_map = self._image_acquirer.remote_device.node_map

                # Reset to default user set
                try:
                    node_map.UserSetSelector.value = "Default"
                    node_map.UserSetLoad.execute()
                except Exception:
                    pass  # Not all devices support user sets

                # Enable software trigger mode
                try:
                    node_map.TriggerSelector.value = "FrameStart"
                    node_map.TriggerMode.value = "On"
                    node_map.TriggerSource.value = "Software"
                except Exception:
                    pass

            await self._run_blocking(_apply_defaults)
            self.logger.debug("Applied default Photoneo configuration")

        except Exception as e:
            self.logger.warning(f"Failed to set default configuration: {e}")

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
            CameraTimeoutError: If capture times out
        """
        if not self._is_open or self._image_acquirer is None:
            raise CameraConnectionError("Scanner not opened")

        try:

            def _capture_frame():
                """Perform capture (blocking)."""
                ia = self._image_acquirer
                node_map = ia.remote_device.node_map

                # Configure components to enable
                components_map = {
                    "Range": enable_range,
                    "Intensity": enable_intensity,
                    "Confidence": enable_confidence,
                    "Normal": enable_normal,
                    "ColorCamera": enable_color,
                }

                for comp_name, enabled in components_map.items():
                    try:
                        node_map.ComponentSelector.value = comp_name
                        node_map.ComponentEnable.value = enabled
                    except Exception:
                        pass  # Component may not exist on all models

                # Start acquisition if not already
                if not ia.is_acquiring():
                    ia.start()

                # Execute software trigger
                try:
                    node_map.TriggerSoftware.execute()
                except Exception:
                    pass  # May be in freerun mode

                # Fetch buffer
                timeout_s = timeout_ms / 1000.0
                with ia.fetch(timeout=timeout_s) as buffer:
                    # Parse components from buffer
                    result_data = {
                        "range_map": None,
                        "intensity": None,
                        "confidence": None,
                        "normal_map": None,
                        "color": None,
                        "timestamp": 0.0,
                        "frame_number": 0,
                    }

                    # Get timestamp
                    try:
                        result_data["timestamp"] = buffer.timestamp_ns / 1e9
                    except Exception:
                        import time

                        result_data["timestamp"] = time.time()

                    # Process each component in the buffer
                    # Components arrive in order: Intensity, Range, Confidence, Normal, ColorCamera
                    # We identify by format + resolution + value range
                    coord3d_components = []  # Collect Coord3D components to distinguish Range vs Normal
                    rgb_components = []  # Collect RGB components to distinguish Intensity vs Color

                    for component in buffer.payload.components:
                        data_format = component.data_format
                        arr = component.data.reshape(component.height, component.width, -1)

                        if "Confidence" in str(data_format):
                            # Confidence map
                            result_data["confidence"] = arr[:, :, 0].copy() if arr.shape[2] == 1 else arr.copy()
                        elif "Coord3D" in data_format:
                            # Could be Range or Normal - collect for later disambiguation
                            coord3d_components.append(arr.copy())
                        elif "RGB" in data_format or "BGR" in data_format or "Mono" in data_format:
                            # Could be Intensity or ColorCamera - collect for later disambiguation
                            rgb_components.append(arr.copy())

                    # Disambiguate Coord3D components (Range vs Normal)
                    # Normal vectors have values in [-1, 1], Range has mm values (typically > 1)
                    for arr in coord3d_components:
                        abs_max = np.abs(arr).max()
                        if abs_max <= 1.5:
                            # Normal vectors (normalized, values in [-1, 1])
                            result_data["normal_map"] = arr
                        else:
                            # Range map (XYZ coordinates in mm)
                            result_data["range_map"] = arr

                    # Disambiguate RGB components (Intensity vs ColorCamera)
                    # Intensity has same resolution as depth, ColorCamera is higher res
                    depth_shape = result_data["range_map"].shape[:2] if result_data["range_map"] is not None else None
                    for arr in rgb_components:
                        if depth_shape and arr.shape[:2] == depth_shape:
                            # Same resolution as depth = Intensity
                            result_data["intensity"] = arr
                        else:
                            # Different (higher) resolution = ColorCamera
                            result_data["color"] = arr

                    return result_data

            data = await self._run_blocking(_capture_frame, timeout=timeout_ms / 1000.0 + 5.0)

            self._frame_counter += 1

            return ScanResult(
                range_map=data["range_map"],
                intensity=data["intensity"],
                confidence=data["confidence"],
                normal_map=data["normal_map"],
                color=data["color"],
                timestamp=data["timestamp"],
                frame_number=self._frame_counter,
                components_enabled={
                    ScanComponent.RANGE: enable_range,
                    ScanComponent.INTENSITY: enable_intensity,
                    ScanComponent.CONFIDENCE: enable_confidence,
                    ScanComponent.NORMAL: enable_normal,
                    ScanComponent.COLOR: enable_color,
                },
            )

        except asyncio.TimeoutError as e:
            raise CameraTimeoutError(f"Capture timed out after {timeout_ms}ms") from e
        except Exception as e:
            if isinstance(e, (CameraTimeoutError, CameraCaptureError)):
                raise
            raise CameraCaptureError(f"Capture failed: {e}") from e

    async def capture_point_cloud(
        self,
        include_colors: bool = True,
        include_confidence: bool = False,
        timeout_ms: int = 10000,
    ) -> PointCloudData:
        """Capture and generate 3D point cloud.

        Args:
            include_colors: Whether to include color/intensity
            include_confidence: Whether to include confidence values
            timeout_ms: Capture timeout in milliseconds

        Returns:
            PointCloudData with 3D points

        Raises:
            CameraConnectionError: If scanner not opened
            CameraCaptureError: If capture fails
        """
        # Capture scan data
        result = await self.capture(
            timeout_ms=timeout_ms,
            enable_range=True,
            enable_intensity=include_colors,
            enable_confidence=include_confidence,
        )

        if not result.has_range:
            raise CameraCaptureError("No range data captured")

        range_map = result.range_map
        h, w = range_map.shape[:2]

        # Check if range_map is XYZ (3 channels) or just Z (2D)
        if range_map.ndim == 3 and range_map.shape[2] == 3:
            # Range data is already XYZ coordinates
            points = range_map.astype(np.float32).reshape(-1, 3)
            # Valid mask: points where at least one coordinate is non-zero
            valid_mask = (np.abs(range_map).sum(axis=2) > 0).reshape(-1)
        else:
            # Range data is depth-only, reconstruct XYZ
            u, v = np.meshgrid(np.arange(w), np.arange(h))

            # Get Z values
            if range_map.ndim == 3:
                z = range_map[:, :, 0].astype(np.float32)
            else:
                z = range_map.astype(np.float32)

            # Simple pinhole model - for proper reconstruction use device calibration
            x = (u - w / 2) * z / 1000.0
            y = (v - h / 2) * z / 1000.0

            points = np.stack([x, y, z], axis=-1).reshape(-1, 3)
            valid_mask = (z > 0).reshape(-1)

        points = points[valid_mask]

        # Colors
        colors = None
        if include_colors and result.has_intensity:
            intensity = result.intensity
            if intensity.ndim == 2:
                # Grayscale to RGB
                colors = np.stack([intensity, intensity, intensity], axis=-1)
            else:
                colors = intensity
            # Reshape to match pixel count and apply valid mask
            colors = colors.reshape(-1, 3 if colors.ndim == 3 else 1)
            if colors.shape[1] == 1:
                colors = np.repeat(colors, 3, axis=1)
            colors = colors[valid_mask].astype(np.float32) / 255.0

        # Confidence
        confidence = None
        if include_confidence and result.has_confidence:
            conf = result.confidence
            if conf.ndim > 2:
                conf = conf[:, :, 0]
            confidence = conf.reshape(-1)[valid_mask].astype(np.float32) / 255.0

        return PointCloudData(
            points=points.astype(np.float64),
            colors=colors.astype(np.float64) if colors is not None else None,
            confidence=confidence.astype(np.float64) if confidence is not None else None,
            num_points=len(points),
            has_colors=(colors is not None),
        )

    async def close(self) -> None:
        """Close scanner and release resources."""
        if self._image_acquirer is not None:
            try:

                def _close():
                    if self._image_acquirer.is_acquiring():
                        self._image_acquirer.stop()
                    self._image_acquirer.destroy()

                await self._run_blocking(_close, timeout=5.0)
            except Exception as e:
                self.logger.warning(f"Error closing scanner: {e}")
            finally:
                self._image_acquirer = None

        self._is_open = False
        self.logger.info("Photoneo scanner closed")

    # =========================================================================
    # Configuration Methods
    # =========================================================================

    def _check_open(self) -> None:
        """Check if scanner is open, raise if not."""
        if not self._is_open or self._image_acquirer is None:
            raise CameraConnectionError("Scanner not opened")

    async def get_capabilities(self) -> ScannerCapabilities:
        """Get scanner capabilities and available settings."""
        self._check_open()

        def _get_caps():
            node_map = self._image_acquirer.remote_device.node_map
            caps = ScannerCapabilities()

            # Available components
            caps.has_range = True
            caps.has_intensity = True
            caps.has_confidence = True
            caps.has_normal = True
            caps.has_color = True

            # Operation modes
            try:
                caps.operation_modes = list(node_map.OperationMode.symbolics)
            except Exception:
                caps.operation_modes = []

            # Coding strategies
            try:
                caps.coding_strategies = list(node_map.CodingStrategy.symbolics)
            except Exception:
                caps.coding_strategies = []

            # Coding qualities
            try:
                caps.coding_qualities = list(node_map.CodingQuality.symbolics)
            except Exception:
                caps.coding_qualities = []

            # Texture sources
            try:
                caps.texture_sources = list(node_map.TextureSource.symbolics)
            except Exception:
                caps.texture_sources = []

            # Output topologies
            try:
                caps.output_topologies = list(node_map.OutputTopology.symbolics)
            except Exception:
                caps.output_topologies = []

            # Exposure range
            try:
                caps.exposure_range = (node_map.ExposureTime.min, node_map.ExposureTime.max)
            except Exception:
                pass

            # LED power range
            try:
                caps.led_power_range = (node_map.LEDPower.min, node_map.LEDPower.max)
            except Exception:
                pass

            # Laser power range
            try:
                caps.laser_power_range = (node_map.LaserPower.min, node_map.LaserPower.max)
            except Exception:
                pass

            # FPS range
            try:
                caps.fps_range = (node_map.MaximumFPS.min, node_map.MaximumFPS.max)
            except Exception:
                pass

            # Device info
            caps.model = self._device_info.get("model", "") if self._device_info else ""
            caps.serial_number = self._device_info.get("serial_number", "") if self._device_info else ""

            return caps

        return await self._run_blocking(_get_caps)

    async def get_configuration(self) -> ScannerConfiguration:
        """Get current scanner configuration."""
        self._check_open()

        def _get_config():
            node_map = self._image_acquirer.remote_device.node_map
            config = ScannerConfiguration()

            # Operation settings
            try:
                config.operation_mode = OperationMode(node_map.OperationMode.value)
            except Exception:
                pass
            try:
                config.coding_strategy = CodingStrategy(node_map.CodingStrategy.value)
            except Exception:
                pass
            try:
                config.coding_quality = CodingQuality(node_map.CodingQuality.value)
            except Exception:
                pass
            try:
                config.maximum_fps = node_map.MaximumFPS.value
            except Exception:
                pass

            # Exposure settings
            try:
                config.exposure_time = node_map.ExposureTime.value
            except Exception:
                pass
            try:
                config.single_pattern_exposure = node_map.SinglePatternExposure.value
            except Exception:
                pass
            try:
                config.shutter_multiplier = node_map.ShutterMultiplier.value
            except Exception:
                pass
            try:
                config.scan_multiplier = node_map.ScanMultiplier.value
            except Exception:
                pass
            try:
                config.color_exposure = node_map.ColorSettings_Exposure.value
            except Exception:
                pass

            # Lighting settings
            try:
                config.led_power = node_map.LEDPower.value
            except Exception:
                pass
            try:
                config.laser_power = node_map.LaserPower.value
            except Exception:
                pass

            # Texture settings
            try:
                config.texture_source = TextureSource(node_map.TextureSource.value)
            except Exception:
                pass
            try:
                config.camera_texture_source = TextureSource(node_map.CameraTextureSource.value)
            except Exception:
                pass

            # Output settings
            try:
                config.output_topology = OutputTopology(node_map.OutputTopology.value)
            except Exception:
                pass
            try:
                config.camera_space = CameraSpace(node_map.CameraSpace.value)
            except Exception:
                pass

            # Processing settings
            try:
                config.normals_estimation_radius = node_map.NormalsEstimationRadius.value
            except Exception:
                pass
            try:
                config.max_inaccuracy = node_map.MaxInaccuracy.value
            except Exception:
                pass
            try:
                config.calibration_volume_only = node_map.CalibrationVolumeOnly.value
            except Exception:
                pass
            try:
                config.hole_filling = node_map.HoleFilling.value
            except Exception:
                pass

            # Trigger settings
            try:
                node_map.TriggerSelector.value = "FrameStart"
                if node_map.TriggerMode.value == "Off":
                    config.trigger_mode = TriggerMode.CONTINUOUS
                else:
                    config.trigger_mode = TriggerMode.SOFTWARE
            except Exception:
                pass
            try:
                config.hardware_trigger = node_map.HardwareTrigger.value
            except Exception:
                pass
            try:
                config.hardware_trigger_signal = HardwareTriggerSignal(node_map.HardwareTriggerSignal.value)
            except Exception:
                pass

            return config

        return await self._run_blocking(_get_config)

    async def set_configuration(self, config: ScannerConfiguration) -> None:
        """Apply scanner configuration."""
        self._check_open()

        def _set_config():
            node_map = self._image_acquirer.remote_device.node_map

            # Operation settings
            if config.operation_mode is not None:
                try:
                    node_map.OperationMode.value = config.operation_mode.value
                except Exception as e:
                    self.logger.warning(f"Failed to set operation_mode: {e}")

            if config.coding_strategy is not None:
                try:
                    node_map.CodingStrategy.value = config.coding_strategy.value
                except Exception as e:
                    self.logger.warning(f"Failed to set coding_strategy: {e}")

            if config.coding_quality is not None:
                try:
                    node_map.CodingQuality.value = config.coding_quality.value
                except Exception as e:
                    self.logger.warning(f"Failed to set coding_quality: {e}")

            if config.maximum_fps is not None:
                try:
                    node_map.MaximumFPS.value = config.maximum_fps
                except Exception as e:
                    self.logger.warning(f"Failed to set maximum_fps: {e}")

            # Exposure settings
            if config.exposure_time is not None:
                try:
                    node_map.ExposureTime.value = config.exposure_time
                except Exception as e:
                    self.logger.warning(f"Failed to set exposure_time: {e}")

            if config.single_pattern_exposure is not None:
                try:
                    node_map.SinglePatternExposure.value = config.single_pattern_exposure
                except Exception as e:
                    self.logger.warning(f"Failed to set single_pattern_exposure: {e}")

            if config.shutter_multiplier is not None:
                try:
                    node_map.ShutterMultiplier.value = config.shutter_multiplier
                except Exception as e:
                    self.logger.warning(f"Failed to set shutter_multiplier: {e}")

            if config.scan_multiplier is not None:
                try:
                    node_map.ScanMultiplier.value = config.scan_multiplier
                except Exception as e:
                    self.logger.warning(f"Failed to set scan_multiplier: {e}")

            if config.color_exposure is not None:
                try:
                    node_map.ColorSettings_Exposure.value = config.color_exposure
                except Exception as e:
                    self.logger.warning(f"Failed to set color_exposure: {e}")

            # Lighting settings
            if config.led_power is not None:
                try:
                    node_map.LEDPower.value = config.led_power
                except Exception as e:
                    self.logger.warning(f"Failed to set led_power: {e}")

            if config.laser_power is not None:
                try:
                    node_map.LaserPower.value = config.laser_power
                except Exception as e:
                    self.logger.warning(f"Failed to set laser_power: {e}")

            # Texture settings
            if config.texture_source is not None:
                try:
                    node_map.TextureSource.value = config.texture_source.value
                except Exception as e:
                    self.logger.warning(f"Failed to set texture_source: {e}")

            if config.camera_texture_source is not None:
                try:
                    node_map.CameraTextureSource.value = config.camera_texture_source.value
                except Exception as e:
                    self.logger.warning(f"Failed to set camera_texture_source: {e}")

            # Output settings
            if config.output_topology is not None:
                try:
                    node_map.OutputTopology.value = config.output_topology.value
                except Exception as e:
                    self.logger.warning(f"Failed to set output_topology: {e}")

            if config.camera_space is not None:
                try:
                    node_map.CameraSpace.value = config.camera_space.value
                except Exception as e:
                    self.logger.warning(f"Failed to set camera_space: {e}")

            # Processing settings
            if config.normals_estimation_radius is not None:
                try:
                    node_map.NormalsEstimationRadius.value = config.normals_estimation_radius
                except Exception as e:
                    self.logger.warning(f"Failed to set normals_estimation_radius: {e}")

            if config.max_inaccuracy is not None:
                try:
                    node_map.MaxInaccuracy.value = config.max_inaccuracy
                except Exception as e:
                    self.logger.warning(f"Failed to set max_inaccuracy: {e}")

            if config.calibration_volume_only is not None:
                try:
                    node_map.CalibrationVolumeOnly.value = config.calibration_volume_only
                except Exception as e:
                    self.logger.warning(f"Failed to set calibration_volume_only: {e}")

            if config.hole_filling is not None:
                try:
                    node_map.HoleFilling.value = config.hole_filling
                except Exception as e:
                    self.logger.warning(f"Failed to set hole_filling: {e}")

            # Trigger settings
            if config.trigger_mode is not None:
                try:
                    node_map.TriggerSelector.value = "FrameStart"
                    if config.trigger_mode == TriggerMode.CONTINUOUS:
                        node_map.TriggerMode.value = "Off"
                    else:
                        node_map.TriggerMode.value = "On"
                        node_map.TriggerSource.value = "Software"
                except Exception as e:
                    self.logger.warning(f"Failed to set trigger_mode: {e}")

            if config.hardware_trigger is not None:
                try:
                    node_map.HardwareTrigger.value = config.hardware_trigger
                except Exception as e:
                    self.logger.warning(f"Failed to set hardware_trigger: {e}")

            if config.hardware_trigger_signal is not None:
                try:
                    node_map.HardwareTriggerSignal.value = config.hardware_trigger_signal.value
                except Exception as e:
                    self.logger.warning(f"Failed to set hardware_trigger_signal: {e}")

        await self._run_blocking(_set_config)
        self.logger.info("Configuration applied")

    # -------------------------------------------------------------------------
    # Individual Configuration Methods
    # -------------------------------------------------------------------------

    async def set_exposure_time(self, milliseconds: float) -> None:
        """Set exposure time in milliseconds."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.ExposureTime.value = milliseconds

        await self._run_blocking(_set)

    async def get_exposure_time(self) -> float:
        """Get current exposure time in milliseconds."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.ExposureTime.value

        return await self._run_blocking(_get)

    async def set_operation_mode(self, mode: str) -> None:
        """Set scanner operation mode."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.OperationMode.value = mode

        await self._run_blocking(_set)

    async def get_operation_mode(self) -> str:
        """Get current operation mode."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.OperationMode.value

        return await self._run_blocking(_get)

    async def set_coding_strategy(self, strategy: str) -> None:
        """Set structured light coding strategy."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.CodingStrategy.value = strategy

        await self._run_blocking(_set)

    async def get_coding_strategy(self) -> str:
        """Get current coding strategy."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.CodingStrategy.value

        return await self._run_blocking(_get)

    async def set_coding_quality(self, quality: str) -> None:
        """Set scan quality/speed tradeoff."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.CodingQuality.value = quality

        await self._run_blocking(_set)

    async def get_coding_quality(self) -> str:
        """Get current coding quality."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.CodingQuality.value

        return await self._run_blocking(_get)

    async def set_led_power(self, power: int) -> None:
        """Set LED illumination power (0-4095)."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.LEDPower.value = power

        await self._run_blocking(_set)

    async def get_led_power(self) -> int:
        """Get current LED power level."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.LEDPower.value

        return await self._run_blocking(_get)

    async def set_laser_power(self, power: int) -> None:
        """Set laser/projector power (1-4095)."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.LaserPower.value = power

        await self._run_blocking(_set)

    async def get_laser_power(self) -> int:
        """Get current laser power level."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.LaserPower.value

        return await self._run_blocking(_get)

    async def set_texture_source(self, source: str) -> None:
        """Set texture/intensity data source."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.TextureSource.value = source

        await self._run_blocking(_set)

    async def get_texture_source(self) -> str:
        """Get current texture source."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.TextureSource.value

        return await self._run_blocking(_get)

    async def set_output_topology(self, topology: str) -> None:
        """Set point cloud output topology."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.OutputTopology.value = topology

        await self._run_blocking(_set)

    async def get_output_topology(self) -> str:
        """Get current output topology."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.OutputTopology.value

        return await self._run_blocking(_get)

    async def set_camera_space(self, space: str) -> None:
        """Set coordinate system reference camera."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.CameraSpace.value = space

        await self._run_blocking(_set)

    async def get_camera_space(self) -> str:
        """Get current camera space."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.CameraSpace.value

        return await self._run_blocking(_get)

    async def set_normals_estimation_radius(self, radius: int) -> None:
        """Set radius for surface normal estimation (0-4)."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.NormalsEstimationRadius.value = radius

        await self._run_blocking(_set)

    async def get_normals_estimation_radius(self) -> int:
        """Get current normals estimation radius."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.NormalsEstimationRadius.value

        return await self._run_blocking(_get)

    async def set_max_inaccuracy(self, value: float) -> None:
        """Set maximum allowed inaccuracy for point filtering (0-100)."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.MaxInaccuracy.value = value

        await self._run_blocking(_set)

    async def get_max_inaccuracy(self) -> float:
        """Get current max inaccuracy setting."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.MaxInaccuracy.value

        return await self._run_blocking(_get)

    async def set_hole_filling(self, enabled: bool) -> None:
        """Enable/disable hole filling in point cloud."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.HoleFilling.value = enabled

        await self._run_blocking(_set)

    async def get_hole_filling(self) -> bool:
        """Get hole filling state."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.HoleFilling.value

        return await self._run_blocking(_get)

    async def set_calibration_volume_only(self, enabled: bool) -> None:
        """Enable/disable filtering to calibration volume only."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.CalibrationVolumeOnly.value = enabled

        await self._run_blocking(_set)

    async def get_calibration_volume_only(self) -> bool:
        """Get calibration volume filtering state."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.CalibrationVolumeOnly.value

        return await self._run_blocking(_get)

    async def set_trigger_mode(self, mode: str) -> None:
        """Set trigger mode ('Software', 'Hardware', 'Continuous')."""
        self._check_open()

        def _set():
            node_map = self._image_acquirer.remote_device.node_map
            node_map.TriggerSelector.value = "FrameStart"

            if mode.lower() == "continuous":
                node_map.TriggerMode.value = "Off"
            else:
                node_map.TriggerMode.value = "On"
                node_map.TriggerSource.value = "Software"

        await self._run_blocking(_set)

    async def get_trigger_mode(self) -> str:
        """Get current trigger mode."""
        self._check_open()

        def _get():
            node_map = self._image_acquirer.remote_device.node_map
            node_map.TriggerSelector.value = "FrameStart"
            if node_map.TriggerMode.value == "Off":
                return "Continuous"
            return "Software"

        return await self._run_blocking(_get)

    async def set_hardware_trigger(self, enabled: bool) -> None:
        """Enable/disable hardware trigger."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.HardwareTrigger.value = enabled

        await self._run_blocking(_set)

    async def get_hardware_trigger(self) -> bool:
        """Get hardware trigger state."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.HardwareTrigger.value

        return await self._run_blocking(_get)

    async def set_maximum_fps(self, fps: float) -> None:
        """Set maximum frames per second (0-100)."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.MaximumFPS.value = fps

        await self._run_blocking(_set)

    async def get_maximum_fps(self) -> float:
        """Get current maximum FPS setting."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.MaximumFPS.value

        return await self._run_blocking(_get)

    async def set_shutter_multiplier(self, multiplier: int) -> None:
        """Set shutter multiplier (1-10)."""
        self._check_open()

        def _set():
            self._image_acquirer.remote_device.node_map.ShutterMultiplier.value = multiplier

        await self._run_blocking(_set)

    async def get_shutter_multiplier(self) -> int:
        """Get current shutter multiplier."""
        self._check_open()

        def _get():
            return self._image_acquirer.remote_device.node_map.ShutterMultiplier.value

        return await self._run_blocking(_get)

    # Properties
    @property
    def name(self) -> str:
        """Get scanner name."""
        if self._device_info:
            return f"Photoneo:{self._device_info.get('serial_number', 'unknown')}"
        return f"Photoneo:{self.serial_number or 'unknown'}"

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
        return f"PhotoneoBackend(name={self.name}, status={status})"
