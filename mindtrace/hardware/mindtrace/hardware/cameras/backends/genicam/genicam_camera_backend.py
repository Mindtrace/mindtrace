"""GenICam Camera Backend Module"""

import asyncio
import os
import platform
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

try:
    from harvesters.core import Harvester

    HARVESTERS_AVAILABLE = True
    GENICAM_AVAILABLE = True

    # Optional PFNC imports - not critical for basic functionality
    try:
        from harvesters.util.pfnc import PFNC_VERSION_1_0, PFNC_VERSION_2_0, PFNC_VERSION_2_1  # noqa: F401
    except ImportError:
        pass  # PFNC constants not available in this version

except ImportError:  # pragma: no cover
    HARVESTERS_AVAILABLE = False
    GENICAM_AVAILABLE = False
    Harvester = None

from mindtrace.hardware.cameras.backends.camera_backend import CameraBackend
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
    CameraTimeoutError,
    HardwareOperationError,
    SDKNotAvailableError,
)


class GenICamCameraBackend(CameraBackend):
    """GenICam Camera Backend Implementation

    This class provides a comprehensive implementation for GenICam-compliant cameras using the Harvesters library
    with Matrix Vision GenTL Producer. It supports advanced camera features including trigger modes, exposure control,
    ROI settings, and image quality enhancement.

    Thread Safety:
        Uses a singleton Harvester instance shared across all backend instances to avoid GenTL device conflicts.
        Multiple cameras can be opened simultaneously using the same Harvester.

    Features:
        - Full GenICam camera support via Harvesters
        - Matrix Vision GenTL Producer integration
        - Hardware trigger and continuous capture modes
        - ROI (Region of Interest) control
        - Automatic exposure and gain control
        - Image quality enhancement with CLAHE
        - Configuration import/export functionality
        - Robust error handling and connection management
        - Vendor-specific parameter handling (Keyence, Basler, etc.)

    Requirements:
        - Harvesters library (pip install harvesters)
        - Matrix Vision mvIMPACT Acquire SDK
        - OpenCV for image processing
        - GenTL Producer (.cti file) installed on system

    Installation:
        1. Install Matrix Vision mvIMPACT Acquire SDK
        2. pip install harvesters opencv-python numpy
        3. Configure network interface for GigE cameras
        4. Set GENICAM_CTI_PATH environment variable (optional)

    Usage::

        from mindtrace.hardware.cameras.backends.genicam import GenICamCameraBackend

        # Get available cameras
        cameras = GenICamCameraBackend.get_available_cameras()

        # Initialize camera
        camera = GenICamCameraBackend("device_serial", img_quality_enhancement=True)
        success, cam_obj, remote_obj = await camera.initialize()

        if success:
            # Configure and capture
            await camera.set_exposure(50000)
            await camera.set_triggermode("continuous")
            image = await camera.capture()
            await camera.close()

    Configuration:
        All parameters are configurable via environment variables or the hardware configuration system:
        - GENICAM_CTI_PATH: Path to GenTL Producer (.cti file)
        - MINDTRACE_CAMERA_EXPOSURE_TIME: Default exposure time in microseconds
        - MINDTRACE_CAMERA_TRIGGER_MODE: Default trigger mode ("continuous" or "trigger")
        - MINDTRACE_CAMERA_IMAGE_QUALITY_ENHANCEMENT: Enable CLAHE enhancement
        - MINDTRACE_CAMERA_RETRIEVE_RETRY_COUNT: Number of capture retry attempts
        - MINDTRACE_CAMERA_TIMEOUT_MS: Capture timeout in milliseconds

    Supported Camera Models:
        - Keyence VJ series cameras
        - Basler GigE cameras (alternative to pypylon)
        - Allied Vision cameras
        - FLIR/Teledyne cameras
        - Any GenICam-compliant camera with compatible GenTL Producer

    Error Handling:
        The class uses a comprehensive exception hierarchy for precise error reporting:
        - SDKNotAvailableError: Harvesters library not installed
        - CameraNotFoundError: Camera not detected or accessible
        - CameraInitializationError: Failed to initialize camera
        - CameraConfigurationError: Invalid configuration parameters
        - CameraConnectionError: Connection issues
        - CameraCaptureError: Image acquisition failures
        - CameraTimeoutError: Operation timeout
        - HardwareOperationError: General hardware operation failures

    Attributes:
        initialized: Whether camera was successfully initialized
        image_acquirer: Harvesters ImageAcquirer object
        harvester: Harvesters Harvester object
        triggermode: Current trigger mode ("continuous" or "trigger")
        img_quality_enhancement: Current image enhancement setting
        timeout_ms: Capture timeout in milliseconds
        retrieve_retry_count: Number of capture retry attempts
        device_info: Camera device information from discovery
        vendor_quirks: Vendor-specific parameter handling flags
        cti_path: Path to GenTL Producer file
    """

    # Class-level singleton Harvester instance shared across all backend instances
    _shared_harvester: Optional[Harvester] = None
    _harvester_cti_path: Optional[str] = None
    _harvester_lock = None  # Will be initialized as threading.Lock() when first needed

    def __init__(
        self,
        camera_name: str,
        camera_config: Optional[str] = None,
        img_quality_enhancement: Optional[bool] = None,
        retrieve_retry_count: Optional[int] = None,
        **backend_kwargs,
    ):
        """Initialize GenICam camera with configurable parameters.

        Args:
            camera_name: Camera identifier (serial number, device ID, or user-defined name)
            camera_config: Path to JSON configuration file (optional)
            img_quality_enhancement: Enable CLAHE image enhancement (uses config default if None)
            retrieve_retry_count: Number of capture retry attempts (uses config default if None)
            **backend_kwargs: Backend-specific parameters:
                - cti_path: Path to GenTL Producer file (auto-detected if None)
                - timeout_ms: Capture timeout in milliseconds (uses config default if None)
                - buffer_count: Number of frame buffers (uses config default if None)

        Raises:
            SDKNotAvailableError: If Harvesters library is not available
            CameraConfigurationError: If configuration is invalid
            CameraInitializationError: If camera initialization fails
        """
        if not HARVESTERS_AVAILABLE:
            raise SDKNotAvailableError(
                "harvesters",
                "Install Harvesters to use GenICam cameras:\n"
                "1. Download and install Matrix Vision mvIMPACT Acquire SDK from https://www.matrix-vision.com/\n"
                "2. pip install harvesters\n"
                "3. Ensure GenTL Producer (.cti file) is accessible\n"
                "4. Configure network interface for GigE cameras",
            )
        else:
            assert Harvester is not None, "Harvesters is available but Harvester class is not initialized"

        super().__init__(camera_name, camera_config, img_quality_enhancement, retrieve_retry_count)

        # Get backend-specific configuration with fallbacks
        cti_path = backend_kwargs.get("cti_path")
        timeout_ms = backend_kwargs.get("timeout_ms")
        buffer_count = backend_kwargs.get("buffer_count")

        if timeout_ms is None:
            timeout_ms = getattr(self.camera_config, "timeout_ms", 5000)
        if buffer_count is None:
            buffer_count = getattr(self.camera_config, "buffer_count", 10)

        # Validate parameters
        if buffer_count < 1:
            raise CameraConfigurationError("Buffer count must be at least 1")
        if timeout_ms < 100:
            raise CameraConfigurationError("Timeout must be at least 100ms")

        # Auto-detect CTI path if not provided
        if cti_path is None:
            cti_path = self._detect_cti_path()

        if not os.path.exists(cti_path):
            raise CameraConfigurationError(f"GenTL Producer file not found: {cti_path}")

        # Store configuration
        self.camera_config_path = camera_config
        self.cti_path = cti_path
        self.timeout_ms = timeout_ms
        self.buffer_count = buffer_count

        # Internal state
        self.harvester: Optional[Harvester] = None
        self.image_acquirer: Optional[Any] = None
        self.device_info: Optional[Dict[str, Any]] = None
        self.vendor_quirks: Dict[str, bool] = {
            "use_integer_exposure": False,
            "exposure_node_name": "ExposureTime",
            "gain_node_name": "Gain",
        }
        self.triggermode = self.camera_config.cameras.trigger_mode

        # Derived operation timeout for non-capture operations
        self._op_timeout_s = max(3.0, float(self.timeout_ms) / 1000.0)

        # Thread executor for blocking Harvesters calls
        self._loop = None
        self._sdk_executor = None

        self.logger.info(f"GenICam camera '{self.camera_name}' initialized successfully")

    @classmethod
    def _get_shared_harvester(cls, cti_path: str) -> Harvester:
        """Get or create the shared Harvester instance.

        Args:
            cti_path: Path to GenTL Producer file

        Returns:
            Shared Harvester instance

        Raises:
            CameraConfigurationError: If CTI file doesn't exist or Harvester initialization fails
        """
        import threading

        # Initialize lock if needed
        if cls._harvester_lock is None:
            cls._harvester_lock = threading.Lock()

        with cls._harvester_lock:
            # Create new harvester if none exists or CTI path changed
            if cls._shared_harvester is None or cls._harvester_cti_path != cti_path:
                # Clean up old harvester if CTI path changed
                if cls._shared_harvester is not None:
                    try:
                        cls._shared_harvester.reset()
                    except Exception:
                        pass

                # Create new harvester and update device list ONCE
                cls._shared_harvester = Harvester()
                cls._shared_harvester.add_file(cti_path)
                cls._shared_harvester.update()  # Update device list on creation ONLY
                cls._harvester_cti_path = cti_path

            return cls._shared_harvester

    @staticmethod
    def _detect_cti_path() -> str:
        """Auto-detect Matrix Vision GenTL Producer path based on platform.

        Returns:
            Path to GenTL Producer (.cti) file

        Raises:
            CameraConfigurationError: If CTI file cannot be found
        """
        # Check environment variable first
        env_path = os.getenv("GENICAM_CTI_PATH")
        if env_path and os.path.exists(env_path):
            return env_path

        system = platform.system()
        machine = platform.machine()

        # Platform-specific paths for Matrix Vision mvIMPACT Acquire
        paths = {
            ("Linux", "x86_64"): "/opt/ImpactAcquire/lib/x86_64/mvGenTLProducer.cti",
            ("Linux", "aarch64"): "/opt/ImpactAcquire/lib/arm64/mvGenTLProducer.cti",
            ("Windows", "AMD64"): r"C:\Program Files\MATRIX VISION\mvIMPACT Acquire\bin\win64\mvGenTLProducer.cti",
            ("Darwin", "x86_64"): "/Applications/ImpactAcquire/lib/mvGenTLProducer.cti",
            ("Darwin", "arm64"): "/Applications/ImpactAcquire/lib/mvGenTLProducer.cti",
        }

        cti_path = paths.get((system, machine))
        if cti_path and os.path.exists(cti_path):
            return cti_path

        # Alternative paths or common locations
        alternative_paths = [
            "/usr/lib/mvimpact-acquire/mvGenTLProducer.cti",
            "/usr/local/lib/mvimpact-acquire/mvGenTLProducer.cti",
            os.path.expanduser("~/mvimpact-acquire/lib/mvGenTLProducer.cti"),
        ]

        for alt_path in alternative_paths:
            if os.path.exists(alt_path):
                return alt_path

        raise CameraConfigurationError(
            f"GenTL Producer not found for {system} {machine}. "
            f"Please install Matrix Vision mvIMPACT Acquire SDK or set GENICAM_CTI_PATH environment variable."
        )

    async def _sdk(self, func, *args, timeout: Optional[float] = None, **kwargs):
        """Run a potentially blocking Harvesters call on a dedicated thread with timeout.

        Args:
            func: Callable to execute
            *args: Positional args for the callable
            timeout: Optional timeout (seconds). Defaults to self._op_timeout_s
            **kwargs: Keyword args for the callable

        Returns:
            Result of the callable

        Raises:
            CameraTimeoutError: If operation times out
            HardwareOperationError: If operation fails
        """
        import concurrent.futures

        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        if self._sdk_executor is None:
            self._sdk_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix=f"harvesters-{self.camera_name}"
            )

        def _call():
            return func(*args, **kwargs)

        fut = self._loop.run_in_executor(self._sdk_executor, _call)
        try:
            return await asyncio.wait_for(fut, timeout=timeout or self._op_timeout_s)
        except asyncio.TimeoutError as e:
            raise CameraTimeoutError(
                f"Harvesters operation timed out after {timeout or self._op_timeout_s:.2f}s for camera '{self.camera_name}'"
            ) from e
        except Exception as e:
            raise HardwareOperationError(f"Harvesters operation failed for camera '{self.camera_name}': {e}") from e

    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """Get available GenICam cameras.

        Args:
            include_details: If True, return detailed information

        Returns:
            List of camera names (serial numbers or device IDs) or dict with details

        Raises:
            SDKNotAvailableError: If Harvesters library is not available
            HardwareOperationError: If camera discovery fails
        """
        if not HARVESTERS_AVAILABLE:
            raise SDKNotAvailableError("harvesters", "Harvesters library is not available for camera discovery")
        else:
            assert Harvester is not None, "Harvesters is available but Harvester class is not initialized"

        try:
            available_cameras = []
            camera_details = {}

            # Try to detect CTI path
            try:
                cti_path = GenICamCameraBackend._detect_cti_path()
            except CameraConfigurationError:
                # If no CTI found, return empty list
                return camera_details if include_details else available_cameras

            # Get shared harvester instance
            harvester = GenICamCameraBackend._get_shared_harvester(cti_path)

            # Discover devices
            harvester.update()

            for device_info in harvester.device_info_list:
                # Use serial number as primary identifier
                camera_identifier = getattr(device_info, "serial_number", None)
                if not camera_identifier:
                    # Fallback to device ID or model
                    camera_identifier = getattr(device_info, "id_", None) or getattr(device_info, "model", "Unknown")

                available_cameras.append(camera_identifier)

                if include_details:
                    # Safely get attributes from device_info
                    def safe_getattr(obj, attr, default="Unknown"):
                        try:
                            return getattr(obj, attr, default)
                        except AttributeError:
                            return default

                    def safe_parent_attr(obj, attr, default="Unknown"):
                        try:
                            parent = getattr(obj, "parent", None)
                            if parent:
                                return getattr(parent, attr, default)
                            return default
                        except AttributeError:
                            return default

                    camera_details[camera_identifier] = {
                        "serial_number": safe_getattr(device_info, "serial_number"),
                        "model": safe_getattr(device_info, "model"),
                        "vendor": safe_getattr(device_info, "vendor"),
                        "device_class": safe_getattr(device_info, "device_class"),
                        "interface": safe_parent_attr(device_info, "id_"),
                        "display_name": safe_getattr(device_info, "display_name", camera_identifier),
                        "user_defined_name": safe_getattr(device_info, "user_defined_name", ""),
                        "device_id": safe_getattr(device_info, "id_"),
                    }

            return camera_details if include_details else available_cameras

        except Exception as e:
            raise HardwareOperationError(f"Failed to discover GenICam cameras: {str(e)}")

    async def initialize(self) -> Tuple[bool, Any, Any]:
        """Initialize the camera connection.

        This searches for the camera by name, serial number, or device ID and establishes
        a connection if found.

        Returns:
            Tuple of (success status, image_acquirer object, device_info)

        Raises:
            CameraNotFoundError: If no cameras found or specified camera not found
            CameraInitializationError: If camera initialization fails
            CameraConnectionError: If camera connection fails
        """
        if not HARVESTERS_AVAILABLE:
            raise SDKNotAvailableError("harvesters", "Harvesters library is not available for camera initialization")
        else:
            assert Harvester is not None, "Harvesters is available but Harvester class is not initialized"

        try:
            # Prepare dedicated single-thread executor for SDK calls
            import concurrent.futures

            self._loop = asyncio.get_running_loop()
            if not hasattr(self, "_sdk_executor") or self._sdk_executor is None:
                self._sdk_executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix=f"harvesters-{self.camera_name}"
                )

            # Get shared harvester instance
            self.harvester = self._get_shared_harvester(self.cti_path)

            # Get device list directly - it's just an attribute access
            # NOTE: Do NOT call harvester.update() here! It stops all active acquisitions
            # on other cameras sharing this Harvester instance. The device list is already
            # populated when the Harvester was first created in _get_shared_harvester().
            device_list = self.harvester.device_info_list
            if len(device_list) == 0:
                raise CameraNotFoundError("No GenICam cameras found")

            # Find camera by name, serial number, or device ID
            camera_found = False
            target_device_info = None

            # Parse camera name to extract actual identifier
            # Camera names come in as "GenICam:serial_number" from discovery
            if self.camera_name.startswith("GenICam:"):
                actual_camera_id = self.camera_name.split(":", 1)[1]
            else:
                actual_camera_id = self.camera_name

            for device_info in device_list:
                serial_number = getattr(device_info, "serial_number", "")
                device_id = getattr(device_info, "id_", "")
                user_defined_name = getattr(device_info, "user_defined_name", "")
                display_name = getattr(device_info, "display_name", "")

                if actual_camera_id in [
                    serial_number,
                    device_id,
                    user_defined_name,
                    display_name,
                ] or actual_camera_id in str(device_info):
                    camera_found = True
                    target_device_info = device_info
                    break

            if not camera_found:
                available_cameras = [
                    f"{getattr(info, 'serial_number', 'Unknown')} ({getattr(info, 'model', 'Unknown')})"
                    for info in device_list
                ]
                raise CameraNotFoundError(
                    f"Camera '{actual_camera_id}' (from '{self.camera_name}') not found. Available cameras: {available_cameras}"
                )

            # Create image acquirer
            try:
                # Create by index - find the index of our target device
                target_index = None
                for i, device_info in enumerate(device_list):
                    if device_info == target_device_info:
                        target_index = i
                        break

                if target_index is None:
                    raise CameraConnectionError(f"Failed to find index for camera '{actual_camera_id}'")

                # Create the image acquirer synchronously like the working script
                self.image_acquirer = self.harvester.create(target_index)

                if self.image_acquirer is None:
                    raise CameraConnectionError(f"Failed to create image acquirer for camera '{self.camera_name}'")

                # Store device info and detect vendor quirks
                self.device_info = {
                    "serial_number": getattr(target_device_info, "serial_number", "Unknown"),
                    "model": getattr(target_device_info, "model", "Unknown"),
                    "vendor": getattr(target_device_info, "vendor", "Unknown"),
                    "device_class": getattr(target_device_info, "device_class", "Unknown"),
                    "display_name": getattr(target_device_info, "display_name", self.camera_name),
                }

                # Detect vendor-specific quirks
                await self._detect_vendor_quirks()

                # Configure the camera after opening
                await self._configure_camera()

                # Start acquisition for continuous capture (required for some cameras like Keyence)
                await self._start_acquisition()

                # Load config if provided
                if self.camera_config_path and os.path.exists(self.camera_config_path):
                    await self.import_config(self.camera_config_path)

                self.initialized = True
                return True, self.image_acquirer, self.device_info

            except Exception as e:
                self.logger.error(f"Failed to open GenICam camera '{self.camera_name}': {str(e)}")
                # Clean up resources on failure
                await self._cleanup_on_failure()
                raise CameraConnectionError(f"Failed to open camera '{self.camera_name}': {str(e)}")

        except (CameraNotFoundError, CameraConnectionError):
            # Clean up resources on failure
            await self._cleanup_on_failure()
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error initializing GenICam camera '{self.camera_name}': {str(e)}")
            # Clean up resources on failure
            await self._cleanup_on_failure()
            raise CameraInitializationError(f"Unexpected error initializing camera '{self.camera_name}': {str(e)}")

    async def _cleanup_on_failure(self):
        """Clean up resources when initialization fails."""
        try:
            # Stop and destroy image acquirer if it was created
            if hasattr(self, "image_acquirer") and self.image_acquirer is not None:
                try:

                    def _cleanup_acquirer():
                        if self.image_acquirer.is_acquiring():
                            self.image_acquirer.stop()
                        self.image_acquirer.destroy()

                    await self._sdk(_cleanup_acquirer, timeout=2.0)  # Short timeout for cleanup
                except Exception as e:
                    self.logger.warning(f"Error cleaning up image acquirer during failure: {e}")
                finally:
                    self.image_acquirer = None

            # DO NOT reset the shared Harvester - it's used by other cameras!
            # Just clear our reference to it
            if hasattr(self, "harvester"):
                self.harvester = None

            # Shutdown executor
            if hasattr(self, "_sdk_executor") and self._sdk_executor is not None:
                try:
                    self._sdk_executor.shutdown(wait=False, cancel_futures=True)
                except Exception as e:
                    self.logger.warning(f"Error shutting down executor during failure: {e}")
                finally:
                    self._sdk_executor = None

            self.initialized = False

        except Exception as e:
            # Don't raise exceptions during cleanup - just log
            self.logger.warning(f"Error during failure cleanup for camera '{self.camera_name}': {e}")

    async def _detect_vendor_quirks(self):
        """Detect vendor-specific parameter handling requirements."""
        if self.device_info and "vendor" in self.device_info:
            vendor = self.device_info["vendor"].upper()

            if "KEYENCE" in vendor:
                self.vendor_quirks.update(
                    {
                        "use_integer_exposure": True,
                        "exposure_node_name": "ExposureTime",
                        "gain_node_name": "Gain",
                    }
                )
                self.logger.debug("Detected Keyence camera, using integer exposure values")
            elif "BASLER" in vendor:
                self.vendor_quirks.update(
                    {
                        "use_integer_exposure": False,
                        "exposure_node_name": "ExposureTime",
                        "gain_node_name": "Gain",
                    }
                )
                self.logger.debug("Detected Basler camera, using float exposure values")
            else:
                # Default for unknown vendors
                self.vendor_quirks.update(
                    {
                        "use_integer_exposure": False,
                        "exposure_node_name": "ExposureTime",
                        "gain_node_name": "Gain",
                    }
                )
                self.logger.debug(f"Unknown vendor '{vendor}', using default parameter handling")

        # Detect TriggerMode writability (camera-specific, not vendor-specific)
        await self._detect_trigger_mode_capability()

    async def _detect_trigger_mode_capability(self):
        """Detect if camera supports runtime trigger mode changes.

        Some cameras (e.g., Keyence) have read-only TriggerMode that must be
        configured via camera software, not GenICam API.
        """
        try:
            await self._ensure_connected()

            def _check_trigger_capability():
                node_map = self.image_acquirer.remote_device.node_map

                # Check if TriggerMode node exists
                if not hasattr(node_map, "TriggerMode"):
                    return False, "off", "TriggerMode node not found"

                trigger_mode_node = node_map.TriggerMode

                # Get current trigger mode value
                try:
                    current_mode = trigger_mode_node.value.lower()
                except Exception as e:
                    return False, "unknown", f"Cannot read TriggerMode: {e}"

                # Check access mode (3 = Read Only, 4 = Read/Write)
                try:
                    access_mode = trigger_mode_node.get_access_mode()
                    is_writable = access_mode == 4  # 4 = RW (Read/Write)
                except Exception:
                    # Fallback: assume writable if we can't check
                    is_writable = True

                return is_writable, current_mode, None

            is_writable, current_mode, error = await self._sdk(_check_trigger_capability, timeout=self._op_timeout_s)

            # Store results in vendor_quirks
            self.vendor_quirks["trigger_mode_writable"] = is_writable
            self.vendor_quirks["trigger_mode_at_init"] = current_mode

            if not is_writable:
                self.logger.warning(
                    f"Camera '{self.camera_name}' has read-only TriggerMode (current: {current_mode}). "
                    f"Trigger mode must be configured using camera software. "
                    f"Runtime trigger mode changes via API are not supported."
                )
            else:
                self.logger.debug(
                    f"Camera '{self.camera_name}' supports runtime trigger mode changes (current: {current_mode})"
                )

            # Update triggermode to reflect actual camera state
            self.triggermode = current_mode

        except Exception as e:
            self.logger.warning(f"Could not detect trigger mode capability for '{self.camera_name}': {e}")
            # Assume writable if detection fails (optimistic default)
            self.vendor_quirks["trigger_mode_writable"] = True
            self.vendor_quirks["trigger_mode_at_init"] = "continuous"

    async def _ensure_connected(self):
        """Ensure camera is connected and image acquirer is available.

        Raises:
            CameraConnectionError: If camera is not connected
        """
        if self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not connected")

    async def _get_node_value(self, node_name: str, fallback_names: Optional[List[str]] = None):
        """Get GenICam node value with fallback names.

        Args:
            node_name: Primary node name to try
            fallback_names: Alternative node names to try if primary fails

        Returns:
            Node value

        Raises:
            HardwareOperationError: If node cannot be accessed
        """
        await self._ensure_connected()

        node_names = [node_name] + (fallback_names or [])

        for name in node_names:
            try:

                def _get_value():
                    node_map = self.image_acquirer.remote_device.node_map
                    node = getattr(node_map, name, None)
                    if node is not None:
                        return node.value
                    return None

                value = await self._sdk(_get_value, timeout=self._op_timeout_s)
                if value is not None:
                    return value
            except Exception as e:
                self.logger.debug(f"Failed to get node '{name}' for camera '{self.camera_name}': {e}")
                continue

        raise HardwareOperationError(f"Could not access any of these nodes: {node_names}")

    async def _set_node_value(self, node_name: str, value: Any, fallback_names: Optional[List[str]] = None):
        """Set GenICam node value with vendor-specific type handling.

        Args:
            node_name: Primary node name to try
            value: Value to set
            fallback_names: Alternative node names to try if primary fails

        Raises:
            HardwareOperationError: If node cannot be set
        """
        await self._ensure_connected()

        node_names = [node_name] + (fallback_names or [])

        for name in node_names:
            try:

                def _set_value():
                    node_map = self.image_acquirer.remote_device.node_map
                    node = getattr(node_map, name, None)
                    if node is not None:
                        # Apply vendor-specific type conversion
                        if name == "ExposureTime" and self.vendor_quirks.get("use_integer_exposure", False):
                            value_to_set = int(value)
                        else:
                            value_to_set = value
                        node.value = value_to_set
                    else:
                        raise AttributeError(f"Node '{name}' not found")

                await self._sdk(_set_value, timeout=self._op_timeout_s)
                return  # Success - exit method
            except Exception as e:
                self.logger.debug(f"Failed to set node '{name}' for camera '{self.camera_name}': {e}")
                continue

        raise HardwareOperationError(f"Could not set any of these nodes: {node_names}")

    async def _configure_camera(self):
        """Configure initial camera settings.

        Raises:
            CameraConfigurationError: If camera configuration fails
        """
        try:
            await self._ensure_connected()

            # Set buffer count and acquisition mode
            def _configure_buffers():
                self.image_acquirer.num_buffers = self.buffer_count

                # Set AcquisitionMode to Continuous for multi-capture support
                node_map = self.image_acquirer.remote_device.node_map
                if hasattr(node_map, "AcquisitionMode"):
                    try:
                        node_map.AcquisitionMode.value = "Continuous"
                        self.logger.debug(f"Set AcquisitionMode to Continuous for camera '{self.camera_name}'")
                    except Exception as acq_error:
                        self.logger.warning(f"Could not set AcquisitionMode to Continuous: {acq_error}")

            await self._sdk(_configure_buffers, timeout=self._op_timeout_s)

            self.logger.debug(f"GenICam camera '{self.camera_name}' configured with buffer_count={self.buffer_count}")

        except Exception as e:
            self.logger.error(f"Failed to configure GenICam camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to configure camera '{self.camera_name}': {str(e)}")

    async def _start_acquisition(self):
        """Start image acquisition stream (required for some cameras like Keyence)."""
        try:
            await self._ensure_connected()

            def _start_stream():
                if not self.image_acquirer.is_acquiring():
                    self.image_acquirer.start()
                    self.logger.debug(f"Started acquisition for camera '{self.camera_name}'")

            await self._sdk(_start_stream, timeout=self._op_timeout_s)

        except Exception as e:
            self.logger.warning(f"Failed to start acquisition for camera '{self.camera_name}': {str(e)}")
            # Don't raise error - some cameras might not need this

    async def get_exposure_range(self) -> List[Union[int, float]]:
        """Get the supported exposure time range in microseconds.

        Returns:
            List with [min_exposure, max_exposure] in microseconds

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            HardwareOperationError: If exposure range retrieval fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            await self._ensure_connected()

            def _get_exposure_range():
                node_map = self.image_acquirer.remote_device.node_map
                node_name = self.vendor_quirks.get("exposure_node_name", "ExposureTime")

                # Try different possible exposure node names
                for name in [node_name, "ExposureTime", "ExposureTimeAbs", "ExposureTimeRaw"]:
                    try:
                        node = getattr(node_map, name, None)
                        if node is not None:
                            return [node.min, node.max]
                    except Exception:
                        continue

                # Return reasonable defaults if no exposure node found
                return [1.0, 1000000.0]

            min_value, max_value = await self._sdk(_get_exposure_range, timeout=self._op_timeout_s)
            return [min_value, max_value]

        except Exception as e:
            self.logger.warning(f"Exposure range not available for camera '{self.camera_name}': {str(e)}")
            return [1.0, 1000000.0]  # 1 μs to 1 second

    async def get_exposure(self) -> float:
        """Get current exposure time in microseconds.

        Returns:
            Current exposure time

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            HardwareOperationError: If exposure retrieval fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            node_name = self.vendor_quirks.get("exposure_node_name", "ExposureTime")
            exposure = await self._get_node_value(node_name, ["ExposureTime", "ExposureTimeAbs", "ExposureTimeRaw"])
            return float(exposure)
        except Exception as e:
            self.logger.warning(f"Exposure not available for camera '{self.camera_name}': {str(e)}")
            return 20000.0  # 20ms default

    async def set_exposure(self, exposure: Union[int, float]):
        """Set the camera exposure time in microseconds.

        Args:
            exposure: Exposure time in microseconds

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            CameraConfigurationError: If exposure value is out of range
            HardwareOperationError: If exposure setting fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            min_exp, max_exp = await self.get_exposure_range()

            if exposure < min_exp or exposure > max_exp:
                raise CameraConfigurationError(
                    f"Exposure {exposure} outside valid range [{min_exp}, {max_exp}] for camera '{self.camera_name}'"
                )

            node_name = self.vendor_quirks.get("exposure_node_name", "ExposureTime")
            await self._set_node_value(node_name, exposure, ["ExposureTime", "ExposureTimeAbs", "ExposureTimeRaw"])

            # Verify setting
            actual_exposure = await self.get_exposure()
            if not (abs(actual_exposure - exposure) < 0.01 * max(1.0, float(exposure))):
                raise HardwareOperationError(
                    f"Exposure verification failed for camera '{self.camera_name}': requested={exposure}, actual={actual_exposure}"
                )

        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Exposure setting failed for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set exposure: {str(e)}")

    async def get_current_pixel_format(self) -> str:
        """Get current pixel format.

        Returns:
            Current pixel format string (e.g., "Mono8", "RGB8", "BayerRG8")

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            HardwareOperationError: If pixel format retrieval fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            await self._ensure_connected()

            def _get_pixel_format():
                node_map = self.image_acquirer.remote_device.node_map
                pixel_format_node = getattr(node_map, "PixelFormat", None)
                if pixel_format_node is not None:
                    return str(pixel_format_node.value)
                return "Unknown"

            return await self._sdk(_get_pixel_format)

        except Exception as e:
            self.logger.warning(f"Pixel format not available for camera '{self.camera_name}': {str(e)}")
            return "Unknown"

    async def get_width_range(self) -> List[int]:
        """Get camera width range.

        Returns:
            List containing [min_width, max_width]

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If width range retrieval fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_connected()

            def _get_width_range():
                node_map = self.image_acquirer.remote_device.node_map
                width_node = getattr(node_map, "Width", None)
                if width_node is not None:
                    return [width_node.min, width_node.max]
                # Return default range if Width node not available
                return [1, 9999]

            return await self._sdk(_get_width_range, timeout=self._op_timeout_s)

        except Exception as e:
            self.logger.warning(f"Width range not available for camera '{self.camera_name}': {str(e)}")
            return [1, 9999]  # Default range

    async def get_height_range(self) -> List[int]:
        """Get camera height range.

        Returns:
            List containing [min_height, max_height]

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If height range retrieval fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")

        try:
            await self._ensure_connected()

            def _get_height_range():
                node_map = self.image_acquirer.remote_device.node_map
                height_node = getattr(node_map, "Height", None)
                if height_node is not None:
                    return [height_node.min, height_node.max]
                # Return default range if Height node not available
                return [1, 9999]

            return await self._sdk(_get_height_range, timeout=self._op_timeout_s)

        except Exception as e:
            self.logger.warning(f"Height range not available for camera '{self.camera_name}': {str(e)}")
            return [1, 9999]  # Default range

    async def get_pixel_format_range(self) -> List[str]:
        """Get list of supported pixel formats.

        Returns:
            List of supported pixel format strings

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            HardwareOperationError: If pixel format list retrieval fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            await self._ensure_connected()

            def _get_pixel_formats():
                node_map = self.image_acquirer.remote_device.node_map
                pixel_format_node = getattr(node_map, "PixelFormat", None)
                if pixel_format_node is not None and hasattr(pixel_format_node, "entries"):
                    return [str(entry.symbolic) for entry in pixel_format_node.entries if entry.is_available]
                return []

            formats = await self._sdk(_get_pixel_formats)
            return formats if formats else ["Unknown"]

        except Exception as e:
            self.logger.warning(f"Pixel formats not available for camera '{self.camera_name}': {str(e)}")
            return ["Unknown"]

    async def set_pixel_format(self, pixel_format: str):
        """Set the camera pixel format.

        Args:
            pixel_format: Pixel format string (e.g., "Mono8", "RGB8")

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            CameraConfigurationError: If pixel format is not supported
            HardwareOperationError: If pixel format setting fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            await self._ensure_connected()

            def _set_pixel_format():
                node_map = self.image_acquirer.remote_device.node_map
                pixel_format_node = getattr(node_map, "PixelFormat", None)
                if pixel_format_node is None:
                    raise HardwareOperationError("PixelFormat node not available")

                # Check if format is supported
                if hasattr(pixel_format_node, "entries"):
                    available_formats = [
                        str(entry.symbolic) for entry in pixel_format_node.entries if entry.is_available
                    ]
                    if pixel_format not in available_formats:
                        raise CameraConfigurationError(
                            f"Pixel format '{pixel_format}' not supported. Available: {available_formats}"
                        )

                pixel_format_node.value = pixel_format

            await self._sdk(_set_pixel_format)

        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Pixel format setting failed for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set pixel format: {str(e)}")

    async def get_triggermode(self) -> str:
        """Get current trigger mode.

        Returns:
            "continuous" or "trigger"

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            HardwareOperationError: If trigger mode retrieval fails
        """
        if not self.initialized or self.image_acquirer is None:
            return "continuous"

        try:
            await self._ensure_connected()

            def _get_trigger_mode():
                node_map = self.image_acquirer.remote_device.node_map

                # Try to get trigger mode
                trigger_mode_node = getattr(node_map, "TriggerMode", None)
                if trigger_mode_node is not None:
                    try:
                        trigger_enabled = trigger_mode_node.value == "On"

                        # Check trigger source if available and readable
                        trigger_source_node = getattr(node_map, "TriggerSource", None)
                        if trigger_source_node is not None:
                            try:
                                trigger_source = trigger_source_node.value
                                return "trigger" if (trigger_enabled and trigger_source == "Software") else "continuous"
                            except Exception:
                                # TriggerSource not readable - just use TriggerMode
                                return "trigger" if trigger_enabled else "continuous"
                        else:
                            return "trigger" if trigger_enabled else "continuous"
                    except Exception:
                        # TriggerMode not readable
                        pass

                return "continuous"  # Default if no trigger nodes found or readable

            trigger_mode = await self._sdk(_get_trigger_mode, timeout=self._op_timeout_s)
            self.triggermode = trigger_mode
            return trigger_mode

        except Exception as e:
            self.logger.error(f"Error getting trigger mode for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to get trigger mode: {str(e)}")

    async def set_triggermode(self, triggermode: str = "continuous"):
        """Set the camera's trigger mode for image acquisition.

        Args:
            triggermode: Trigger mode ("continuous" or "trigger")

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            CameraConfigurationError: If trigger mode is invalid
            HardwareOperationError: If trigger mode setting fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        if triggermode not in ["continuous", "trigger"]:
            raise CameraConfigurationError(
                f"Invalid trigger mode '{triggermode}' for camera '{self.camera_name}'. "
                "Must be 'continuous' or 'trigger'"
            )

        try:
            await self._ensure_connected()

            # Check if camera supports runtime trigger mode changes
            if not self.vendor_quirks.get("trigger_mode_writable", True):
                current_mode = self.vendor_quirks.get("trigger_mode_at_init", "unknown")
                raise CameraConfigurationError(
                    f"Camera '{self.camera_name}' does not support runtime trigger mode changes. "
                    f"Current mode: '{current_mode}'. "
                    f"Trigger mode must be configured using camera software (e.g., Keyence configuration tool). "
                    f"Once configured at the hardware level, the camera will operate in that mode."
                )

            def _set_trigger_mode():
                node_map = self.image_acquirer.remote_device.node_map

                # Check if acquisition is running
                was_acquiring = self.image_acquirer.is_acquiring()

                # Stop acquisition if running (required for trigger mode changes)
                if was_acquiring:
                    self.image_acquirer.stop()

                try:
                    if triggermode == "continuous":
                        # Disable trigger mode
                        trigger_mode_node = getattr(node_map, "TriggerMode", None)
                        if trigger_mode_node is not None:
                            trigger_mode_node.value = "Off"
                    else:
                        # Enable trigger mode
                        trigger_selector_node = getattr(node_map, "TriggerSelector", None)
                        if trigger_selector_node is not None:
                            trigger_selector_node.value = "FrameStart"

                        trigger_mode_node = getattr(node_map, "TriggerMode", None)
                        if trigger_mode_node is not None:
                            trigger_mode_node.value = "On"

                        trigger_source_node = getattr(node_map, "TriggerSource", None)
                        if trigger_source_node is not None:
                            trigger_source_node.value = "Software"

                finally:
                    # Always restart acquisition if it was running before
                    if was_acquiring:
                        self.image_acquirer.start()

            await self._sdk(_set_trigger_mode, timeout=self._op_timeout_s)
            self.triggermode = triggermode

            self.logger.debug(f"Trigger mode set to '{triggermode}' for camera '{self.camera_name}'")

        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Error setting trigger mode for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set trigger mode: {str(e)}")

    async def capture(self) -> np.ndarray:
        """Capture a single image from the camera.

        In continuous mode, returns the latest available frame.
        In trigger mode, executes a software trigger and waits for the image.

        Returns:
            Image array in BGR format

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            CameraCaptureError: If image capture fails
            CameraTimeoutError: If capture times out
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            await self._ensure_connected()

            for i in range(self.retrieve_retry_count):
                if i > 0:
                    self.logger.debug(
                        f"Retrying capture {i + 1} of {self.retrieve_retry_count} for camera '{self.camera_name}'"
                    )

                try:

                    def _capture_image():
                        # Ensure acquisition is running (should already be started in initialization)
                        if not self.image_acquirer.is_acquiring():
                            self.image_acquirer.start()
                            self.logger.debug(f"Started acquisition during capture for camera '{self.camera_name}'")

                        # Execute software trigger if in trigger mode
                        # NOTE: Must be done AFTER acquisition is started for some cameras
                        if self.triggermode == "trigger":
                            node_map = self.image_acquirer.remote_device.node_map

                            # Find software trigger command
                            trigger_cmd = getattr(node_map, "TriggerSoftware", None)
                            if trigger_cmd is None:
                                trigger_cmd = getattr(node_map, "SoftwareTrigger", None)
                                cmd_name = "SoftwareTrigger"
                            else:
                                cmd_name = "TriggerSoftware"

                            if trigger_cmd is None:
                                raise HardwareOperationError(
                                    f"No software trigger command found for camera '{self.camera_name}'. "
                                    f"Camera may not support software triggering."
                                )

                            # Execute software trigger
                            self.logger.debug(f"Executing {cmd_name} for camera '{self.camera_name}'")
                            trigger_cmd.execute()

                        # Fetch image with timeout
                        timeout_s = max(10.0, float(self.timeout_ms) / 1000.0)
                        with self.image_acquirer.fetch(timeout=timeout_s) as buffer:
                            # Get image component
                            component = buffer.payload.components[0]

                            # Get image dimensions and data
                            width = component.width
                            height = component.height
                            data = component.data

                            # Reshape based on pixel format - ensure dimensions are integers
                            height, width = int(height), int(width)
                            if component.num_components_per_pixel == 1:
                                # Monochrome image
                                image = data.reshape(height, width)
                                # Convert to BGR for consistency
                                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
                            else:
                                # Color image
                                channels = int(component.num_components_per_pixel)
                                image = data.reshape(height, width, channels)

                                # Convert RGB to BGR if needed (OpenCV uses BGR)
                                if channels == 3:
                                    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

                            return image

                    # Try direct capture without threading for debugging
                    try:
                        image = _capture_image()
                    except Exception as direct_error:
                        self.logger.warning(f"Direct capture failed, trying with SDK wrapper: {direct_error}")
                        image = await self._sdk(_capture_image, timeout=self._op_timeout_s + (self.timeout_ms / 1000.0))

                    if self.img_quality_enhancement and image is not None:
                        image = await self._enhance_image(image)

                    return image

                except Exception as e:
                    if "timeout" in str(e).lower():
                        if i == self.retrieve_retry_count - 1:
                            raise CameraTimeoutError(
                                f"Capture timeout after {self.retrieve_retry_count} attempts "
                                f"for camera '{self.camera_name}': {str(e)}"
                            ) from e
                        continue
                    else:
                        raise CameraCaptureError(f"Capture failed for camera '{self.camera_name}': {str(e)}") from e

            raise CameraCaptureError(
                f"Failed to capture image after {self.retrieve_retry_count} attempts for camera '{self.camera_name}'"
            )

        except (CameraConnectionError, CameraCaptureError, CameraTimeoutError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during capture for camera '{self.camera_name}': {str(e)}")
            raise CameraCaptureError(f"Unexpected capture error for camera '{self.camera_name}': {str(e)}") from e

    async def _enhance_image(self, image: np.ndarray) -> np.ndarray:
        """Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) enhancement.

        Args:
            image: Input BGR image

        Returns:
            Enhanced BGR image

        Raises:
            CameraCaptureError: If image enhancement fails
        """
        try:
            # Run image processing in thread to avoid blocking
            def enhance():
                lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
                length, a, b = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                cl = clahe.apply(length)
                enhanced_lab = cv2.merge((cl, a, b))
                enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
                return enhanced_img

            return await asyncio.to_thread(enhance)
        except Exception as e:
            self.logger.error(f"Image enhancement failed for camera '{self.camera_name}': {str(e)}")
            raise CameraCaptureError(f"Image enhancement failed: {str(e)}")

    async def check_connection(self) -> bool:
        """Check if camera is connected and operational.

        Returns:
            True if connected and operational, False otherwise
        """
        if not self.initialized or self.image_acquirer is None:
            return False

        try:
            # Check connection without calling capture() to avoid state corruption
            def _check_camera_accessible():
                # Verify the camera is still accessible via node map
                node_map = self.image_acquirer.remote_device.node_map
                # Try to access a basic node to verify communication
                try:
                    # Access vendor name node (should always be readable)
                    vendor_node = getattr(node_map, "DeviceVendorName", None)
                    if vendor_node is not None:
                        _ = vendor_node.value  # This will fail if camera is disconnected
                        return True
                except Exception:
                    pass
                return False

            # Check if acquisition is running (good sign of healthy connection)
            is_acquiring = self.image_acquirer.is_acquiring()
            is_accessible = await self._sdk(_check_camera_accessible, timeout=5.0)

            return is_accessible and is_acquiring

        except Exception as e:
            self.logger.warning(f"Connection check failed for camera '{self.camera_name}': {str(e)}")
            return False

    async def close(self):
        """Close the camera and release resources.

        Raises:
            CameraConnectionError: If camera closure fails
        """
        if self.image_acquirer is not None:
            try:
                image_acquirer = self.image_acquirer
                self.image_acquirer = None
                self.initialized = False

                # Stop acquisition
                try:

                    def _stop_acquisition():
                        if image_acquirer.is_acquiring():
                            image_acquirer.stop()

                    await self._sdk(_stop_acquisition, timeout=self._op_timeout_s)
                except Exception as e:
                    self.logger.warning(f"Error stopping acquisition for camera '{self.camera_name}': {str(e)}")

                # Destroy image acquirer
                try:
                    await self._sdk(image_acquirer.destroy, timeout=self._op_timeout_s)
                except Exception as e:
                    self.logger.warning(f"Error destroying image acquirer for camera '{self.camera_name}': {str(e)}")

                self.logger.info(f"GenICam camera '{self.camera_name}' closed")

            except Exception as e:
                self.logger.error(f"Error in camera cleanup for '{self.camera_name}': {str(e)}")
                raise CameraConnectionError(f"Failed to close camera '{self.camera_name}': {str(e)}")

        # Release harvester reference (but don't reset it - it's shared)
        self.harvester = None

        # Shutdown executor if present
        try:
            if hasattr(self, "_sdk_executor") and self._sdk_executor is not None:
                self._sdk_executor.shutdown(wait=False, cancel_futures=True)
                self._sdk_executor = None
        except Exception:
            pass

    # Placeholder implementations for optional methods - will implement based on GenICam node availability
    async def get_gain_range(self) -> List[Union[int, float]]:
        """Get camera gain range."""
        try:
            node_name = self.vendor_quirks.get("gain_node_name", "Gain")

            def _get_gain_range():
                node_map = self.image_acquirer.remote_device.node_map
                node = getattr(node_map, node_name, None)
                if node is not None:
                    return [node.min, node.max]
                return [1.0, 16.0]  # Default range

            return await self._sdk(_get_gain_range, timeout=self._op_timeout_s)
        except Exception:
            return [1.0, 16.0]  # Default range

    async def get_gain(self) -> float:
        """Get current camera gain."""
        try:
            node_name = self.vendor_quirks.get("gain_node_name", "Gain")
            gain = await self._get_node_value(node_name, ["Gain", "GainRaw", "AnalogGain"])
            return float(gain)
        except Exception:
            return 1.0  # Default gain

    async def set_gain(self, gain: Union[int, float]):
        """Set camera gain."""
        try:
            min_gain, max_gain = await self.get_gain_range()

            if gain < min_gain or gain > max_gain:
                raise CameraConfigurationError(
                    f"Gain {gain} outside valid range [{min_gain}, {max_gain}] for camera '{self.camera_name}'"
                )

            node_name = self.vendor_quirks.get("gain_node_name", "Gain")
            await self._set_node_value(node_name, gain, ["Gain", "GainRaw", "AnalogGain"])
        except Exception as e:
            raise HardwareOperationError(f"Failed to set gain for camera '{self.camera_name}': {str(e)}")

    async def get_wb(self) -> str:
        """Get current white balance mode using GenICam nodes.

        Returns:
            Current white balance mode string

        Raises:
            CameraConnectionError: If camera is not initialized
        """
        if not self.initialized or self.image_acquirer is None:
            return "auto"  # Default fallback

        try:
            await self._ensure_connected()

            def _get_wb():
                node_map = self.image_acquirer.remote_device.node_map

                # Try common white balance node names
                wb_auto_node = getattr(node_map, "BalanceWhiteAuto", None)
                if wb_auto_node is not None:
                    try:
                        wb_mode = wb_auto_node.value
                        if wb_mode == "Off":
                            return "manual"
                        elif wb_mode == "Once":
                            return "once"
                        else:
                            return "auto"
                    except Exception:
                        pass

                # Alternative node names
                wb_mode_node = getattr(node_map, "WhiteBalanceMode", None)
                if wb_mode_node is not None:
                    try:
                        return str(wb_mode_node.value).lower()
                    except Exception:
                        pass

                return "auto"  # Default

            return await self._sdk(_get_wb, timeout=self._op_timeout_s)

        except Exception as e:
            self.logger.warning(f"White balance retrieval failed for camera '{self.camera_name}': {str(e)}")
            return "auto"

    async def set_auto_wb_once(self, value: str):
        """Execute automatic white balance once using GenICam nodes.

        Args:
            value: White balance mode ("auto", "once", "manual", "off")

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If white balance setting fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            await self._ensure_connected()

            def _set_wb():
                node_map = self.image_acquirer.remote_device.node_map

                # Try to set white balance mode
                wb_auto_node = getattr(node_map, "BalanceWhiteAuto", None)
                if wb_auto_node is not None:
                    try:
                        if value.lower() in ["auto", "continuous"]:
                            wb_auto_node.value = "Continuous"
                        elif value.lower() in ["once", "single"]:
                            wb_auto_node.value = "Once"
                        elif value.lower() in ["manual", "off"]:
                            wb_auto_node.value = "Off"
                        else:
                            wb_auto_node.value = "Once"  # Default to once
                        return  # Success - exit
                    except Exception as e:
                        self.logger.debug(f"Could not set BalanceWhiteAuto: {e}")

                # Alternative node approach
                wb_mode_node = getattr(node_map, "WhiteBalanceMode", None)
                if wb_mode_node is not None:
                    try:
                        wb_mode_node.value = value
                        return  # Success - exit
                    except Exception as e:
                        self.logger.debug(f"Could not set WhiteBalanceMode: {e}")

                raise HardwareOperationError("White balance nodes not available")

            await self._sdk(_set_wb, timeout=self._op_timeout_s)
            self.logger.debug(f"White balance set to '{value}' for camera '{self.camera_name}'")

        except Exception as e:
            self.logger.warning(f"White balance setting failed for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set white balance: {str(e)}")

    async def get_wb_range(self) -> List[str]:
        """Get available white balance modes using GenICam nodes.

        Returns:
            List of available white balance mode strings

        Raises:
            CameraConnectionError: If camera is not initialized
        """
        if not self.initialized or self.image_acquirer is None:
            return ["auto", "manual", "once"]  # Default fallback

        try:
            await self._ensure_connected()

            def _get_wb_range():
                node_map = self.image_acquirer.remote_device.node_map

                # Try to get available white balance modes
                wb_auto_node = getattr(node_map, "BalanceWhiteAuto", None)
                if wb_auto_node is not None:
                    try:
                        # Check if node has enumeration entries
                        if hasattr(wb_auto_node, "symbolics"):
                            modes = []
                            for symbolic in wb_auto_node.symbolics:
                                if symbolic.lower() == "continuous":
                                    modes.append("auto")
                                elif symbolic.lower() == "off":
                                    modes.append("manual")
                                elif symbolic.lower() == "once":
                                    modes.append("once")
                                else:
                                    modes.append(symbolic.lower())
                            return modes
                    except Exception as e:
                        self.logger.debug(f"Could not get BalanceWhiteAuto range: {e}")

                # Return common modes if enumeration fails
                return ["auto", "manual", "once"]

            return await self._sdk(_get_wb_range, timeout=self._op_timeout_s)

        except Exception as e:
            self.logger.warning(f"White balance range retrieval failed for camera '{self.camera_name}': {str(e)}")
            return ["auto", "manual", "once"]

    async def import_config(self, config_path: str):
        """Import camera configuration from JSON file.

        Args:
            config_path: Path to JSON configuration file

        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If configuration file is invalid
            HardwareOperationError: If configuration import fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            import json
            import os

            if not os.path.exists(config_path):
                raise CameraConfigurationError(f"Configuration file not found: {config_path}")

            with open(config_path, "r") as f:
                config = json.load(f)

            # Apply configuration settings
            # Support both 'exposure_time' (new) and 'exposure' (legacy) for backward compatibility
            if "exposure_time" in config:
                await self.set_exposure(config["exposure_time"])
            elif "exposure" in config:
                await self.set_exposure(config["exposure"])

            if "gain" in config:
                await self.set_gain(config["gain"])

            if "triggermode" in config:
                await self.set_triggermode(config["triggermode"])

            if "white_balance" in config:
                await self.set_auto_wb_once(config["white_balance"])

            if "roi" in config and isinstance(config["roi"], dict):
                roi = config["roi"]
                if all(key in roi for key in ["x", "y", "width", "height"]):
                    await self.set_ROI(roi["x"], roi["y"], roi["width"], roi["height"])

            # Apply any vendor-specific GenICam settings
            if "genicam_nodes" in config and isinstance(config["genicam_nodes"], dict):
                await self._apply_genicam_nodes(config["genicam_nodes"])

            self.logger.info(f"Configuration imported successfully for camera '{self.camera_name}'")

        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Configuration import failed for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to import configuration: {str(e)}")

    async def export_config(self, config_path: str):
        """Export camera configuration to JSON file.

        Args:
            config_path: Path to save JSON configuration file

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If configuration export fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            import json
            import os

            # Gather current configuration
            config = {
                "camera_name": self.camera_name,
                "vendor": self.device_info.get("vendor", "Unknown") if self.device_info else "Unknown",
                "model": self.device_info.get("model", "Unknown") if self.device_info else "Unknown",
                "exported_timestamp": time.time(),
                "exposure_time": await self.get_exposure(),
                "gain": await self.get_gain(),
                "triggermode": await self.get_triggermode(),
                "white_balance": await self.get_wb(),
                "roi": await self.get_ROI(),
                "exposure_range": await self.get_exposure_range(),
                "gain_range": await self.get_gain_range(),
                "white_balance_range": await self.get_wb_range(),
            }

            # Add GenICam-specific nodes that might be useful
            genicam_nodes = await self._export_genicam_nodes()
            if genicam_nodes:
                config["genicam_nodes"] = genicam_nodes

            # Ensure directory exists
            os.makedirs(os.path.dirname(config_path), exist_ok=True)

            # Save configuration
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

            self.logger.info(f"Configuration exported successfully for camera '{self.camera_name}' to {config_path}")

        except (CameraConnectionError,):
            raise
        except Exception as e:
            self.logger.error(f"Configuration export failed for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to export configuration: {str(e)}")

    async def _apply_genicam_nodes(self, node_config: Dict[str, Any]):
        """Apply GenICam node configuration.

        Args:
            node_config: Dictionary of node names to values
        """
        try:
            await self._ensure_connected()

            def _apply_nodes():
                node_map = self.image_acquirer.remote_device.node_map
                applied_count = 0

                for node_name, value in node_config.items():
                    try:
                        node = getattr(node_map, node_name, None)
                        if node is not None and hasattr(node, "value"):
                            node.value = value
                            applied_count += 1
                            self.logger.debug(f"Applied GenICam node '{node_name}' = {value}")
                    except Exception as e:
                        self.logger.debug(f"Could not apply GenICam node '{node_name}': {e}")

                return applied_count

            applied_count = await self._sdk(_apply_nodes, timeout=self._op_timeout_s)
            self.logger.debug(
                f"Applied {applied_count}/{len(node_config)} GenICam nodes for camera '{self.camera_name}'"
            )

        except Exception as e:
            self.logger.warning(f"GenICam node application failed for camera '{self.camera_name}': {str(e)}")

    async def _export_genicam_nodes(self) -> Dict[str, Any]:
        """Export key GenICam node values.

        Returns:
            Dictionary of node names to values
        """
        try:
            await self._ensure_connected()

            def _export_nodes():
                node_map = self.image_acquirer.remote_device.node_map
                nodes = {}

                # Common nodes to export
                node_names_to_export = [
                    "PixelFormat",
                    "AcquisitionMode",
                    "AcquisitionFrameRate",
                    "ExposureMode",
                    "GainAuto",
                    "BalanceWhiteAuto",
                    "BinningHorizontal",
                    "BinningVertical",
                    "ReverseX",
                    "ReverseY",
                    "TestPattern",
                ]

                for node_name in node_names_to_export:
                    try:
                        node = getattr(node_map, node_name, None)
                        if node is not None and hasattr(node, "value"):
                            nodes[node_name] = node.value
                    except Exception:
                        pass

                return nodes

            return await self._sdk(_export_nodes, timeout=self._op_timeout_s)

        except Exception as e:
            self.logger.warning(f"GenICam node export failed for camera '{self.camera_name}': {str(e)}")
            return {}

    async def set_ROI(self, x: int, y: int, width: int, height: int):
        """Set Region of Interest using GenICam nodes.

        Args:
            x: Left offset
            y: Top offset
            width: Width of ROI
            height: Height of ROI

        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If ROI parameters are invalid
            HardwareOperationError: If ROI setting fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            await self._ensure_connected()

            def _set_roi():
                node_map = self.image_acquirer.remote_device.node_map

                # Try common GenICam ROI node names
                offset_x_node = getattr(node_map, "OffsetX", None) or getattr(node_map, "RegionOffsetX", None)
                offset_y_node = getattr(node_map, "OffsetY", None) or getattr(node_map, "RegionOffsetY", None)
                width_node = getattr(node_map, "Width", None) or getattr(node_map, "RegionWidth", None)
                height_node = getattr(node_map, "Height", None) or getattr(node_map, "RegionHeight", None)

                # Set ROI parameters if nodes are available and writable
                if offset_x_node is not None and hasattr(offset_x_node, "value"):
                    try:
                        offset_x_node.value = x
                    except Exception as e:
                        self.logger.debug(f"Could not set OffsetX: {e}")

                if offset_y_node is not None and hasattr(offset_y_node, "value"):
                    try:
                        offset_y_node.value = y
                    except Exception as e:
                        self.logger.debug(f"Could not set OffsetY: {e}")

                if width_node is not None and hasattr(width_node, "value"):
                    try:
                        width_node.value = width
                    except Exception as e:
                        self.logger.debug(f"Could not set Width: {e}")

                if height_node is not None and hasattr(height_node, "value"):
                    try:
                        height_node.value = height
                    except Exception as e:
                        self.logger.debug(f"Could not set Height: {e}")

                # No return needed - void method

            await self._sdk(_set_roi, timeout=self._op_timeout_s)
            self.logger.debug(f"ROI set to ({x}, {y}, {width}, {height}) for camera '{self.camera_name}'")

        except Exception as e:
            self.logger.warning(f"ROI setting failed for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set ROI: {str(e)}")

    async def get_ROI(self) -> Dict[str, int]:
        """Get current ROI settings from GenICam nodes.

        Returns:
            Dictionary with 'x', 'y', 'width', 'height' keys

        Raises:
            CameraConnectionError: If camera is not initialized
        """
        if not self.initialized or self.image_acquirer is None:
            return {"x": 0, "y": 0, "width": 1920, "height": 1080}  # Default fallback

        try:
            await self._ensure_connected()

            def _get_roi():
                node_map = self.image_acquirer.remote_device.node_map

                # Try to get ROI values from common GenICam nodes
                x = 0
                y = 0
                width = 1920  # Default width
                height = 1080  # Default height

                # Get offset X
                offset_x_node = getattr(node_map, "OffsetX", None) or getattr(node_map, "RegionOffsetX", None)
                if offset_x_node is not None:
                    try:
                        x = offset_x_node.value
                    except Exception:
                        pass

                # Get offset Y
                offset_y_node = getattr(node_map, "OffsetY", None) or getattr(node_map, "RegionOffsetY", None)
                if offset_y_node is not None:
                    try:
                        y = offset_y_node.value
                    except Exception:
                        pass

                # Get width
                width_node = getattr(node_map, "Width", None) or getattr(node_map, "RegionWidth", None)
                if width_node is not None:
                    try:
                        width = width_node.value
                    except Exception:
                        pass

                # Get height
                height_node = getattr(node_map, "Height", None) or getattr(node_map, "RegionHeight", None)
                if height_node is not None:
                    try:
                        height = height_node.value
                    except Exception:
                        pass

                return {"x": int(x), "y": int(y), "width": int(width), "height": int(height)}

            return await self._sdk(_get_roi, timeout=self._op_timeout_s)

        except Exception as e:
            self.logger.warning(f"ROI retrieval failed for camera '{self.camera_name}': {str(e)}")
            return {"x": 0, "y": 0, "width": 1920, "height": 1080}

    async def reset_ROI(self):
        """Reset ROI to maximum sensor area using GenICam nodes.

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If ROI reset fails
        """
        if not self.initialized or self.image_acquirer is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not initialized")

        try:
            await self._ensure_connected()

            def _reset_roi():
                node_map = self.image_acquirer.remote_device.node_map

                # Reset to maximum sensor size
                # First, set offsets to 0
                offset_x_node = getattr(node_map, "OffsetX", None) or getattr(node_map, "RegionOffsetX", None)
                if offset_x_node is not None:
                    try:
                        offset_x_node.value = 0
                    except Exception as e:
                        self.logger.debug(f"Could not reset OffsetX: {e}")

                offset_y_node = getattr(node_map, "OffsetY", None) or getattr(node_map, "RegionOffsetY", None)
                if offset_y_node is not None:
                    try:
                        offset_y_node.value = 0
                    except Exception as e:
                        self.logger.debug(f"Could not reset OffsetY: {e}")

                # Set width and height to maximum
                width_node = getattr(node_map, "Width", None) or getattr(node_map, "RegionWidth", None)
                if width_node is not None:
                    try:
                        # Try to get max width from node
                        max_width = getattr(width_node, "max", 1920)
                        width_node.value = max_width
                    except Exception as e:
                        self.logger.debug(f"Could not reset Width: {e}")

                height_node = getattr(node_map, "Height", None) or getattr(node_map, "RegionHeight", None)
                if height_node is not None:
                    try:
                        # Try to get max height from node
                        max_height = getattr(height_node, "max", 1080)
                        height_node.value = max_height
                    except Exception as e:
                        self.logger.debug(f"Could not reset Height: {e}")

                # No return needed - void method

            await self._sdk(_reset_roi, timeout=self._op_timeout_s)
            self.logger.debug(f"ROI reset to maximum sensor area for camera '{self.camera_name}'")

        except Exception as e:
            self.logger.warning(f"ROI reset failed for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to reset ROI: {str(e)}")

    async def set_capture_timeout(self, timeout_ms: int):
        """Set capture timeout in milliseconds.

        Args:
            timeout_ms: Timeout value in milliseconds

        Raises:
            ValueError: If timeout_ms is negative
        """
        if timeout_ms < 0:
            raise ValueError(f"Timeout must be non-negative, got {timeout_ms}")

        self.timeout_ms = timeout_ms
        self.logger.debug(f"Set capture timeout to {timeout_ms}ms for camera '{self.camera_name}'")

    async def get_capture_timeout(self) -> int:
        """Get current capture timeout in milliseconds.

        Returns:
            Current timeout value in milliseconds
        """
        return self.timeout_ms
