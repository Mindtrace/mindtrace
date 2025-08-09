"""Modern Camera Manager for Mindtrace Hardware System

A clean, intuitive camera management system that provides unified access to
multiple camera backends with async operations and proper resource management.

Key Features:
    - Automatic backend discovery and lazy loading
    - Clean async API with context manager support
    - Unified camera proxy interface
    - Thread-safe operations with proper locking
    - Comprehensive configuration management
    - Integrated error handling

Supported Backends:
    - Basler: Industrial cameras (pypylon SDK)
    - OpenCV: USB cameras and webcams
    - Mock backends for testing

Usage:
    # Simple usage
    async with CameraManager() as manager:
        cameras = manager.discover_cameras()
        camera = await manager.get_camera(cameras[0])
        image = await camera.capture()

    # With configuration
    async with CameraManager(include_mocks=True) as manager:
        cameras = manager.discover_cameras(["MockBasler"])  # example mock backend
        cam = await manager.get_camera(cameras[0])
        await cam.configure(exposure=20000, gain=2.5)
        image = await cam.capture("output.jpg")
"""

import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2

from mindtrace.core.base.mindtrace_base import Mindtrace
from mindtrace.hardware.cameras.backends.camera_backend import CameraBackend
from mindtrace.hardware.cameras.core.camera import Camera
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
    CameraTimeoutError,
)

# Backend discovery and lazy loading
_backend_cache = {
    "basler": {"checked": False, "available": False, "class": None},
    "opencv": {"checked": False, "available": False, "class": None},
}


def _discover_backend(backend_name: str, logger=None) -> Tuple[bool, Optional[Any]]:
    """Discover and cache backend availability."""
    cache_key = backend_name.lower()
    if cache_key not in _backend_cache:
        return False, None

    cache = _backend_cache[cache_key]
    if cache["checked"]:
        return cache["available"], cache["class"]

    try:
        if cache_key == "basler":
            from mindtrace.hardware.cameras.backends.basler import BASLER_AVAILABLE, BaslerCameraBackend

            cache["available"] = BASLER_AVAILABLE
            cache["class"] = BaslerCameraBackend if BASLER_AVAILABLE else None

        elif cache_key == "opencv":
            from mindtrace.hardware.cameras.backends.opencv import OPENCV_AVAILABLE, OpenCVCameraBackend

            cache["available"] = OPENCV_AVAILABLE
            cache["class"] = OpenCVCameraBackend if OPENCV_AVAILABLE else None

        if logger and cache["available"]:
            logger.debug(f"{backend_name} backend loaded successfully")

    except ImportError as e:
        cache["available"] = False
        cache["class"] = None
        if logger:
            logger.debug(f"{backend_name} backend not available: {e}")

    finally:
        cache["checked"] = True

    return cache["available"], cache["class"]


def _get_mock_camera(backend_name: str):
    """Get mock camera class for backend."""
    try:
        if backend_name.lower() == "basler":
            from mindtrace.hardware.cameras.backends.basler.mock_basler import MockBaslerCamera

            return MockBaslerCamera
        else:
            raise CameraInitializationError(f"Mock backend not available for {backend_name}")
    except ImportError as e:
        raise CameraInitializationError(f"Mock {backend_name} backend not available: {e}")


class CameraManager(Mindtrace):
    """Modern camera manager with clean API and automatic backend discovery.

    Provides unified access to multiple camera backends with proper resource
    management, async operations, and comprehensive error handling.
    """

    def __init__(self, include_mocks: bool = False, max_concurrent_captures: int | None = None, **kwargs):
        """Initialize camera manager.

        Args:
            include_mocks: Include mock cameras in discovery
            max_concurrent_captures: Maximum number of concurrent captures across all cameras
                                    (important for network bandwidth management, especially for GigE cameras).
                                    If None, uses value from configuration system.
        """
        super().__init__(**kwargs)

        self._cameras: Dict[str, Camera] = {}
        self._include_mocks = include_mocks
        self.logger.debug(f"Initializing CameraManager (include_mocks={include_mocks})")
        self._discovered_backends = self._discover_all_backends()

        # Get max_concurrent_captures from config if not provided
        if max_concurrent_captures is None:
            from mindtrace.hardware.core.config import get_hardware_config

            config = get_hardware_config()
            max_concurrent_captures = config.get_config().cameras.max_concurrent_captures

        # Network bandwidth management - global semaphore to limit concurrent captures
        # This prevents network saturation when multiple GigE cameras capture simultaneously
        # Typical GigE bandwidth: 125 MB/s, high-res image: ~6MB, so limit concurrent captures
        self._capture_semaphore = asyncio.Semaphore(max_concurrent_captures)

        self.logger.info(
            f"CameraManager initialized. Available backends: {self._discovered_backends}, "
            f"max_concurrent_captures={max_concurrent_captures}"
        )

    def _discover_all_backends(self) -> List[str]:
        """Discover all available camera backends."""
        backends = []

        # Check hardware backends
        for backend_name in ["Basler", "OpenCV"]:
            self.logger.debug(f"Checking availability for backend '{backend_name}'")
            available, _ = _discover_backend(backend_name, self.logger)
            if available:
                backends.append(backend_name)
                self.logger.debug(f"Backend '{backend_name}' available")
            else:
                self.logger.debug(f"Backend '{backend_name}' not available")

        # Add mock backends if requested
        if self._include_mocks:
            backends.extend(["MockBasler"])
            self.logger.debug("Including mock backends: ['MockBasler']")

        return backends

    def get_available_backends(self) -> List[str]:
        """Get list of available backend names."""
        return self._discovered_backends.copy()

    def get_backend_info(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed information about all backends."""
        info = {}

        for backend in ["Basler", "OpenCV"]:
            available, _ = _discover_backend(backend.lower())
            info[backend] = {"available": available, "type": "hardware", "sdk_required": True}

        if self._include_mocks:
            info["MockBasler"] = {"available": True, "type": "mock", "sdk_required": False}

        return info

    def discover_cameras(self, backends: Optional[Union[str, List[str]]] = None) -> List[str]:
        """Discover available cameras across specified backends or all backends.

        Args:
            backends: Optional backend(s) to discover cameras from. Can be:
                     - None: Discover from all available backends (default behavior)
                     - str: Single backend name (e.g., "Basler", "OpenCV")
                     - List[str]: Multiple backend names (e.g., ["Basler", "OpenCV"])

        Returns:
            List of camera names in format "Backend:device_name"

        Examples:
            # Discover all cameras (existing behavior)
            all_cameras = manager.discover_cameras()

            # Discover only Basler cameras
            basler_cameras = manager.discover_cameras("Basler")

            # Discover from multiple specific backends
            cameras = manager.discover_cameras(["Basler", "OpenCV"])
        """
        all_cameras = []

        # Determine which backends to search
        if backends is None:
            # Default behavior: search all discovered backends
            backends_to_search = self._discovered_backends
        elif isinstance(backends, str):
            # Single backend specified
            backends_to_search = [backends]
        elif isinstance(backends, list):
            # Multiple backends specified
            backends_to_search = backends
        else:
            raise ValueError(f"Invalid backends parameter: {backends}. Must be None, str, or List[str]")

        self.logger.debug(f"Discovering cameras. Backends requested: {backends_to_search}")

        # Validate that specified backends are available
        for backend in backends_to_search:
            if backend not in self._discovered_backends:
                self.logger.warning(
                    f"Backend '{backend}' not available or not discovered. Available backends: {self._discovered_backends}"
                )
                continue

        # Filter to only include available backends
        backends_to_search = [b for b in backends_to_search if b in self._discovered_backends]
        self.logger.debug(f"Backends to search after filtering: {backends_to_search}")

        for backend in backends_to_search:
            try:
                if backend in ["Basler", "OpenCV"]:
                    available, camera_class = _discover_backend(backend.lower(), self.logger)
                    if available and camera_class:
                        cameras = camera_class.get_available_cameras()
                        self.logger.debug(f"Found {len(cameras)} cameras for backend '{backend}'")
                        all_cameras.extend([f"{backend}:{cam}" for cam in cameras])

                elif backend.startswith("Mock"):
                    backend_name = backend.replace("Mock", "").lower()
                    mock_class = _get_mock_camera(backend_name)
                    cameras = mock_class.get_available_cameras()
                    self.logger.debug(f"Found {len(cameras)} mock cameras for backend '{backend}'")
                    all_cameras.extend([f"{backend}:{cam}" for cam in cameras])

            except Exception as e:
                self.logger.error(f"Camera discovery failed for {backend}: {e}")

        return all_cameras

    def _parse_camera_name(self, camera_name: str) -> Tuple[str, str]:
        """Parse full camera name into backend and device name."""
        if ":" not in camera_name:
            self.logger.error(
                f"Invalid camera name format received: '{camera_name}'. Expected 'Backend:device_name'"
            )
            raise CameraConfigurationError(
                f"Invalid camera name format: '{camera_name}'. Expected 'Backend:device_name'"
            )

        backend, device_name = camera_name.split(":", 1)
        return backend, device_name

    def _create_camera_instance(self, backend: str, device_name: str, **kwargs) -> CameraBackend:
        """Create camera instance for specified backend."""
        if backend not in self._discovered_backends:
            self.logger.error(f"Requested backend '{backend}' not in discovered backends: {self._discovered_backends}")
            raise CameraNotFoundError(f"Backend '{backend}' not available")

        try:
            if backend in ["Basler", "OpenCV"]:
                available, camera_class = _discover_backend(backend.lower(), self.logger)
                if not available or not camera_class:
                    self.logger.error(f"Requested backend '{backend}' is not available or has no class")
                    raise CameraNotFoundError(f"Backend '{backend}' not available")
                self.logger.debug(f"Creating camera instance for {backend}:{device_name}")
                return camera_class(device_name, **kwargs)

            elif backend.startswith("Mock"):
                backend_name = backend.replace("Mock", "").lower()
                self.logger.debug(f"Creating mock camera instance for {backend}:{device_name}")
                mock_class = _get_mock_camera(backend_name)
                return mock_class(device_name, **kwargs)

            else:
                self.logger.error(f"Unknown backend requested: {backend}")
                raise CameraNotFoundError(f"Unknown backend: {backend}")

        except Exception as e:
            self.logger.error(f"Failed to create camera '{backend}:{device_name}': {e}")
            raise CameraInitializationError(f"Failed to create camera '{backend}:{device_name}': {e}")

    async def initialize_camera(self, camera_name: str, test_connection: bool = True, **kwargs) -> None:
        """Initialize a single camera with optional connection testing.

        Args:
            camera_name: Full camera name "Backend:device_name"
            test_connection: Whether to test camera by capturing a test image
            **kwargs: Camera configuration parameters

        Raises:
            CameraInitializationError: If camera initialization fails
            CameraConnectionError: If connection test fails
            ValueError: If camera is already initialized
        """
        # Check if already initialized
        if camera_name in self._cameras:
            self.logger.warning(f"Camera '{camera_name}' is already initialized")
            raise ValueError(f"Camera '{camera_name}' is already initialized")

        # Parse and validate camera name
        backend, device_name = self._parse_camera_name(camera_name)

        # Create camera instance
        self.logger.debug(f"Creating camera backend instance for '{camera_name}'")
        camera = self._create_camera_instance(backend, device_name, **kwargs)

        # Initialize camera
        try:
            self.logger.debug(f"Setting up camera backend for '{camera_name}'")
            await camera.setup_camera()
            self.logger.debug(f"Camera backend setup completed for '{camera_name}'")
        except Exception as e:
            self.logger.error(f"Failed to initialize camera '{camera_name}': {e}")
            raise CameraInitializationError(f"Failed to initialize camera '{camera_name}': {e}")

        # Test camera connection by attempting to capture
        if test_connection:
            self.logger.info(f"Testing connection for camera '{camera_name}'...")
            try:
                success = await camera.check_connection()
                if not success:
                    # Try actual capture as additional test
                    success, test_image = await camera.capture()
                    if not success or test_image is None:
                        await camera.close()  # Clean up before raising
                        raise CameraConnectionError(
                            f"Camera '{camera_name}' failed connection test - could not capture test image"
                        )

                self.logger.info(f"Camera '{camera_name}' passed connection test")

            except Exception as e:
                await camera.close()  # Clean up before raising
                if isinstance(e, CameraConnectionError):
                    raise
                raise CameraConnectionError(f"Camera '{camera_name}' connection test failed: {e}")

        # Create proxy and store
        proxy = Camera(camera, camera_name)
        self._cameras[camera_name] = proxy

        self.logger.info(f"Camera '{camera_name}' initialized successfully")

    async def initialize_cameras(self, camera_names: List[str], test_connections: bool = True, **kwargs) -> List[str]:
        """Initialize multiple cameras with optional connection testing.

        Args:
            camera_names: List of camera names to initialize
            test_connections: Whether to test camera connections
            **kwargs: Camera configuration parameters

        Returns:
            List of camera names that failed to initialize
        """
        failed_cameras = []

        self.logger.info(f"Initializing {len(camera_names)} cameras...")

        for camera_name in camera_names:
            try:
                # Skip if already initialized
                if camera_name in self._cameras:
                    self.logger.info(f"Camera '{camera_name}' already initialized")
                    continue

                # Initialize camera with connection testing
                await self.initialize_camera(camera_name, test_connection=test_connections, **kwargs)
                self.logger.info(f"Camera '{camera_name}' initialized successfully")

            except (CameraInitializationError, CameraConnectionError, ValueError) as e:
                self.logger.error(f"Failed to initialize camera '{camera_name}': {e}")
                failed_cameras.append(camera_name)

                # Clean up any partial initialization
                if camera_name in self._cameras:
                    try:
                        await self.close_camera(camera_name)
                    except Exception:
                        pass  # Already failed, ignore cleanup errors

            except Exception as e:
                self.logger.error(f"Unexpected error initializing camera '{camera_name}': {e}")
                failed_cameras.append(camera_name)

        if failed_cameras:
            self.logger.warning(f"Failed to initialize cameras: {failed_cameras}")
        else:
            self.logger.info("All cameras initialized successfully")

        return failed_cameras

    def get_camera(self, camera_name: str) -> Camera:
        """Get an initialized camera by name.

        Args:
            camera_name: Full camera name "Backend:device_name"

        Returns:
            Camera instance

        Raises:
            KeyError: If camera is not initialized
        """
        if camera_name not in self._cameras:
            self.logger.error(f"Requested camera '{camera_name}' is not initialized")
            raise KeyError(f"Camera '{camera_name}' is not initialized. Use initialize_camera() first.")

        return self._cameras[camera_name]

    def get_cameras(self, camera_names: List[str]) -> Dict[str, Camera]:
        """Get multiple initialized cameras by name.

        Args:
            camera_names: List of camera names to retrieve

        Returns:
            Dictionary mapping camera names to Camera instances.
            Only includes successfully retrieved cameras.
        """
        cameras = {}

        for camera_name in camera_names:
            try:
                cameras[camera_name] = self.get_camera(camera_name)
            except KeyError as e:
                self.logger.warning(f"Could not retrieve camera '{camera_name}': {e}")

        return cameras

    def get_active_cameras(self) -> List[str]:
        """Get names of currently active (initialized) cameras.

        Returns:
            List of camera names that are currently initialized and active
        """
        return list(self._cameras.keys())

    def get_max_concurrent_captures(self) -> int:
        """Get the current maximum number of concurrent captures.

        Returns:
            Current maximum concurrent captures limit
        """
        return self._capture_semaphore._value

    def set_max_concurrent_captures(self, max_captures: int) -> None:
        """Set the maximum number of concurrent captures allowed.

        This is important for network bandwidth management, especially for GigE cameras.
        Typical values:
        - 1: Conservative, ensures no network saturation
        - 2: Balanced, allows some concurrency while managing bandwidth
        - 3+: Aggressive, may cause network issues with many high-res cameras

        Args:
            max_captures: Maximum number of concurrent captures

        Raises:
            ValueError: If max_captures is less than 1
        """
        if max_captures < 1:
            raise ValueError("max_captures must be at least 1")

        # Create new semaphore with updated limit
        self._capture_semaphore = asyncio.Semaphore(max_captures)
        self.logger.info(f"Max concurrent captures set to {max_captures}")

    def get_network_bandwidth_info(self) -> Dict[str, Any]:
        """Get information about network bandwidth management.

        Returns:
            Dictionary with bandwidth management information including:
            - max_concurrent_captures: Current limit
            - active_cameras: Number of active cameras
            - gige_cameras: Number of GigE cameras (Basler)
            - bandwidth_management_enabled: Always True
            - recommended_settings: Recommended limits for different scenarios
        """
        return {
            "max_concurrent_captures": self.get_max_concurrent_captures(),
            "active_cameras": len(self._cameras),
            "gige_cameras": len([cam for cam in self._cameras.keys() if "Basler" in cam]),
            "bandwidth_management_enabled": True,
            "recommended_settings": {
                "conservative": 1,  # For critical applications
                "balanced": 2,  # For most applications
                "aggressive": 3,  # Only for high-bandwidth networks
            },
        }

    async def close_camera(self, camera_name: str) -> None:
        """Close and remove a specific camera.

        This method safely closes the camera connection, releases resources,
        and removes the camera from the active cameras list.

        Args:
            camera_name: Name of the camera to close

        Raises:
            Exception: If error occurs during camera closure
        """
        if camera_name in self._cameras:
            try:
                await self._cameras[camera_name].close()
                del self._cameras[camera_name]
                self.logger.info(f"Camera '{camera_name}' closed")
            except Exception as e:
                self.logger.error(f"Error closing camera '{camera_name}': {e}")
                raise

    async def close_all_cameras(self) -> None:
        """Close all active cameras.

        This method attempts to close all cameras, continuing even if some
        fail to close properly. Errors are logged but do not stop the process.
        """
        for camera_name in list(self._cameras.keys()):
            try:
                await self.close_camera(camera_name)
            except Exception as e:
                self.logger.error(f"Error closing camera '{camera_name}': {e}")

    async def batch_configure(self, configurations: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """Configure multiple cameras simultaneously.

        Args:
            configurations: Dict mapping camera names to their settings

        Returns:
            Dict mapping camera names to success status
        """
        results = {}

        # Execute all configurations in parallel
        async def configure_camera(camera_name: str, settings: Dict[str, Any]) -> Tuple[str, bool]:
            try:
                camera = self.get_camera(camera_name)  # Now synchronous retrieval
                success = await camera.configure(**settings)
                return camera_name, success
            except Exception as e:
                self.logger.error(f"Configuration failed for '{camera_name}': {e}")
                return camera_name, False

        tasks = [configure_camera(name, settings) for name, settings in configurations.items()]

        config_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in config_results:
            if isinstance(result, BaseException):
                self.logger.error(f"Configuration task failed: {result}")
            else:
                camera_name, success = result
                results[camera_name] = success

        return results

    async def batch_capture(self, camera_names: List[str]) -> Dict[str, Any]:
        """Capture from multiple cameras with network bandwidth management.

        Uses a global semaphore to limit concurrent captures to prevent network saturation,
        especially important for GigE cameras where bandwidth is limited.

        Args:
            camera_names: List of camera names to capture from

        Returns:
            Dict mapping camera names to captured images
        """
        results = {}

        async def capture_from_camera(camera_name: str) -> Tuple[str, Any]:
            try:
                # Acquire semaphore to limit concurrent captures (network bandwidth management)
                async with self._capture_semaphore:
                    camera = self.get_camera(camera_name)
                    image = await camera.capture()
                    return camera_name, image
            except Exception as e:
                self.logger.error(f"Capture failed for '{camera_name}': {e}")
                return camera_name, None

        tasks = [capture_from_camera(name) for name in camera_names]
        capture_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in capture_results:
            if isinstance(result, BaseException):
                self.logger.error(f"Capture task failed: {result}")
            else:
                camera_name, image = result
                results[camera_name] = image

        return results

    async def batch_capture_hdr(
        self,
        camera_names: List[str],
        save_path_pattern: Optional[str] = None,
        exposure_levels: int = 3,
        exposure_multiplier: float = 2.0,
        return_images: bool = True,
    ) -> Dict[str, Union[List[Any], bool]]:
        """Capture HDR images from multiple cameras simultaneously.

        Args:
            camera_names: List of camera names to capture HDR from
            save_path_pattern: Optional path pattern. Use {camera} and {exposure} placeholders.
                              Example: "hdr_{camera}_{exposure}.jpg"
            exposure_levels: Number of different exposure levels to capture
            exposure_multiplier: Multiplier between exposure levels
            return_images: Whether to return the captured images

        Returns:
            Dict mapping camera names to HDR capture results

        Example:
            # Capture HDR from multiple cameras
            results = await manager.batch_capture_hdr(
                ["Basler:cam2"],
                save_path_pattern="hdr_{camera}_{exposure}.jpg",
                exposure_levels=5
            )
        """
        results = {}

        async def capture_hdr_from_camera(camera_name: str) -> Tuple[str, Union[List[Any], bool]]:
            try:
                # Acquire semaphore to limit concurrent captures (network bandwidth management)
                async with self._capture_semaphore:
                    camera = self.get_camera(camera_name)

                    # Format save path for this camera
                    camera_save_pattern = None
                    if save_path_pattern:
                        # Replace {camera} placeholder with camera name (sanitized)
                        safe_camera_name = camera_name.replace(":", "_")
                        camera_save_pattern = save_path_pattern.replace("{camera}", safe_camera_name)

                    result = await camera.capture_hdr(
                        save_path_pattern=camera_save_pattern,
                        exposure_levels=exposure_levels,
                        exposure_multiplier=exposure_multiplier,
                        return_images=return_images,
                    )
                    return camera_name, result
            except Exception as e:
                self.logger.error(f"HDR capture failed for '{camera_name}': {e}")
                return camera_name, [] if return_images else False

        tasks = [capture_hdr_from_camera(name) for name in camera_names]
        hdr_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in hdr_results:
            if isinstance(result, BaseException):
                self.logger.error(f"HDR capture task failed: {result}")
            else:
                camera_name, hdr_result = result
                results[camera_name] = hdr_result

        return results

    # Context manager support
    async def __aenter__(self):
        """Async context manager entry."""
        self.logger.debug("Entering CameraManager context")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with proper cleanup."""
        self.logger.debug("Exiting CameraManager context; closing all cameras")
        await self.close_all_cameras()

    def __del__(self):
        """Destructor warning for improper cleanup."""
        if hasattr(self, "_cameras") and self._cameras:
            if hasattr(self, "logger"):
                self.logger.warning(
                    f"CameraManager destroyed with {len(self._cameras)} active cameras. "
                    "Use 'async with CameraManager()' for proper cleanup."
                )


# Convenience functions for quick access
async def initialize_and_get_camera(camera_name: str, **kwargs) -> Camera:
    """Quick access function to initialize and get a single camera.

    Args:
        camera_name: Camera name "Backend:device_name"
        **kwargs: Camera configuration parameters

    Returns:
        Camera instance
    """
    manager = CameraManager()
    await manager.initialize_camera(camera_name, **kwargs)
    return manager.get_camera(camera_name)


def discover_all_cameras(
    include_mocks: bool = False, max_concurrent_captures: int = 2, backends: Optional[Union[str, List[str]]] = None
) -> List[str]:
    """Quick function to discover cameras from all or specific backends.

    Args:
        include_mocks: Include mock cameras in discovery
        max_concurrent_captures: Maximum concurrent captures for network bandwidth management
        backends: Optional backend(s) to discover cameras from. Can be:
                 - None: Discover from all available backends (default)
                 - str: Single backend name (e.g., "Basler", "OpenCV")
                 - List[str]: Multiple backend names (e.g., ["Basler", "OpenCV"])

    Returns:
        List of available camera names

    Examples:
        # Discover all cameras
        all_cameras = discover_all_cameras()

        # Discover only Basler cameras
        basler_cameras = discover_all_cameras(backends="Basler")

        # Discover from multiple backends
        cameras = discover_all_cameras(backends=["Basler", "OpenCV"])
    """
    manager = CameraManager(include_mocks=include_mocks, max_concurrent_captures=max_concurrent_captures)
    return manager.discover_cameras(backends=backends) 
