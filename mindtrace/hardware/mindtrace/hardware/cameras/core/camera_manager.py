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

    def _submit_coro(self, coro):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    # ===== Public sync API (delegating) =====
    def get_available_backends(self) -> List[str]:
        return self._manager.get_available_backends()

    def get_backend_info(self) -> Dict[str, Dict[str, Any]]:
        return self._manager.get_backend_info()

    def discover_cameras(self, backends: Optional[Union[str, List[str]]] = None) -> List[str]:
        return self._manager.discover_cameras(backends=backends)

    def initialize_camera(self, camera_name: str, test_connection: bool = True, **kwargs) -> None:
        return self._submit_coro(self._manager.initialize_camera(camera_name, test_connection=test_connection, **kwargs))

    def initialize_cameras(self, camera_names: List[str], test_connections: bool = True, **kwargs) -> List[str]:
        return self._submit_coro(
            self._manager.initialize_cameras(camera_names, test_connections=test_connections, **kwargs)
        )

    def get_camera(self, camera_name: str) -> Camera:
        async_cam: AsyncCamera = self._manager.get_camera(camera_name)
        # Wrap with sync facade bound to this manager's loop
        return Camera(async_cam, self._loop)

    def get_cameras(self, camera_names: List[str]) -> Dict[str, Camera]:
        async_map = self._manager.get_cameras(camera_names)
        return {name: Camera(async_cam, self._loop) for name, async_cam in async_map.items()}

    def get_active_cameras(self) -> List[str]:
        return self._manager.get_active_cameras()

    def get_max_concurrent_captures(self) -> int:
        return self._manager.get_max_concurrent_captures()

    def set_max_concurrent_captures(self, max_captures: int) -> None:
        return self._manager.set_max_concurrent_captures(max_captures)

    def get_network_bandwidth_info(self) -> Dict[str, Any]:
        return self._manager.get_network_bandwidth_info()

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
            return mgr.discover_cameras(backends=backends)
        finally:
            try:
                mgr.shutdown()
            except Exception:
                pass

    @classmethod
    def initialize_and_get_camera(cls, camera_name: str, **kwargs) -> "Camera":
        mgr = cls()
        try:
            mgr.initialize_camera(camera_name, **kwargs)
            return mgr.get_camera(camera_name)
        finally:
            try:
                mgr.shutdown()
            except Exception:
                pass

    # ===== Lifecycle =====
    def shutdown(self):
        try:
            self.close_all_cameras()
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)
        self.logger.info("CameraManager (sync) shutdown complete")

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass 
