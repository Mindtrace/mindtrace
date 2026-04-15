"""Async camera manager for Mindtrace hardware cameras."""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from mindtrace.core import Mindtrace
from mindtrace.hardware.cameras.backends.camera_backend import CameraBackend
from mindtrace.hardware.cameras.core.async_camera import AsyncCamera
from mindtrace.hardware.cameras.core.capture_groups import (
    CaptureGroup,
    StageSetConfigDict,
    build_capture_groups,
    get_semaphore_for_capture,
    validate_stage_set_configs,
)
from mindtrace.hardware.core.exceptions import (
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
)


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
        "genicam": {"checked": False, "available": False, "class": None},
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

        # Performance settings that persist across camera open/close cycles
        self._timeout_ms = self._hardware_config.cameras.timeout_ms
        self._retrieve_retry_count = self._hardware_config.cameras.retrieve_retry_count

        # Stage+Set capture groups (per-group concurrency control)
        self._capture_groups: Dict[str, CaptureGroup] = {}
        self._camera_group_keys: Dict[str, List[str]] = {}

        # Auto-reconnection / failure tracking
        self._failure_counts: Dict[str, int] = {}
        self._last_reinit_attempt: Dict[str, float] = {}
        self._max_consecutive_failures = self._hardware_config.cameras.max_consecutive_failures
        self._reinitialization_cooldown = self._hardware_config.cameras.reinitialization_cooldown

        # Camera config preservation directory
        camera_config_dir = self._hardware_config.cameras.camera_config_dir
        if not camera_config_dir:
            camera_config_dir = str(
                Path(self._hardware_config.paths.config_dir).expanduser() / "cameras"
            )
        self._camera_config_dir = camera_config_dir

        self.logger.info(
            f"AsyncCameraManager initialized. Available backends: {self._discovered_backends}, "
            f"max_concurrent_captures={max_concurrent_captures}, "
            f"timeout_ms={self._timeout_ms}, retrieve_retry_count={self._retrieve_retry_count}"
        )

    def backends(self) -> List[str]:
        """Available backend names."""
        return self._discovered_backends.copy()

    def backend_info(self) -> Dict[str, Dict[str, Any]]:
        """Detailed information about all backends."""
        info: Dict[str, Dict[str, Any]] = {}
        for backend in ["Basler", "OpenCV", "GenICam"]:
            available, _ = self._discover_backend(backend.lower())
            info[backend] = {"available": available, "type": "hardware", "sdk_required": True}
        if self._include_mocks:
            info["MockBasler"] = {"available": True, "type": "mock", "sdk_required": False}
        return info

    # ------------------------------------------------------------------ #
    #  Discovery helpers (shared by discover / discover_async)            #
    # ------------------------------------------------------------------ #

    @classmethod
    def _resolve_backends(
        cls,
        backends: Optional[Union[str, List[str]]],
        include_mocks: bool = False,
    ) -> List[str]:
        """Normalize and filter the *backends* parameter to a validated list.

        Returns only backends whose SDK is actually importable on this machine.
        """
        # --- normalise input ---
        if backends is None:
            candidates = []
            for key, name in [("opencv", "OpenCV"), ("basler", "Basler"), ("genicam", "GenICam")]:
                try:
                    available, _ = cls._discover_backend(key)
                    if available:
                        candidates.append(name)
                except Exception:
                    pass
            if include_mocks:
                candidates.append("MockBasler")
        elif isinstance(backends, str):
            candidates = [backends]
        elif isinstance(backends, list):
            candidates = list(backends)
        else:
            raise ValueError(f"Invalid backends parameter: {backends}. Must be None, str, or List[str]")

        # --- filter to available ---
        valid_names = {"OpenCV", "Basler", "GenICam"}
        if include_mocks:
            valid_names.add("MockBasler")

        resolved = []
        for name in candidates:
            if name not in valid_names:
                try:
                    cls.logger.warning(f"Unknown backend '{name}'. Available: {sorted(valid_names)}")
                except Exception:
                    pass
                continue
            if name == "MockBasler":
                resolved.append(name)
            else:
                try:
                    available, _ = cls._discover_backend(name.lower())
                    if available:
                        resolved.append(name)
                except Exception:
                    pass

        try:
            cls.logger.debug(f"Resolved backends for discovery: {resolved}")
        except Exception:
            pass
        return resolved

    @staticmethod
    def _format_discovery_result(
        backend_name: str,
        cameras: Union[List[str], Dict[str, Dict[str, str]]],
        *,
        names_out: List[str],
        details_out: List[Dict[str, Any]],
        details: bool,
    ) -> None:
        """Append raw backend discovery results to the shared output lists."""

        def _safe_int(d: Dict, key: str, default: int = 0) -> int:
            try:
                return int(d.get(key, default))
            except Exception:
                return default

        def _safe_float(d: Dict, key: str, default: float = 0.0) -> float:
            try:
                return float(d.get(key, default))
            except Exception:
                return default

        if details:
            if isinstance(cameras, dict):
                for cam_name, info in cameras.items():
                    record: Dict[str, Any] = {
                        "name": f"{backend_name}:{cam_name}",
                        "backend": backend_name,
                        "index": _safe_int(info, "index", -1),
                        "width": _safe_int(info, "width"),
                        "height": _safe_int(info, "height"),
                        "fps": _safe_float(info, "fps"),
                    }
                    # GenICam-specific metadata
                    for field in (
                        "serial_number",
                        "model",
                        "vendor",
                        "interface",
                        "display_name",
                        "user_defined_name",
                        "device_id",
                    ):
                        if field in info:
                            record[field] = info.get(field, "")
                    details_out.append(record)
            elif isinstance(cameras, list):
                for cam in cameras:
                    idx: int = -1
                    try:
                        idx = int(cam.split("_")[-1])
                    except Exception:
                        pass
                    details_out.append(
                        {
                            "name": f"{backend_name}:{cam}",
                            "backend": backend_name,
                            "index": idx,
                            "width": 0,
                            "height": 0,
                            "fps": 0.0,
                        }
                    )
        else:
            if isinstance(cameras, dict):
                names_out.extend(f"{backend_name}:{cam}" for cam in cameras)
            elif isinstance(cameras, list):
                names_out.extend(f"{backend_name}:{cam}" for cam in cameras)

    # ------------------------------------------------------------------ #
    #  Public discovery API                                               #
    # ------------------------------------------------------------------ #

    @classmethod
    def discover(
        cls,
        backends: Optional[Union[str, List[str]]] = None,
        details: bool = False,
        include_mocks: bool = False,
    ) -> Union[List[str], List[Dict[str, Any]]]:
        """Discover available cameras across specified backends (sequential).

        Args:
            backends: Backend(s) to query. ``None`` auto-detects all available.
            details: Return detail dicts instead of name strings.
            include_mocks: Include mock backends.

        Returns:
            List of ``"Backend:device"`` strings, or list of detail dicts.

        Example::

            cameras = manager.discover()
            baslers = manager.discover("Basler")
            mixed   = manager.discover(["Basler", "OpenCV", "GenICam"])
        """
        backends_to_search = cls._resolve_backends(backends, include_mocks)

        all_cameras: List[str] = []
        all_details: List[Dict[str, Any]] = []

        for backend in backends_to_search:
            try:
                if backend == "OpenCV":
                    from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import (
                        OpenCVCameraBackend,
                    )

                    result = OpenCVCameraBackend.get_available_cameras(include_details=details)
                elif backend == "MockBasler":
                    mock_class = cls._get_mock_camera("basler")
                    result = mock_class.get_available_cameras()
                else:
                    available, camera_class = cls._discover_backend(backend.lower())
                    if not (available and camera_class):
                        continue
                    try:
                        result = camera_class.get_available_cameras(include_details=details)
                    except TypeError:
                        # Backend doesn't support include_details kwarg
                        result = camera_class.get_available_cameras()

                cls._format_discovery_result(
                    backend,
                    result,
                    names_out=all_cameras,
                    details_out=all_details,
                    details=details,
                )
            except Exception as e:
                try:
                    cls.logger.warning(f"Failed discovery for backend '{backend}': {e}")
                except Exception:
                    pass

        return all_details if details else all_cameras

    @classmethod
    async def discover_async(
        cls,
        backends: Optional[Union[str, List[str]]] = None,
        details: bool = False,
        include_mocks: bool = False,
    ) -> Union[List[str], List[Dict[str, Any]]]:
        """Discover available cameras across backends in parallel.

        Same interface as :meth:`discover` but runs each backend concurrently
        via ``asyncio.gather``, reducing wall-clock time.

        Example::

            cameras = await AsyncCameraManager.discover_async()
            mixed   = await AsyncCameraManager.discover_async(["Basler", "OpenCV"])
        """
        backends_to_search = cls._resolve_backends(backends, include_mocks)

        # Build one async task per backend
        async def _discover_one(name: str) -> Tuple[str, Union[List[str], Dict[str, Dict[str, str]]]]:
            if name == "OpenCV":
                from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import OpenCVCameraBackend

                return name, await OpenCVCameraBackend.discover_async(include_details=details)
            if name == "MockBasler":
                mock_class = cls._get_mock_camera("basler")
                return name, await asyncio.to_thread(mock_class.get_available_cameras)
            # Basler / GenICam
            available, camera_class = cls._discover_backend(name.lower())
            if available and camera_class:
                return name, await camera_class.discover_async(include_details=details)
            return name, []

        tasks = [_discover_one(b) for b in backends_to_search]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_cameras: List[str] = []
        all_details: List[Dict[str, Any]] = []

        for result in results:
            if isinstance(result, Exception):
                try:
                    cls.logger.warning(f"Backend discovery failed: {result}")
                except Exception:
                    pass
                continue
            backend_name, cameras = result
            cls._format_discovery_result(
                backend_name,
                cameras,
                names_out=all_cameras,
                details_out=all_details,
                details=details,
            )

        return all_details if details else all_cameras

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

            # Auto-export config for state preservation on reconnect
            await self._auto_export_config(camera_name)

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

    @property
    def timeout_ms(self) -> int:
        """Get the current capture timeout in milliseconds.

        Returns:
            Current capture timeout in milliseconds
        """
        return self._timeout_ms

    @timeout_ms.setter
    def timeout_ms(self, timeout: int) -> None:
        """Set the capture timeout for future camera opens and update active cameras.

        Args:
            timeout: Timeout in milliseconds

        Raises:
            ValueError: If timeout is less than 100
        """
        if timeout < 100:
            raise ValueError("timeout_ms must be at least 100")
        self._timeout_ms = timeout
        # Update all active cameras
        for camera_name, camera in self._cameras.items():
            if hasattr(camera, "_backend") and hasattr(camera._backend, "timeout_ms"):
                camera._backend.timeout_ms = timeout
                if hasattr(camera._backend, "_op_timeout_s"):
                    camera._backend._op_timeout_s = max(1.0, float(timeout) / 1000.0)
        self.logger.info(f"Capture timeout set to {timeout}ms")

    @property
    def retrieve_retry_count(self) -> int:
        """Get the current retrieve retry count.

        Returns:
            Current number of capture retry attempts
        """
        return self._retrieve_retry_count

    @retrieve_retry_count.setter
    def retrieve_retry_count(self, count: int) -> None:
        """Set the retrieve retry count for future camera opens and update active cameras.

        Args:
            count: Number of retry attempts

        Raises:
            ValueError: If count is less than 1
        """
        if count < 1:
            raise ValueError("retrieve_retry_count must be at least 1")
        self._retrieve_retry_count = count
        # Update all active cameras
        for camera_name, camera in self._cameras.items():
            if hasattr(camera, "_backend") and hasattr(camera._backend, "retrieve_retry_count"):
                camera._backend.retrieve_retry_count = count
        self.logger.info(f"Retrieve retry count set to {count}")

    def diagnostics(self) -> Dict[str, Any]:
        """Get diagnostics information including bandwidth management and resilience status."""
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
            "failure_counts": dict(self._failure_counts),
            "cameras_in_cooldown": [
                name
                for name, ts in self._last_reinit_attempt.items()
                if time.time() - ts < self._reinitialization_cooldown
            ],
            "capture_groups_count": len(self._capture_groups),
        }

    # ------------------------------------------------------------------ #
    #  Capture Groups (stage+set batching)                                #
    # ------------------------------------------------------------------ #

    def configure_capture_groups(self, config: StageSetConfigDict) -> None:
        """Configure stage+set capture groups with per-group semaphores.

        Each group creates a concurrency semaphore sized to ``batch_size``,
        limiting how many cameras within the group can capture simultaneously.

        Args:
            config: ``{stage: {set: {"batch_size": int, "cameras": [str]}}}``

        Raises:
            CameraConfigurationError: If config is invalid.
        """
        is_valid, error = validate_stage_set_configs(config, self.active_cameras)
        if not is_valid:
            raise CameraConfigurationError(f"Invalid capture group config: {error}")

        groups, camera_map = build_capture_groups(config)
        self._capture_groups = groups
        self._camera_group_keys = camera_map
        self.logger.info(
            f"Configured {len(groups)} capture groups for {len(camera_map)} cameras"
        )

    def remove_capture_groups(self) -> None:
        """Clear all capture group configurations."""
        count = len(self._capture_groups)
        self._capture_groups.clear()
        self._camera_group_keys.clear()
        self.logger.info(f"Removed {count} capture groups")

    def get_capture_groups(self) -> Dict[str, Any]:
        """Return current capture group configuration as serializable dict."""
        return {key: group.to_dict() for key, group in self._capture_groups.items()}

    # ------------------------------------------------------------------ #
    #  Auto-Reconnection / Failure Tracking                               #
    # ------------------------------------------------------------------ #

    def _get_camera_config_path(self, camera_name: str) -> str:
        """Return filesystem path for a camera's preserved config."""
        safe_name = camera_name.replace(":", "_").replace("/", "_")
        return str(Path(self._camera_config_dir) / f"{safe_name}.json")

    async def _auto_export_config(self, camera_name: str) -> None:
        """Export camera config after successful init for later restoration."""
        try:
            if camera_name not in self._cameras:
                return
            camera = self._cameras[camera_name]
            config_path = self._get_camera_config_path(camera_name)
            Path(config_path).parent.mkdir(parents=True, exist_ok=True)
            await camera.save_config(config_path)
            self.logger.debug(f"Auto-exported config for '{camera_name}' to {config_path}")
        except Exception as e:
            self.logger.warning(f"Failed to auto-export config for '{camera_name}': {e}")

    async def _auto_import_config(self, camera_name: str) -> None:
        """Restore camera config from previously saved file."""
        try:
            config_path = self._get_camera_config_path(camera_name)
            if not Path(config_path).exists():
                self.logger.debug(f"No saved config for '{camera_name}'")
                return
            if camera_name not in self._cameras:
                return
            camera = self._cameras[camera_name]
            await camera.load_config(config_path)
            self.logger.info(f"Auto-imported config for '{camera_name}' from {config_path}")
        except Exception as e:
            self.logger.warning(f"Failed to auto-import config for '{camera_name}': {e}")

    async def _handle_camera_failure(self, camera_name: str) -> None:
        """Handle consecutive failures: cooldown check, close, reinit, restore config."""
        current_time = time.time()

        # Cooldown check — avoid thrashing
        last_attempt = self._last_reinit_attempt.get(camera_name, 0.0)
        if current_time - last_attempt < self._reinitialization_cooldown:
            remaining = self._reinitialization_cooldown - (current_time - last_attempt)
            self.logger.info(
                f"Reinit cooldown for '{camera_name}', {remaining:.1f}s remaining"
            )
            return

        self.logger.warning(
            f"Failure threshold reached for '{camera_name}' "
            f"({self._failure_counts.get(camera_name, 0)} consecutive failures), "
            f"attempting reinit"
        )
        self._last_reinit_attempt[camera_name] = current_time

        # Close the camera
        try:
            await self.close(camera_name)
        except Exception as e:
            self.logger.warning(f"Error closing '{camera_name}' during reinit: {e}")

        # Re-open and restore config
        try:
            await self.open(camera_name, test_connection=True)
            await self._auto_import_config(camera_name)
            # Re-export to keep the saved file fresh
            await self._auto_export_config(camera_name)
            self._failure_counts[camera_name] = 0
            self.logger.info(f"Reinit successful for '{camera_name}'")
        except Exception as e:
            self.logger.error(f"Reinit failed for '{camera_name}': {e}")
            # Reset counter to prevent immediate re-trigger on next capture
            self._failure_counts[camera_name] = 0

    def _record_capture_success(self, camera_name: str) -> None:
        """Reset failure counter on successful capture."""
        if self._failure_counts.get(camera_name, 0) > 0:
            self._failure_counts[camera_name] = 0

    async def _record_capture_failure(self, camera_name: str) -> None:
        """Increment failure counter and trigger reinit if threshold reached."""
        count = self._failure_counts.get(camera_name, 0) + 1
        self._failure_counts[camera_name] = count
        self.logger.warning(
            f"Capture failure #{count} for '{camera_name}' "
            f"(threshold: {self._max_consecutive_failures})"
        )
        if count >= self._max_consecutive_failures:
            await self._handle_camera_failure(camera_name)

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
                    # Clean up failure tracking (but preserve group assignments — they're config, not state)
                    self._failure_counts.pop(camera_name, None)
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
                await camera.configure(**settings)
                return camera_name, True
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
        self,
        camera_names: List[str],
        save_path_pattern: Optional[str] = None,
        output_format: str = "pil",
        stage: Optional[str] = None,
        set_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Capture from multiple cameras with network bandwidth management.

        Args:
            camera_names: List of camera names to capture from
            save_path_pattern: Optional path pattern for saving images. Use {camera} placeholder for camera name
            output_format: Output format for images
            stage: Optional stage name for capture group routing
            set_name: Optional set name for capture group routing

        Returns:
            Dictionary mapping camera names to captured images or file paths
        """
        results = {}

        async def capture_from_camera(camera_name: str) -> Tuple[str, Any]:
            try:
                # Route to correct semaphore (group-specific or global)
                semaphore, err = get_semaphore_for_capture(
                    camera_name,
                    stage,
                    set_name,
                    self._capture_groups,
                    self._camera_group_keys,
                    self._capture_semaphore,
                )
                if err:
                    raise CameraConfigurationError(err)

                async with semaphore:
                    if camera_name not in self._cameras:
                        raise KeyError(f"Camera '{camera_name}' is not initialized. Use open() first.")
                    camera = self._cameras[camera_name]

                    # Generate save path for this camera if pattern provided
                    save_path = None
                    if save_path_pattern:
                        # Replace {camera} placeholder with camera name (sanitized for filesystem)
                        safe_camera_name = camera_name.replace(":", "_").replace("/", "_")
                        save_path = save_path_pattern.replace("{camera}", safe_camera_name)

                    image = await camera.capture(save_path=save_path, output_format=output_format)

                    # Track success for auto-reconnection
                    self._record_capture_success(camera_name)

                    # When save_path_pattern is provided, return the file path instead of image data
                    if save_path_pattern and save_path:
                        return camera_name, save_path
                    else:
                        return camera_name, image
            except Exception as e:
                self.logger.error(f"Capture failed for '{camera_name}': {e}")
                # Track failure for auto-reconnection
                await self._record_capture_failure(camera_name)
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
        output_format: str = "pil",
        stage: Optional[str] = None,
        set_name: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Capture HDR images from multiple cameras simultaneously."""
        results = {}

        async def capture_hdr_from_camera(camera_name: str) -> Tuple[str, Dict[str, Any]]:
            try:
                # Route to correct semaphore (group-specific or global)
                semaphore, err = get_semaphore_for_capture(
                    camera_name,
                    stage,
                    set_name,
                    self._capture_groups,
                    self._camera_group_keys,
                    self._capture_semaphore,
                )
                if err:
                    raise CameraConfigurationError(err)

                async with semaphore:
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
                        output_format=output_format,
                    )

                    self._record_capture_success(camera_name)
                    return camera_name, result
            except Exception as e:
                self.logger.error(f"HDR capture failed for '{camera_name}': {e}")
                await self._record_capture_failure(camera_name)
                return camera_name, {
                    "success": False,
                    "images": None,
                    "image_paths": None,
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
        for backend_name in ["Basler", "OpenCV", "GenICam"]:
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

        # Inject manager's performance settings if not explicitly provided
        if "timeout_ms" not in kwargs:
            kwargs["timeout_ms"] = self._timeout_ms
        if "retrieve_retry_count" not in kwargs:
            kwargs["retrieve_retry_count"] = self._retrieve_retry_count

        try:
            if backend in ["Basler", "OpenCV", "GenICam"]:
                available, camera_class = self._discover_backend(backend.lower())
                if not available or not camera_class:
                    self.logger.error(f"Requested backend '{backend}' is not available or has no class")
                    raise CameraNotFoundError(f"Backend '{backend}' not available")
                self.logger.debug(
                    f"Creating camera instance for {backend}:{device_name} with timeout={kwargs['timeout_ms']}ms, retry={kwargs['retrieve_retry_count']}"
                )
                return camera_class(device_name, **kwargs)

            elif backend.startswith("Mock"):
                backend_name = backend.replace("Mock", "").lower()
                self.logger.debug(
                    f"Creating mock camera instance for {backend}:{device_name} with timeout={kwargs['timeout_ms']}ms, retry={kwargs['retrieve_retry_count']}"
                )
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

            elif cache_key == "genicam":
                from mindtrace.hardware.cameras.backends.genicam import GENICAM_AVAILABLE, GenICamCameraBackend

                cache["available"] = GENICAM_AVAILABLE
                cache["class"] = GenICamCameraBackend if GENICAM_AVAILABLE else None

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
