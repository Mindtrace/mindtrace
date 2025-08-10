"""Synchronous Camera Manager facade for Mindtrace hardware cameras.

This class provides a synchronous API that delegates to `AsyncCameraManager`
running on a dedicated background event loop thread.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Dict, List, Optional, Tuple, Union

from mindtrace.core.base.mindtrace_base import Mindtrace
from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager
from mindtrace.hardware.cameras.core.async_camera import AsyncCamera
from mindtrace.hardware.cameras.core.camera import Camera


class CameraManager(Mindtrace):
    """Synchronous facade over `AsyncCameraManager`.

    Notes:
        - Starts a private event loop in a background thread on initialization.
        - All public methods are blocking and submit their async counterparts to the loop.
        - Use `close_all_cameras()` or `shutdown()` to stop the background loop and release resources.
    """

    def __init__(self, include_mocks: bool = False, max_concurrent_captures: int | None = None, **kwargs):
        super().__init__(**kwargs)
        self._shutting_down = False
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._manager = self._call_in_loop(
            AsyncCameraManager, include_mocks=include_mocks, max_concurrent_captures=max_concurrent_captures
        )
        self.logger.info("CameraManager (sync) initialized with background event loop")

    # ===== Loop helpers =====
    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _call_in_loop(self, ctor_or_coro, *args, **kwargs):
        """Run constructor or coroutine in the background loop and return result synchronously."""
        if asyncio.iscoroutinefunction(ctor_or_coro):
            coro = ctor_or_coro(*args, **kwargs)
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return fut.result()
        else:
            # Construct object inside loop thread to bind its tasks to that loop
            result_future: Future = Future()

            def _create():
                try:
                    obj = ctor_or_coro(*args, **kwargs)
                    result_future.set_result(obj)
                except Exception as e:
                    result_future.set_exception(e)

            self._loop.call_soon_threadsafe(_create)
            return result_future.result()

    def _submit_coro(self, coro, timeout: float | None = None):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return fut.result(timeout=timeout)
        except Exception:
            # Best-effort cancellation on timeout or other failures
            try:
                fut.cancel()
            except Exception:
                pass
            raise

    # ===== Public sync API (delegating) =====
    def get_available_backends(self) -> List[str]:
        return self._call_in_loop(self._manager.get_available_backends)

    def get_backend_info(self) -> Dict[str, Dict[str, Any]]:
        return self._call_in_loop(self._manager.get_backend_info)

    def discover(self, backends: Optional[Union[str, List[str]]] = None, details: bool = False):
        return self._call_in_loop(self._manager.discover, backends=backends, details=details)

    def open(self, names: Optional[Union[str, List[str]]] = None, test_connection: bool = True, **kwargs) -> Union["Camera", Dict[str, "Camera"]]:
        """Open one or more cameras.

        Args:
            names: Camera name (e.g., "Backend:device") or a list of names. If None, opens the first available camera 
                (prefers OpenCV).
            test_connection: If True, perform a lightweight connection test after opening.
            **kwargs: Optional backend-specific configuration to apply during open.

        Returns:
            If a single name or None is provided, returns a `Camera`.
            If a list of names is provided, returns a `Dict[str, Camera]` mapping each name to a `Camera`.

        Raises:
            CameraNotFoundError: If no cameras are available when names is None.
            CameraInitializationError: If opening the camera fails.
            CameraConnectionError: If the connection test fails when test_connection is True.
            ValueError: If a provided camera name is already open (depending on backend policy) or invalid.

        Notes:
            - This method is idempotent for single-name calls; if the camera is already open, the existing instance is returned.
        """
        result = self._submit_coro(self._manager.open(names, test_connection=test_connection, **kwargs))
        if isinstance(result, AsyncCamera):
            return Camera(result, self._loop)
        # assume dict[str, AsyncCamera]
        return {name: Camera(async_cam, self._loop) for name, async_cam in result.items()}

    def get_camera(self, camera_name: str) -> Camera:
        async_cam: AsyncCamera = self._call_in_loop(self._manager.get_camera, camera_name)
        # Wrap with sync facade bound to this manager's loop
        return Camera(async_cam, self._loop)

    def get_cameras(self, camera_names: List[str]) -> Dict[str, Camera]:
        async_map = self._call_in_loop(self._manager.get_cameras, camera_names)
        return {name: Camera(async_cam, self._loop) for name, async_cam in async_map.items()}

    @property
    def active_cameras(self) -> List[str]:
        return self._manager.active_cameras

    @property
    def max_concurrent_captures(self) -> int:
        return self._manager.max_concurrent_captures

    @max_concurrent_captures.setter
    def max_concurrent_captures(self, max_captures: int) -> None:
        self._manager.max_concurrent_captures = max_captures

    def diagnostics(self) -> Dict[str, Any]:
        return self._manager.diagnostics()

    def close_camera(self, camera_name: str) -> None:
        return self._submit_coro(self._manager.close_camera(camera_name))

    def close_all_cameras(self) -> None:
        return self._submit_coro(self._manager.close_all_cameras())

    # Convenience/class methods
    @classmethod
    def discover_all_cameras(
        cls,
        include_mocks: bool = False,
        max_concurrent_captures: int = 2,
        backends: Optional[Union[str, List[str]]] = None,
    ) -> List[str]:
        mgr = cls(include_mocks=include_mocks, max_concurrent_captures=max_concurrent_captures)
        try:
            return mgr.discover(backends=backends)
        finally:
            try:
                mgr.close()
            except Exception:
                pass

    @classmethod
    def initialize_and_get_camera(cls, camera_name: str, **kwargs) -> "Camera":
        mgr = cls()
        try:
            mgr.open(camera_name, **kwargs)
            return mgr.get_camera(camera_name)
        finally:
            try:
                mgr.close()
            except Exception:
                pass

    # ===== Lifecycle =====
    def close(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            try:
                # Bound shutdown time; if closing cameras stalls, continue stopping loop
                self._submit_coro(self._manager.close_all_cameras(), timeout=1.0)
            except Exception:
                pass
            try:
                if self._loop.is_running():
                    self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass
            try:
                self._thread.join(timeout=1.5)
            except Exception:
                pass
        finally:
            self.logger.info("CameraManager (sync) shutdown complete")

    def __del__(self):
        # Avoid blocking in destructor; perform best-effort stop
        try:
            if hasattr(self, "_loop") and isinstance(getattr(self, "_loop"), asyncio.AbstractEventLoop):
                try:
                    if self._loop.is_running():
                        self._loop.call_soon_threadsafe(self._loop.stop)
                except Exception:
                    pass
            if hasattr(self, "_thread") and getattr(self, "_thread") is not None:
                try:
                    self._thread.join(timeout=0.2)
                except Exception:
                    pass
        except Exception:
            pass 
