"""Async camera manager for Mindtrace hardware cameras."""

import asyncio
from typing import Any, Dict, List, Optional, Tuple, Union

from mindtrace.core import Mindtrace
from mindtrace.hardware.cameras.backends.camera_backend import CameraBackend
from mindtrace.hardware.cameras.core.async_camera import AsyncCamera
from mindtrace.hardware.core.exceptions import (
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
)

try:
    from mindtrace.storage.gcs import GCSStorageHandler

    STORAGE_AVAILABLE = True
except ImportError:
    GCSStorageHandler = None
    STORAGE_AVAILABLE = False


class AsyncCameraManager(Mindtrace):
    """Mindtrace Async Camera Manager class.

    A clean, intuitive camera management system that provides unified access to multiple camera backends with async
    operations and proper resource management.

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

    Usage::

        # Simple usage
        async with AsyncCameraManager() as manager:
            cameras = manager.discover()
            camera = await manager.open(cameras[0])
            image = await camera.capture()

        # With configuration
        async with AsyncCameraManager(include_mocks=True) as manager:
            cameras = manager.discover(["MockBasler"])  # example mock backend
            cam = await manager.open(cameras[0])
            await cam.configure(exposure=20000, gain=2.5)
            image = await cam.capture("output.jpg")
    """

    # Backend discovery and lazy loading (class-level cache shared across instances)
    _backend_cache: Dict[str, Dict[str, Any]] = {
        "basler": {"checked": False, "available": False, "class": None},
        "opencv": {"checked": False, "available": False, "class": None},
    }

    def __init__(self, include_mocks: bool = False, max_concurrent_captures: int | None = None, **kwargs):
        """Initialize camera manager.

        Args:
            include_mocks: Include mock cameras in discovery
            max_concurrent_captures: Maximum number of concurrent captures across all cameras
                                    (important for network bandwidth management, especially for GigE cameras).
                                    If None, uses value from configuration system.
        """
        super().__init__(**kwargs)

        self._cameras: Dict[str, AsyncCamera] = {}
        self._include_mocks = include_mocks
        self.logger.debug(f"Initializing AsyncCameraManager (include_mocks={include_mocks})")
        self._discovered_backends = self._discover_all_backends()

        # Get config
        from mindtrace.hardware.core.config import get_hardware_config

        self._hardware_config = get_hardware_config().get_config()

        # Get max_concurrent_captures from config if not provided
        if max_concurrent_captures is None:
            max_concurrent_captures = self._hardware_config.cameras.max_concurrent_captures

        # Network bandwidth management - global semaphore to limit concurrent captures
        self._capture_semaphore = asyncio.Semaphore(max_concurrent_captures)
        self._max_concurrent_captures = max_concurrent_captures

        self.logger.info(
            f"AsyncCameraManager initialized. Available backends: {self._discovered_backends}, "
            f"max_concurrent_captures={max_concurrent_captures}"
        )

    def backends(self) -> List[str]:
        """Available backend names."""
        return self._discovered_backends.copy()

    def backend_info(self) -> Dict[str, Dict[str, Any]]:
        """Detailed information about all backends."""
        info: Dict[str, Dict[str, Any]] = {}
        for backend in ["Basler", "OpenCV"]:
            available, _ = self._discover_backend(backend.lower())
            info[backend] = {"available": available, "type": "hardware", "sdk_required": True}
        if self._include_mocks:
            info["MockBasler"] = {"available": True, "type": "mock", "sdk_required": False}
        return info

    @classmethod
    def discover(
        cls,
        backends: Optional[Union[str, List[str]]] = None,
        details: bool = False,
        include_mocks: bool = False,
    ) -> Union[List[str], List[Dict[str, Any]]]:
        """Discover available cameras across specified backends or all backends.

        Args:
            backends: Optional backend(s) to discover cameras from. Can be:
                - None: Discover from all available backends (default behavior)
                - str: Single backend name (e.g., "Basler", "OpenCV")
                - List[str]: Multiple backend names (e.g., ["Basler", "OpenCV"])
            details: If True, return a list of dicts with detailed camera information.

        Returns:
            If details is False (default): List of camera names in format "Backend:device_name".
            If details is True: List of records with keys {name, backend, index, width, height, fps}.

        Raises:
            ValueError: If backends parameter is not None, str, or List[str].

        Example::

            # Discover all cameras
            cameras = manager.discover()

            # Discover only Basler cameras
            baslers = manager.discover("Basler")

            # Discover multiple backends
            mixed = manager.discover(["Basler", "OpenCV"])"""
        all_cameras: List[str] = []
        all_details: List[Dict[str, Any]] = []

        # Determine which backends to search
        if backends is None:
            # Compute discovered backends for this call
            discovered = []
            try:
                available, _ = cls._discover_backend("opencv")
                if available:
                    discovered.append("OpenCV")
            except Exception:
                pass
            try:
                available, _ = cls._discover_backend("basler")
                if available:
                    discovered.append("Basler")
            except Exception:
                pass
            if include_mocks:
                discovered.append("MockBasler")
            backends_to_search = discovered
        elif isinstance(backends, str):
            backends_to_search = [backends]
        elif isinstance(backends, list):
            backends_to_search = backends
        else:
            raise ValueError(f"Invalid backends parameter: {backends}. Must be None, str, or List[str]")

        try:
            cls.logger.debug(f"Discovering cameras. Backends requested: {backends_to_search}")
        except Exception:
            pass

        # Validate specified backends
        for backend in backends_to_search:
            valid = {"OpenCV", "Basler"}
            if include_mocks:
                valid.add("MockBasler")
            if backend not in valid:
                try:
                    cls.logger.warning(
                        f"Backend '{backend}' not available or not discovered. Available backends: {sorted(list(valid))}"
                    )
                except Exception:
                    pass
                continue

        # Filter
        valid_list = []
        for b in backends_to_search:
            if b == "OpenCV":
                available, _ = cls._discover_backend("opencv")
                if available:
                    valid_list.append(b)
            elif b == "Basler":
                available, _ = cls._discover_backend("basler")
                if available:
                    valid_list.append(b)
            elif b == "MockBasler" and include_mocks:
                valid_list.append(b)
        backends_to_search = valid_list
        try:
            cls.logger.debug(f"Backends to search after filtering: {backends_to_search}")
        except Exception:
            pass

        for backend in backends_to_search:
            try:
                if backend == "OpenCV":
                    from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import (
                        OpenCVCameraBackend,
                    )

                    if details:
                        det = OpenCVCameraBackend.get_available_cameras(include_details=True)
                        try:
                            cls.logger.debug(f"Found {len(det)} OpenCV cameras (detailed)")
                        except Exception:
                            pass
                        for cam_name, d in det.items():
                            try:
                                idx = int(d.get("index", -1))
                            except Exception:
                                idx = -1
                            try:
                                w = int(d.get("width", 0))
                            except Exception:
                                w = 0
                            try:
                                h = int(d.get("height", 0))
                            except Exception:
                                h = 0
                            try:
                                fps = float(d.get("fps", 0.0))
                            except Exception:
                                fps = 0.0
                            all_details.append(
                                {
                                    "name": f"{backend}:{cam_name}",
                                    "backend": backend,
                                    "index": idx,
                                    "width": w,
                                    "height": h,
                                    "fps": fps,
                                }
                            )
                    else:
                        cameras = OpenCVCameraBackend.get_available_cameras()
                        try:
                            cls.logger.debug(f"Found {len(cameras)} cameras for backend '{backend}'")
                        except Exception:
                            pass
                        all_cameras.extend([f"{backend}:{cam}" for cam in cameras])
                elif backend == "Basler":
                    available, camera_class = cls._discover_backend(backend.lower())
                    if available and camera_class:
                        cameras = camera_class.get_available_cameras()
                        try:
                            cls.logger.debug(f"Found {len(cameras)} cameras for backend '{backend}'")
                        except Exception:
                            pass
                        if details:
                            for cam in cameras:
                                # Detailed discovery for Basler not available at this stage
                                all_details.append(
                                    {
                                        "name": f"{backend}:{cam}",
                                        "backend": backend,
                                        "index": None,
                                        "width": 0,
                                        "height": 0,
                                        "fps": 0.0,
                                    }
                                )
                        else:
                            all_cameras.extend([f"{backend}:{cam}" for cam in cameras])
                elif backend == "MockBasler" and include_mocks:
                    backend_key = backend.replace("Mock", "").lower()
                    mock_class = cls._get_mock_camera(backend_key)
                    cameras = mock_class.get_available_cameras()
                    try:
                        cls.logger.debug(f"Found {len(cameras)} mock cameras for backend '{backend}'")
                    except Exception:
                        pass
                    if details:
                        for cam in cameras:
                            # Attempt to parse index from name suffix
                            try:
                                idx = int(cam.split("_")[-1])
                            except Exception:
                                idx = -1
                            all_details.append(
                                {
                                    "name": f"{backend}:{cam}",
                                    "backend": backend,
                                    "index": idx,
                                    "width": 0,
                                    "height": 0,
                                    "fps": 0.0,
                                }
                            )
                    else:
                        all_cameras.extend([f"{backend}:{cam}" for cam in cameras])
                else:
                    try:
                        cls.logger.warning(f"Unknown backend '{backend}' requested during discovery")
                    except Exception:
                        pass
            except Exception as e:
                try:
                    cls.logger.warning(f"Failed discovery for backend '{backend}': {e}")
                except Exception:
                    pass

        if details:
            return all_details
        return all_cameras

    async def open(
        self, names: Optional[Union[str, List[str]]] = None, test_connection: bool = True, **kwargs
    ) -> Union[AsyncCamera, Dict[str, AsyncCamera]]:
        """Open one or more cameras with optional connection testing.

        Args:
            names: Camera name or list of names in the form "Backend:device_name". If None, opens the first available camera (preferring OpenCV).
            test_connection: Whether to test camera connection(s) after opening.
            **kwargs: Camera configuration parameters.

        Returns:
            AsyncCamera if a single name was provided, otherwise a dict mapping names to AsyncCamera.
        """
        # If no name provided, choose the first available (prefer OpenCV)
        if names is None:
            try:
                names_list = self.discover(["OpenCV"])  # type: ignore[assignment]
            except Exception:
                names_list = []
            target: Optional[str] = None
            if isinstance(names_list, list) and names_list:
                target = names_list[0]
            if target is None:
                all_names = self.discover()  # type: ignore[assignment]
                if isinstance(all_names, list) and all_names:
                    target = all_names[0]
            if target is None:
                raise CameraNotFoundError("No cameras available to open by default")
            names = target

        if isinstance(names, str):
            camera_name = names
            if camera_name in self._cameras:
                # Idempotent: return existing proxy
                self.logger.warning(f"Camera '{camera_name}' already open; returning existing instance")
                return self._cameras[camera_name]

            backend, device_name = self._parse_camera_name(camera_name)
            self.logger.debug(f"Creating camera backend instance for '{camera_name}'")
            camera = self._create_camera_instance(backend, device_name, **kwargs)

            try:
                self.logger.debug(f"Setting up camera backend for '{camera_name}'")
                await camera.setup_camera()
                self.logger.debug(f"Camera backend setup completed for '{camera_name}'")
            except Exception as e:
                self.logger.error(f"Failed to initialize camera '{camera_name}': {e}")
                raise CameraInitializationError(f"Failed to initialize camera '{camera_name}': {e}")

            if test_connection:
                self.logger.info(f"Testing connection for camera '{camera_name}'...")
                try:
                    success = await camera.check_connection()
                    if not success:
                        test_image = await camera.capture()
                        if test_image is None:
                            await camera.close()
                            raise CameraConnectionError(
                                f"Camera '{camera_name}' failed connection test - could not capture test image"
                            )
                    self.logger.info(f"Camera '{camera_name}' passed connection test")
                except Exception as e:
                    await camera.close()
                    if isinstance(e, CameraConnectionError):
                        raise
                    raise CameraConnectionError(f"Camera '{camera_name}' connection test failed: {e}")

            proxy = AsyncCamera(camera, camera_name)
            self._cameras[camera_name] = proxy
            self.logger.info(f"Camera '{camera_name}' initialized successfully")
            return proxy

        # Multiple
        camera_names = names
        opened: Dict[str, AsyncCamera] = {}
        self.logger.info(f"Initializing {len(camera_names)} cameras...")
        for camera_name in camera_names:
            try:
                if camera_name in self._cameras:
                    self.logger.info(f"Camera '{camera_name}' already initialized")
                    opened[camera_name] = self._cameras[camera_name]
                    continue
                proxy = await self.open(camera_name, test_connection=test_connection, **kwargs)
                opened[camera_name] = proxy
                self.logger.info(f"Camera '{camera_name}' initialized successfully")
            except (CameraInitializationError, CameraConnectionError, ValueError) as e:
                self.logger.error(f"Failed to initialize camera '{camera_name}': {e}")
                if camera_name in self._cameras:
                    try:
                        await self.close(camera_name)
                    except Exception:
                        pass
            except Exception as e:
                self.logger.error(f"Unexpected error initializing camera '{camera_name}': {e}")
        if len(opened) != len(camera_names):
            missing = [n for n in camera_names if n not in opened]
            self.logger.warning(f"Some cameras failed to initialize: {missing}")
        else:
            self.logger.info("All cameras initialized successfully")
        return opened

    @property
    def active_cameras(self) -> List[str]:
        """Get names of currently active (initialized) cameras.

        Returns:
            List of camera names that are currently initialized and active
        """
        return list(self._cameras.keys())

    @property
    def max_concurrent_captures(self) -> int:
        """Get the current maximum number of concurrent captures.

        Returns:
            Current maximum concurrent captures limit
        """
        try:
            return self._max_concurrent_captures
        except AttributeError:
            # fallback if not yet set
            return 1

    @max_concurrent_captures.setter
    def max_concurrent_captures(self, max_captures: int) -> None:
        """Set the maximum number of concurrent captures allowed.

        Args:
            max_captures: Maximum number of concurrent captures

        Raises:
            ValueError: If max_captures is less than 1
        """
        if max_captures < 1:
            raise ValueError("max_captures must be at least 1")
        self._max_concurrent_captures = max_captures
        self._capture_semaphore = asyncio.Semaphore(max_captures)
        self.logger.info(f"Max concurrent captures set to {max_captures}")

    def diagnostics(self) -> Dict[str, Any]:
        """Get diagnostics information including bandwidth management."""
        return {
            "max_concurrent_captures": self.max_concurrent_captures,
            "active_cameras": len(self._cameras),
            "gige_cameras": len([cam for cam in self._cameras.keys() if "Basler" in cam]),
            "bandwidth_management_enabled": True,
            "recommended_settings": {
                "conservative": 1,
                "balanced": 2,
                "aggressive": 3,
            },
        }

    async def close(self, names: Optional[Union[str, List[str]]] = None) -> None:
        """Close one, many, or all cameras.

        Args:
            names: None to close all; str for single; list[str] for multiple.
        """
        if names is None:
            targets = list(self._cameras.keys())
        elif isinstance(names, str):
            targets = [names]
        else:
            targets = list(names)

        for camera_name in targets:
            if camera_name in self._cameras:
                try:
                    await self._cameras[camera_name].close()
                    del self._cameras[camera_name]
                    self.logger.info(f"Camera '{camera_name}' closed")
                except Exception as e:
                    self.logger.warning(f"Failed to close '{camera_name}': {e}")

    async def batch_configure(self, configurations: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """Configure multiple cameras simultaneously."""
        results = {}

        async def configure_camera(camera_name: str, settings: Dict[str, Any]) -> Tuple[str, bool]:
            try:
                if camera_name not in self._cameras:
                    raise KeyError(f"Camera '{camera_name}' is not initialized. Use open() first.")
                camera = self._cameras[camera_name]
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

    async def batch_capture(
        self, camera_names: List[str], upload_to_gcs: bool = False, output_format: str = "numpy"
    ) -> Dict[str, Any]:
        """Capture from multiple cameras with network bandwidth management."""
        results = {}

        async def capture_from_camera(camera_name: str) -> Tuple[str, Any]:
            try:
                async with self._capture_semaphore:
                    if camera_name not in self._cameras:
                        raise KeyError(f"Camera '{camera_name}' is not initialized. Use open() first.")
                    camera = self._cameras[camera_name]
                    image = await camera.capture(upload_to_gcs=upload_to_gcs, output_format=output_format)
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
        upload_to_gcs: bool = False,
        output_format: str = "numpy",
    ) -> Dict[str, Dict[str, Any]]:
        """Capture HDR images from multiple cameras simultaneously."""
        results = {}

        async def capture_hdr_from_camera(camera_name: str) -> Tuple[str, Dict[str, Any]]:
            try:
                async with self._capture_semaphore:
                    if camera_name not in self._cameras:
                        raise KeyError(f"Camera '{camera_name}' is not initialized. Use open() first.")
                    camera = self._cameras[camera_name]

                    camera_save_pattern = None
                    if save_path_pattern:
                        safe_camera_name = camera_name.replace(":", "_")
                        camera_save_pattern = save_path_pattern.replace("{camera}", safe_camera_name)

                    result = await camera.capture_hdr(
                        save_path_pattern=camera_save_pattern,
                        exposure_levels=exposure_levels,
                        exposure_multiplier=exposure_multiplier,
                        return_images=return_images,
                        upload_to_gcs=upload_to_gcs,
                        output_format=output_format,
                    )

                    # HDR upload will be handled by individual camera capture_hdr method

                    return camera_name, result
            except Exception as e:
                self.logger.error(f"HDR capture failed for '{camera_name}': {e}")
                return camera_name, {
                    "success": False,
                    "images": None,
                    "image_paths": None,
                    "gcs_urls": None,
                    "exposure_levels": [],
                    "successful_captures": 0,
                }

        tasks = [capture_hdr_from_camera(name) for name in camera_names]
        hdr_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in hdr_results:
            if isinstance(result, BaseException):
                self.logger.error(f"HDR capture task failed: {result}")
            else:
                camera_name, hdr_result = result
                results[camera_name] = hdr_result

        return results

    async def __aenter__(self):
        """Async context manager entry."""
        self.logger.debug("Entering AsyncCameraManager context")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with proper cleanup."""
        self.logger.debug("Exiting AsyncCameraManager context; closing all cameras")
        await self.close()

    def __del__(self):
        """Destructor warning for improper cleanup."""
        if hasattr(self, "_cameras") and self._cameras:
            if hasattr(self, "logger"):
                self.logger.warning(
                    f"AsyncCameraManager destroyed with {len(self._cameras)} active cameras. "
                    "Use 'async with AsyncCameraManager()' for proper cleanup."
                )

    # ===== Private API (helpers) =====
    def _discover_all_backends(self) -> List[str]:
        """Discover all available camera backends."""
        backends = []
        for backend_name in ["Basler", "OpenCV"]:
            self.logger.debug(f"Checking availability for backend '{backend_name}'")
            available, _ = self._discover_backend(backend_name)
            if available:
                backends.append(backend_name)
                self.logger.debug(f"Backend '{backend_name}' available")
            else:
                self.logger.debug(f"Backend '{backend_name}' not available")
        if self._include_mocks:
            backends.extend(["MockBasler"])
            self.logger.debug("Including mock backends: ['MockBasler']")
        return backends

    def _parse_camera_name(self, camera_name: str) -> Tuple[str, str]:
        """Parse full camera name into backend and device name."""
        if ":" not in camera_name:
            self.logger.error(f"Invalid camera name format received: '{camera_name}'. Expected 'Backend:device_name'")
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
                available, camera_class = self._discover_backend(backend.lower())
                if not available or not camera_class:
                    self.logger.error(f"Requested backend '{backend}' is not available or has no class")
                    raise CameraNotFoundError(f"Backend '{backend}' not available")
                self.logger.debug(f"Creating camera instance for {backend}:{device_name}")
                return camera_class(device_name, **kwargs)

            elif backend.startswith("Mock"):
                backend_name = backend.replace("Mock", "").lower()
                self.logger.debug(f"Creating mock camera instance for {backend}:{device_name}")
                mock_class = self._get_mock_camera(backend_name)
                return mock_class(device_name, **kwargs)

            else:
                self.logger.error(f"Unknown backend requested: {backend}")
                raise CameraNotFoundError(f"Unknown backend: {backend}")

        except Exception as e:
            self.logger.error(f"Failed to create camera '{backend}:{device_name}': {e}")
            raise CameraInitializationError(f"Failed to create camera '{backend}:{device_name}': {e}")

    @classmethod
    def _discover_backend(cls, backend_name: str) -> Tuple[bool, Optional[Any]]:
        """Discover and cache backend availability (class-wide)."""
        cache_key = backend_name.lower()
        if cache_key not in cls._backend_cache:
            return False, None

        cache = cls._backend_cache[cache_key]
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

            if cache["available"]:
                try:
                    cls.logger.debug(f"{backend_name} backend loaded successfully")
                except Exception:
                    pass

        except ImportError as e:
            cache["available"] = False
            cache["class"] = None
            try:
                cls.logger.debug(f"{backend_name} backend not available: {e}")
            except Exception:
                pass

        finally:
            cache["checked"] = True

        return cache["available"], cache["class"]

    @classmethod
    def _get_mock_camera(cls, backend_name: str):
        """Get mock camera class for backend (class method for consistent logging)."""
        try:
            if backend_name.lower() == "basler":
                from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import (
                    MockBaslerCameraBackend,
                )

                return MockBaslerCameraBackend
            else:
                raise CameraInitializationError(f"Mock backend not available for {backend_name}")
        except ImportError as e:
            raise CameraInitializationError(f"Mock {backend_name} backend not available: {e}")
