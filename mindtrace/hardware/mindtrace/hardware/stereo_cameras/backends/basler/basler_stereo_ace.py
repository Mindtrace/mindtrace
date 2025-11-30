"""Basler Stereo ace camera backend using pypylon.

This backend provides access to Basler Stereo ace cameras which combine two ace2 Pro
cameras with a pattern projector into a unified stereo vision system.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from mindtrace.core import Mindtrace
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraNotFoundError,
    SDKNotAvailableError,
)
from mindtrace.hardware.stereo_cameras.core.models import StereoCalibrationData, StereoGrabResult

try:
    from pypylon import pylon

    PYPYLON_AVAILABLE = True
except ImportError:
    PYPYLON_AVAILABLE = False


class BaslerStereoAceBackend(Mindtrace):
    """Backend for Basler Stereo ace cameras using pypylon.

    The Stereo ace camera is accessed through a unified device interface
    (DeviceClass: BaslerGTC/Basler/basler_xw) that presents the stereo pair
    as a single camera with multi-component output.
    """

    DEVICE_CLASS = "BaslerGTC/Basler/basler_xw"

    def __init__(self, serial_number: Optional[str] = None):
        """Initialize Basler Stereo ace backend.

        Args:
            serial_number: Serial number or user-defined name of specific camera.
                          If all digits, treated as serial number.
                          Otherwise, treated as user-defined name.
                          If None, opens first available Stereo ace camera.

        Raises:
            SDKNotAvailableError: If pypylon is not available
        """
        super().__init__()

        if not PYPYLON_AVAILABLE:
            raise SDKNotAvailableError("pypylon not available. Install with: pip install pypylon")

        self.serial_number = serial_number
        self._camera: Optional[pylon.InstantCamera] = None
        self._is_open = False
        self._grab_strategy = pylon.GrabStrategy_LatestImageOnly
        self._calibration: Optional[StereoCalibrationData] = None

    @staticmethod
    def discover() -> List[str]:
        """Discover available Stereo ace cameras.

        Returns:
            List of serial numbers for available Stereo ace cameras

        Raises:
            SDKNotAvailableError: If pypylon is not available
        """
        if not PYPYLON_AVAILABLE:
            raise SDKNotAvailableError("pypylon not available. Install with: pip install pypylon")

        # Create device info filter for Stereo ace cameras
        di = pylon.DeviceInfo()
        di.SetDeviceClass(BaslerStereoAceBackend.DEVICE_CLASS)

        # Enumerate devices with filter
        tl_factory = pylon.TlFactory.GetInstance()
        devices = tl_factory.EnumerateDevices([di])

        return [dev.GetSerialNumber() for dev in devices]

    @staticmethod
    def discover_detailed() -> List[Dict[str, str]]:
        """Discover Stereo ace cameras with detailed information.

        Returns:
            List of dictionaries containing camera information

        Raises:
            SDKNotAvailableError: If pypylon is not available
        """
        if not PYPYLON_AVAILABLE:
            raise SDKNotAvailableError("pypylon not available. Install with: pip install pypylon")

        # Create device info filter for Stereo ace cameras
        di = pylon.DeviceInfo()
        di.SetDeviceClass(BaslerStereoAceBackend.DEVICE_CLASS)

        # Enumerate devices with filter
        tl_factory = pylon.TlFactory.GetInstance()
        devices = tl_factory.EnumerateDevices([di])

        camera_list = []
        for dev in devices:
            camera_list.append(
                {
                    "serial_number": dev.GetSerialNumber(),
                    "model_name": dev.GetModelName(),
                    "friendly_name": dev.GetFriendlyName(),
                    "device_class": dev.GetDeviceClass(),
                }
            )

        return camera_list

    async def initialize(self) -> bool:
        """Initialize camera connection.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            di = pylon.DeviceInfo()
            di.SetDeviceClass(self.DEVICE_CLASS)

            if self.serial_number:
                # Check if it's a serial number (all digits) or user-defined name
                if self.serial_number.isdigit():
                    di.SetSerialNumber(self.serial_number)
                else:
                    di.SetUserDefinedName(self.serial_number)

            tl_factory = pylon.TlFactory.GetInstance()

            try:
                self._camera = pylon.InstantCamera(tl_factory.CreateFirstDevice(di))
            except Exception as e:
                if self.serial_number:
                    raise CameraNotFoundError(f"Stereo ace camera '{self.serial_number}' not found") from e
                else:
                    raise CameraNotFoundError("No Stereo ace cameras found") from e

            self._camera.Open()
            self._is_open = True

            # Set default configuration
            await self._set_default_config()

            # Load calibration
            self._calibration = await self.get_calibration()

            self.logger.info(
                f"Opened Stereo ace: {self._camera.GetDeviceInfo().GetModelName()} "
                f"(SN: {self._camera.GetDeviceInfo().GetSerialNumber()})"
            )
            return True

        except CameraNotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Stereo ace camera: {e}")
            raise CameraConnectionError(f"Failed to initialize: {e}") from e

    async def _set_default_config(self) -> None:
        """Set default stereo camera configuration from hardware config."""
        try:
            # Load config
            from mindtrace.hardware.core.config import get_hardware_config

            hw_config = get_hardware_config().get_config()
            stereo_config = hw_config.stereo_cameras

            # Enable both components by default
            self._camera.ComponentSelector.Value = "Intensity"
            self._camera.ComponentEnable.Value = True
            self._camera.ComponentSelector.Value = "Disparity"
            self._camera.ComponentEnable.Value = True

            # Set default depth range from config
            self._camera.BslDepthMinDepth.Value = stereo_config.depth_range_min
            self._camera.BslDepthMaxDepth.Value = stereo_config.depth_range_max

            # Set illumination mode from config
            self._camera.BslIlluminationMode.Value = stereo_config.illumination_mode

            self.logger.debug(
                f"Applied default stereo camera configuration: "
                f"depth_range=[{stereo_config.depth_range_min}, {stereo_config.depth_range_max}], "
                f"illumination={stereo_config.illumination_mode}"
            )

        except Exception as e:
            self.logger.warning(f"Failed to set default configuration: {e}")

    async def get_calibration(self) -> StereoCalibrationData:
        """Get factory calibration parameters from camera.

        Returns:
            StereoCalibrationData with factory calibration

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If calibration cannot be read
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        try:
            params = {
                "Scan3dBaseline": self._camera.Scan3dBaseline.GetValue(),
                "Scan3dFocalLength": self._camera.Scan3dFocalLength.GetValue(),
                "Scan3dPrincipalPointU": self._camera.Scan3dPrincipalPointU.GetValue(),
                "Scan3dPrincipalPointV": self._camera.Scan3dPrincipalPointV.GetValue(),
                "Scan3dCoordinateScale": self._camera.Scan3dCoordinateScale.GetValue(),
                "Scan3dCoordinateOffset": self._camera.Scan3dCoordinateOffset.GetValue(),
            }

            calibration = StereoCalibrationData.from_camera_params(params)
            self.logger.debug(f"Loaded calibration: {calibration}")
            return calibration

        except Exception as e:
            raise CameraConfigurationError(f"Failed to read calibration: {e}") from e

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
            enable_intensity: Whether to capture intensity data
            enable_disparity: Whether to capture disparity data
            calibrate_disparity: Whether to apply calibration to disparity

        Returns:
            StereoGrabResult containing captured data

        Raises:
            CameraConnectionError: If camera not opened
            CameraCaptureError: If capture fails
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        try:
            # Start grabbing if not already
            if not self._camera.IsGrabbing():
                self._camera.StartGrabbing(self._grab_strategy)

            # Retrieve result
            grab_result = self._camera.RetrieveResult(timeout_ms, pylon.TimeoutHandling_ThrowException)

            try:
                if not grab_result.GrabSucceeded():
                    raise CameraCaptureError(f"Grab failed: {grab_result.ErrorCode} - {grab_result.ErrorDescription}")

                # Extract components
                container = grab_result.GetDataContainer()
                intensity_data = None
                disparity_data = None
                has_intensity = False
                has_disparity = False

                for i in range(container.DataComponentCount):
                    component = container.GetDataComponent(i)

                    if component.ComponentType == pylon.ComponentType_Intensity and enable_intensity:
                        if component.GetPixelType() == pylon.PixelType_RGB8packed:
                            # RGB8
                            intensity_data = component.Array.reshape(component.Height, component.Width, 3)
                        else:
                            # Mono8
                            intensity_data = component.Array.reshape(component.Height, component.Width)
                        has_intensity = True

                    elif component.ComponentType == pylon.ComponentType_Disparity and enable_disparity:
                        disparity_data = component.Array.reshape(component.Height, component.Width)
                        has_disparity = True

                # Apply calibration if requested
                disparity_calibrated = None
                if calibrate_disparity and has_disparity and disparity_data is not None and self._calibration:
                    disparity_calibrated = self._calibration.calibrate_disparity(disparity_data)

                return StereoGrabResult(
                    intensity=intensity_data,
                    disparity=disparity_data,
                    timestamp=grab_result.TimeStamp / 1e9,  # ns -> s
                    frame_number=grab_result.ImageNumber,
                    disparity_calibrated=disparity_calibrated,
                    has_intensity=has_intensity,
                    has_disparity=has_disparity,
                )

            finally:
                grab_result.Release()

        except CameraCaptureError:
            raise
        except Exception as e:
            raise CameraCaptureError(f"Capture failed: {e}") from e

    async def configure(self, **params) -> None:
        """Configure camera parameters.

        Args:
            **params: Parameter name-value pairs to configure. Special parameters:
                     - trigger_mode: "continuous" or "trigger"
                     - depth_range: tuple of (min_depth, max_depth)
                     - illumination_mode: "AlwaysActive" or "AlternateActive"
                     - binning: tuple of (horizontal, vertical)
                     - depth_quality: "Full", "High", "Normal", or "Low"
                     - All other parameters passed directly to camera

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If configuration fails
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        configured = []
        failed = []

        # Handle special parameters first
        special_params = {}

        if "trigger_mode" in params:
            special_params["trigger_mode"] = params.pop("trigger_mode")
        if "depth_range" in params:
            special_params["depth_range"] = params.pop("depth_range")
        if "illumination_mode" in params:
            special_params["illumination_mode"] = params.pop("illumination_mode")
        if "binning" in params:
            special_params["binning"] = params.pop("binning")
        if "depth_quality" in params:
            special_params["depth_quality"] = params.pop("depth_quality")

        # Handle special parameters
        for key, value in special_params.items():
            try:
                if key == "trigger_mode":
                    await self.set_trigger_mode(value)
                elif key == "depth_range":
                    await self.set_depth_range(value[0], value[1])
                elif key == "illumination_mode":
                    await self.set_illumination_mode(value)
                elif key == "binning":
                    await self.set_binning(value[0], value[1])
                elif key == "depth_quality":
                    await self.set_depth_quality(value)
                configured.append(key)
            except Exception as e:
                failed.append((key, str(e)))

        # Handle remaining parameters
        for key, value in params.items():
            try:
                if hasattr(self._camera, key):
                    param = getattr(self._camera, key)
                    if hasattr(param, "Value"):
                        param.Value = value
                        configured.append(key)
                    else:
                        failed.append((key, "not writable"))
                else:
                    failed.append((key, "not found"))
            except Exception as e:
                failed.append((key, str(e)))

        if configured:
            self.logger.debug(f"Configured parameters: {', '.join(configured)}")

        if failed:
            self.logger.warning(f"Failed to configure: {dict(failed)}")

    async def set_depth_range(self, min_depth: float, max_depth: float) -> None:
        """Set depth measurement range.

        Args:
            min_depth: Minimum depth in meters (e.g., 0.3)
            max_depth: Maximum depth in meters (e.g., 5.0)

        Raises:
            CameraConfigurationError: If configuration fails
        """
        await self.configure(BslDepthMinDepth=min_depth, BslDepthMaxDepth=max_depth)

    async def set_illumination_mode(self, mode: str) -> None:
        """Set illumination mode.

        Args:
            mode: 'AlwaysActive' (low latency) or 'AlternateActive' (clean intensity)

        Raises:
            CameraConfigurationError: If configuration fails
        """
        if mode not in ["AlwaysActive", "AlternateActive"]:
            raise CameraConfigurationError(f"Invalid illumination mode: {mode}")
        await self.configure(BslIlluminationMode=mode)

    async def set_binning(self, horizontal: int = 2, vertical: int = 2) -> None:
        """Enable binning for latency reduction.

        Args:
            horizontal: Horizontal binning factor (typically 2)
            vertical: Vertical binning factor (typically 2)

        Note:
            When using binning for low latency, consider also setting
            depth quality to "Full" using set_depth_quality("Full").

        Raises:
            CameraConfigurationError: If configuration fails
        """
        await self.configure(BinningHorizontal=horizontal, BinningVertical=vertical)

    async def set_depth_quality(self, quality: str) -> None:
        """Set depth quality level.

        Args:
            quality: Depth quality setting. Common values:
                    - "Full": Highest quality, recommended with binning
                    - "Normal": Standard quality
                    - "Low": Lower quality, faster processing

        Note:
            Setting quality to "Full" with binning reduces latency while
            maintaining depth quality. This is recommended for low-latency
            applications.

        Raises:
            CameraConfigurationError: If configuration fails

        Example:
            # Low latency configuration
            await camera.set_binning(2, 2)
            await camera.set_depth_quality("Full")
        """
        await self.configure(BslDepthQuality=quality)

    async def set_pixel_format(self, format: str) -> None:
        """Set pixel format for intensity component.

        Args:
            format: Pixel format ("RGB8", "Mono8", etc.)

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If format not available or configuration fails

        Example:
            await camera.set_pixel_format("Mono8")  # Force grayscale
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        try:
            # Check if format is available
            available_formats = self._camera.PixelFormat.GetSymbolics()
            if format not in available_formats:
                raise CameraConfigurationError(
                    f"Pixel format '{format}' not available. Available formats: {', '.join(available_formats)}"
                )

            self._camera.PixelFormat.Value = format
        except CameraConfigurationError:
            raise
        except Exception as e:
            raise CameraConfigurationError(f"Failed to set pixel format: {e}") from e

    async def set_exposure_time(self, microseconds: float) -> None:
        """Set exposure time in microseconds.

        Args:
            microseconds: Exposure time in microseconds (e.g., 5000 = 5ms)

        Raises:
            CameraConfigurationError: If configuration fails

        Example:
            await camera.set_exposure_time(5000)  # 5ms exposure
        """
        await self.configure(ExposureTime=microseconds)

    async def set_gain(self, gain: float) -> None:
        """Set camera gain.

        Args:
            gain: Gain value (typically 0.0 to 24.0, camera-dependent)

        Raises:
            CameraConfigurationError: If configuration fails

        Example:
            await camera.set_gain(2.0)
        """
        await self.configure(Gain=gain)

    async def get_exposure_time(self) -> float:
        """Get current exposure time in microseconds.

        Returns:
            Current exposure time in microseconds

        Raises:
            CameraConnectionError: If camera not opened

        Example:
            exposure = await camera.get_exposure_time()
            print(f"Current exposure: {exposure}μs")
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        return float(self._camera.ExposureTime.Value)

    async def get_gain(self) -> float:
        """Get current camera gain.

        Returns:
            Current gain value

        Raises:
            CameraConnectionError: If camera not opened

        Example:
            gain = await camera.get_gain()
            print(f"Current gain: {gain}")
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        return float(self._camera.Gain.Value)

    async def get_depth_quality(self) -> str:
        """Get current depth quality setting.

        Returns:
            Current depth quality level (e.g., "Full", "Normal", "Low")

        Raises:
            CameraConnectionError: If camera not opened

        Example:
            quality = await camera.get_depth_quality()
            print(f"Depth quality: {quality}")
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        return str(self._camera.BslDepthQuality.Value)

    async def get_pixel_format(self) -> str:
        """Get current pixel format.

        Returns:
            Current pixel format (e.g., "RGB8", "Mono8", "Coord3D_C16")

        Raises:
            CameraConnectionError: If camera not opened

        Example:
            format = await camera.get_pixel_format()
            print(f"Pixel format: {format}")
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        return str(self._camera.PixelFormat.Value)

    async def get_binning(self) -> tuple[int, int]:
        """Get current binning settings.

        Returns:
            Tuple of (horizontal_binning, vertical_binning)

        Raises:
            CameraConnectionError: If camera not opened

        Example:
            h_bin, v_bin = await camera.get_binning()
            print(f"Binning: {h_bin}x{v_bin}")
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        h_bin = int(self._camera.BinningHorizontal.Value)
        v_bin = int(self._camera.BinningVertical.Value)
        return (h_bin, v_bin)

    async def get_illumination_mode(self) -> str:
        """Get current illumination mode.

        Returns:
            Current illumination mode ("AlwaysActive" or "AlternateActive")

        Raises:
            CameraConnectionError: If camera not opened

        Example:
            mode = await camera.get_illumination_mode()
            print(f"Illumination: {mode}")
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        return str(self._camera.BslIlluminationMode.Value)

    async def get_depth_range(self) -> tuple[float, float]:
        """Get current depth measurement range in meters.

        Returns:
            Tuple of (min_depth, max_depth) in meters

        Raises:
            CameraConnectionError: If camera not opened

        Example:
            min_d, max_d = await camera.get_depth_range()
            print(f"Depth range: {min_d}m - {max_d}m")
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        min_depth = float(self._camera.BslDepthMinDepth.Value)
        max_depth = float(self._camera.BslDepthMaxDepth.Value)
        return (min_depth, max_depth)

    async def set_trigger_mode(self, mode: str) -> None:
        """Set trigger mode (simplified interface).

        Args:
            mode: Trigger mode ("continuous" or "trigger")
                 - "continuous": Free-running continuous acquisition (TriggerMode=Off)
                 - "trigger": Software-triggered acquisition (TriggerMode=On, TriggerSource=Software)

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If invalid mode or configuration fails

        Examples:
            >>> await backend.set_trigger_mode("continuous")  # Free running
            >>> await backend.set_trigger_mode("trigger")     # Software triggered
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        if mode not in ["continuous", "trigger"]:
            raise CameraConfigurationError(f"Invalid trigger mode '{mode}'. Must be 'continuous' or 'trigger'")

        if mode == "continuous":
            # Disable triggering - free running mode
            await self.configure(TriggerMode="Off")
        else:
            # Enable software triggering
            await self.configure(TriggerSelector="FrameStart", TriggerMode="On", TriggerSource="Software")

    async def get_trigger_mode(self) -> str:
        """Get current trigger mode (simplified interface).

        Returns:
            "continuous" if TriggerMode is Off, "trigger" if TriggerMode is On with Software source

        Raises:
            CameraConnectionError: If camera not opened

        Examples:
            >>> mode = await backend.get_trigger_mode()
            >>> print(f"Current mode: {mode}")
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        try:
            trigger_enabled = self._camera.TriggerMode.Value == "On"
            trigger_source = self._camera.TriggerSource.Value == "Software"

            return "trigger" if (trigger_enabled and trigger_source) else "continuous"
        except Exception as e:
            raise CameraConfigurationError(f"Failed to get trigger mode: {e}") from e

    async def get_trigger_modes(self) -> List[str]:
        """Get available trigger modes.

        Returns:
            List of supported trigger modes: ["continuous", "trigger"]

        Note:
            This provides a simplified interface. The underlying camera supports
            additional modes (SingleFrame, MultiFrame, hardware triggers) accessible
            via direct configure() calls if needed.
        """
        return ["continuous", "trigger"]

    async def start_grabbing(self) -> None:
        """Start grabbing frames.

        This must be called before execute_trigger() in software trigger mode.

        Raises:
            CameraConnectionError: If camera not opened
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        if not self._camera.IsGrabbing():
            self._camera.StartGrabbing(self._grab_strategy)

    async def execute_trigger(self) -> None:
        """Execute software trigger.

        Note: In software trigger mode, ensure start_grabbing() is called first,
        or call capture() once before the trigger loop to start grabbing.

        Raises:
            CameraConnectionError: If camera not opened
            CameraConfigurationError: If trigger execution fails
        """
        if not self._is_open or self._camera is None:
            raise CameraConnectionError("Camera not opened")

        try:
            self._camera.TriggerSoftware.Execute()
        except Exception as e:
            raise CameraConfigurationError(f"Failed to execute trigger: {e}") from e

    async def close(self) -> None:
        """Close camera and release resources."""
        if self._camera and self._is_open:
            try:
                if self._camera.IsGrabbing():
                    self._camera.StopGrabbing()
                self._camera.Close()
                self._is_open = False
                self.logger.info("Closed Stereo ace camera")
            except Exception as e:
                self.logger.error(f"Error closing camera: {e}")

    @property
    def name(self) -> str:
        """Get camera name."""
        if self._camera and self._is_open:
            return f"BaslerStereoAce:{self._camera.GetDeviceInfo().GetSerialNumber()}"
        return f"BaslerStereoAce:{self.serial_number or 'unknown'}"

    @property
    def is_open(self) -> bool:
        """Check if camera is open."""
        return self._is_open

    @property
    def calibration(self) -> Optional[StereoCalibrationData]:
        """Get calibration data."""
        return self._calibration
