"""Async stereo camera interface providing high-level stereo capture operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import cv2
import numpy as np

from mindtrace.core import Mindtrace
from mindtrace.hardware.core.exceptions import CameraConfigurationError, CameraConnectionError
from mindtrace.hardware.stereo_cameras.core.models import (
    PointCloudData,
    StereoCalibrationData,
    StereoGrabResult,
)

if TYPE_CHECKING:
    pass


class AsyncStereoCamera(Mindtrace):
    """Async stereo camera interface.

    Provides high-level stereo camera operations including multi-component capture
    and 3D point cloud generation.
    """

    def __init__(self, backend):
        """Initialize async stereo camera.

        Args:
            backend: Backend instance (e.g., BaslerStereoAceBackend)
        """
        super().__init__()
        self._backend = backend
        self._calibration: Optional[StereoCalibrationData] = None

    @classmethod
    async def open(cls, name: Optional[str] = None) -> "AsyncStereoCamera":
        """Open and initialize a stereo camera.

        Args:
            name: Camera identifier. Format: "BaslerStereoAce:serial_number"
                 If None, opens first available Stereo ace camera.

        Returns:
            Initialized AsyncStereoCamera instance

        Raises:
            CameraNotFoundError: If camera not found
            CameraConnectionError: If connection fails

        Examples:
            >>> camera = await AsyncStereoCamera.open()
            >>> camera = await AsyncStereoCamera.open("BaslerStereoAce:40644640")
        """
        # Parse name to extract serial number
        serial_number = None
        if name:
            if ":" in name:
                parts = name.split(":")
                if len(parts) == 2:
                    serial_number = parts[1]

        # Import backend (avoid circular import)
        from mindtrace.hardware.stereo_cameras.backends.basler.basler_stereo_ace import BaslerStereoAceBackend

        # Create backend
        backend = BaslerStereoAceBackend(serial_number=serial_number)

        # Initialize
        success = await backend.initialize()
        if not success:
            raise CameraConnectionError(f"Failed to open camera: {name or 'first available'}")

        # Create camera instance
        camera = cls(backend)
        camera._calibration = backend.calibration

        return camera

    # Lifecycle
    async def initialize(self) -> bool:
        """Initialize camera and load calibration.

        Returns:
            True if initialization successful

        Note:
            Usually not needed as open() handles initialization
        """
        success = await self._backend.initialize()
        if success:
            self._calibration = await self._backend.get_calibration()
        return success

    async def close(self) -> None:
        """Close camera and release resources."""
        await self._backend.close()

    # Capture operations
    async def capture(
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
            >>> result = await camera.capture()
            >>> print(f"Intensity: {result.intensity.shape}")
            >>> print(f"Disparity: {result.disparity.shape}")
        """
        return await self._backend.capture(
            timeout_ms=timeout_ms,
            enable_intensity=enable_intensity,
            enable_disparity=enable_disparity,
            calibrate_disparity=calibrate_disparity,
        )

    async def capture_point_cloud(
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
            >>> point_cloud = await camera.capture_point_cloud()
            >>> point_cloud.save_ply("output.ply")
            >>> pcd = point_cloud.to_open3d()
        """
        if self._calibration is None:
            raise CameraConfigurationError("Calibration data not available")

        # Capture stereo data
        result = await self.capture(enable_intensity=include_colors, enable_disparity=True, calibrate_disparity=True)

        # Generate point cloud
        point_cloud = self._generate_point_cloud(result, include_colors)

        # Post-processing
        if downsample_factor > 1:
            point_cloud = point_cloud.downsample(downsample_factor)

        if remove_outliers:
            point_cloud = point_cloud.remove_statistical_outliers()

        return point_cloud

    # Configuration
    async def configure(self, **params) -> None:
        """Configure camera parameters.

        Args:
            **params: Parameter name-value pairs

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If configuration fails

        Examples:
            >>> await camera.configure(ExposureTime=15000, Gain=2.0)
        """
        await self._backend.configure(**params)

    async def set_depth_range(self, min_depth: float, max_depth: float) -> None:
        """Set depth measurement range in meters.

        Args:
            min_depth: Minimum depth (e.g., 0.3 meters)
            max_depth: Maximum depth (e.g., 5.0 meters)

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> await camera.set_depth_range(0.5, 3.0)
        """
        await self._backend.set_depth_range(min_depth, max_depth)

    async def set_illumination_mode(self, mode: str) -> None:
        """Set illumination mode.

        Args:
            mode: 'AlwaysActive' (low latency) or 'AlternateActive' (clean intensity)

        Raises:
            CameraConfigurationError: If invalid mode or configuration fails

        Examples:
            >>> await camera.set_illumination_mode("AlternateActive")
        """
        await self._backend.set_illumination_mode(mode)

    async def set_binning(self, horizontal: int = 2, vertical: int = 2) -> None:
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
            >>> await camera.set_binning(2, 2)
            >>> await camera.set_depth_quality("Full")  # Recommended for low latency
        """
        await self._backend.set_binning(horizontal, vertical)

    async def set_depth_quality(self, quality: str) -> None:
        """Set depth quality level.

        Args:
            quality: Depth quality setting. Common values:
                    - "Full": Highest quality, recommended with binning
                    - "Normal": Standard quality
                    - "Low": Lower quality, faster processing

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> # Low latency configuration
            >>> await camera.set_binning(2, 2)
            >>> await camera.set_depth_quality("Full")
        """
        await self._backend.set_depth_quality(quality)

    async def set_pixel_format(self, format: str) -> None:
        """Set pixel format for intensity component.

        Args:
            format: Pixel format ("RGB8", "Mono8", etc.)

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If format not available or configuration fails

        Examples:
            >>> await camera.set_pixel_format("Mono8")  # Force grayscale
        """
        await self._backend.set_pixel_format(format)

    async def set_exposure_time(self, microseconds: float) -> None:
        """Set exposure time in microseconds.

        Args:
            microseconds: Exposure time in microseconds (e.g., 5000 = 5ms)

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> await camera.set_exposure_time(5000)  # 5ms exposure
        """
        await self._backend.set_exposure_time(microseconds)

    async def set_gain(self, gain: float) -> None:
        """Set camera gain.

        Args:
            gain: Gain value (typically 0.0 to 24.0, camera-dependent)

        Raises:
            CameraConfigurationError: If configuration fails

        Examples:
            >>> await camera.set_gain(2.0)
        """
        await self._backend.set_gain(gain)

    async def get_exposure_time(self) -> float:
        """Get current exposure time in microseconds.

        Returns:
            Current exposure time in microseconds

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> exposure = await camera.get_exposure_time()
            >>> print(f"Exposure: {exposure}μs")
        """
        return await self._backend.get_exposure_time()

    async def get_gain(self) -> float:
        """Get current camera gain.

        Returns:
            Current gain value

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> gain = await camera.get_gain()
            >>> print(f"Gain: {gain}")
        """
        return await self._backend.get_gain()

    async def get_depth_quality(self) -> str:
        """Get current depth quality setting.

        Returns:
            Current depth quality level (e.g., "Full", "Normal", "Low")

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> quality = await camera.get_depth_quality()
            >>> print(f"Quality: {quality}")
        """
        return await self._backend.get_depth_quality()

    async def get_pixel_format(self) -> str:
        """Get current pixel format.

        Returns:
            Current pixel format (e.g., "RGB8", "Mono8", "Coord3D_C16")

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> format = await camera.get_pixel_format()
            >>> print(f"Format: {format}")
        """
        return await self._backend.get_pixel_format()

    async def get_binning(self) -> tuple[int, int]:
        """Get current binning settings.

        Returns:
            Tuple of (horizontal_binning, vertical_binning)

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> h_bin, v_bin = await camera.get_binning()
            >>> print(f"Binning: {h_bin}x{v_bin}")
        """
        return await self._backend.get_binning()

    async def get_illumination_mode(self) -> str:
        """Get current illumination mode.

        Returns:
            Current illumination mode ("AlwaysActive" or "AlternateActive")

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> mode = await camera.get_illumination_mode()
            >>> print(f"Illumination: {mode}")
        """
        return await self._backend.get_illumination_mode()

    async def get_depth_range(self) -> tuple[float, float]:
        """Get current depth measurement range in meters.

        Returns:
            Tuple of (min_depth, max_depth) in meters

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> min_d, max_d = await camera.get_depth_range()
            >>> print(f"Range: {min_d}m - {max_d}m")
        """
        return await self._backend.get_depth_range()

    async def set_trigger_mode(self, mode: str) -> None:
        """Set trigger mode (simplified interface).

        Args:
            mode: Trigger mode ("continuous" or "trigger")
                 - "continuous": Free-running continuous acquisition
                 - "trigger": Software-triggered acquisition

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If invalid mode or configuration fails

        Examples:
            >>> await camera.set_trigger_mode("continuous")  # Free running
            >>> await camera.set_trigger_mode("trigger")     # Software triggered
        """
        await self._backend.set_trigger_mode(mode)

    async def get_trigger_mode(self) -> str:
        """Get current trigger mode (simplified interface).

        Returns:
            "continuous" or "trigger"

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> mode = await camera.get_trigger_mode()
            >>> print(f"Current mode: {mode}")
        """
        return await self._backend.get_trigger_mode()

    async def get_trigger_modes(self) -> list[str]:
        """Get available trigger modes.

        Returns:
            List of supported trigger modes: ["continuous", "trigger"]

        Examples:
            >>> modes = await camera.get_trigger_modes()
            >>> print(f"Available modes: {modes}")
        """
        return await self._backend.get_trigger_modes()

    async def start_grabbing(self) -> None:
        """Start grabbing frames.

        Must be called after enable_software_trigger() and before execute_trigger().

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> await camera.enable_software_trigger()
            >>> await camera.start_grabbing()
            >>> for i in range(10):
            ...     await camera.execute_trigger()
            ...     result = await camera.capture()
        """
        await self._backend.start_grabbing()

    async def execute_trigger(self) -> None:
        """Execute software trigger.

        Triggers a frame capture when in software trigger mode.
        Note: start_grabbing() must be called first after enabling software trigger.

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If trigger execution fails

        Examples:
            >>> await camera.enable_software_trigger()
            >>> await camera.start_grabbing()
            >>> for i in range(10):
            ...     await camera.execute_trigger()
            ...     result = await camera.capture()
        """
        await self._backend.execute_trigger()

    # Properties
    @property
    def name(self) -> str:
        """Get camera name."""
        return self._backend.name

    @property
    def calibration(self) -> Optional[StereoCalibrationData]:
        """Get calibration data."""
        return self._calibration

    @property
    def is_open(self) -> bool:
        """Check if camera is open."""
        return self._backend.is_open

    # Point cloud generation
    def _generate_point_cloud(self, result: StereoGrabResult, include_colors: bool) -> PointCloudData:
        """Generate point cloud from grab result.

        Args:
            result: Stereo grab result
            include_colors: Whether to include color information

        Returns:
            PointCloudData with 3D points

        Raises:
            CameraConfigurationError: If disparity data or calibration missing
        """
        if not result.has_disparity or result.disparity is None:
            raise CameraConfigurationError("Disparity data required for point cloud generation")

        if self._calibration is None:
            raise CameraConfigurationError("Calibration data required for point cloud generation")

        # Use calibrated disparity if available, otherwise calibrate now
        if result.disparity_calibrated is not None:
            disp_cal = result.disparity_calibrated
        else:
            disp_cal = self._calibration.calibrate_disparity(result.disparity)

        # Reproject to 3D using Q matrix
        points_3d = cv2.reprojectImageTo3D(disp_cal, self._calibration.Q)

        # Prepare colors if requested
        colors = None
        if include_colors and result.has_intensity and result.intensity is not None:
            # Resize intensity to match disparity resolution
            h, w = result.disparity.shape
            intensity_resized = cv2.resize(result.intensity, (w, h), interpolation=cv2.INTER_LINEAR)

            # Convert grayscale to RGB if needed
            if intensity_resized.ndim == 2:
                colors = cv2.cvtColor(intensity_resized, cv2.COLOR_GRAY2RGB)
            else:
                colors = intensity_resized

            # Normalize to [0, 1] and flatten
            colors = colors.reshape(-1, 3).astype(np.float64) / 255.0

        # Flatten points
        points = points_3d.reshape(-1, 3).astype(np.float64)

        # Remove invalid points (infinite/NaN from zero disparity)
        valid = np.isfinite(points).all(axis=1)
        points = points[valid]

        if colors is not None:
            colors = colors[valid]

        return PointCloudData(points=points, colors=colors, num_points=len(points), has_colors=(colors is not None))

    def __repr__(self) -> str:
        """String representation."""
        status = "open" if self.is_open else "closed"
        return f"AsyncStereoCamera(name={self.name}, status={status})"
