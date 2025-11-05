"""Synchronous Camera Manager facade for Mindtrace hardware cameras.

This class provides a synchronous API that delegates to `AsyncCameraManager` running on a dedicated background event
loop thread.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Dict, List, Optional, Union

from mindtrace.core import Mindtrace
from mindtrace.hardware.cameras.core.async_camera import AsyncCamera
from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager
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

    # ===== Public sync API (delegating) =====
    def backends(self) -> List[str]:
        return self._call_in_loop(self._manager.backends)

    def backend_info(self) -> Dict[str, Dict[str, Any]]:
        return self._call_in_loop(self._manager.backend_info)

    @classmethod
    def discover(
        cls,
        backends: Optional[Union[str, List[str]]] = None,
        details: bool = False,
        include_mocks: bool = False,
    ):
        return AsyncCameraManager.discover(backends=backends, details=details, include_mocks=include_mocks)

    def open(
        self, names: Optional[Union[str, List[str]]] = None, test_connection: bool = True, **kwargs
    ) -> Union["Camera", Dict[str, "Camera"]]:
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

    def batch_configure(self, configurations: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """Configure multiple cameras simultaneously."""
        return self._submit_coro(self._manager.batch_configure(configurations))

    def batch_capture(
        self, camera_names: List[str], upload_to_gcs: bool = False, output_format: str = "numpy"
    ) -> Dict[str, Any]:
        """Capture from multiple cameras with network bandwidth management."""
        return self._submit_coro(
            self._manager.batch_capture(camera_names, upload_to_gcs=upload_to_gcs, output_format=output_format)
        )

    def batch_capture_hdr(
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
        return self._submit_coro(
            self._manager.batch_capture_hdr(
                camera_names=camera_names,
                save_path_pattern=save_path_pattern,
                exposure_levels=exposure_levels,
                exposure_multiplier=exposure_multiplier,
                return_images=return_images,
                upload_to_gcs=upload_to_gcs,
                output_format=output_format,
            )
        )

    def close(self, names: Optional[Union[str, List[str]]] = None) -> None:
        """Close cameras or shut down the manager.

        Args:
            names: Camera name (e.g., "Backend:device") or a list of names. If None, closes all cameras and shuts down
                the background event loop thread.
        """
        # Close specific cameras
        if names is not None:
            self._submit_coro(self._manager.close(names))
            return

        # Shutdown path
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            try:
                # Bound shutdown time; if closing cameras stalls, continue stopping loop
                self._submit_coro(self._manager.close(None), timeout=1.0)
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
        try:
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            # If scheduling fails, close the coroutine to prevent warnings
            coro.close()
            raise
        try:
            return fut.result(timeout=timeout)
        except Exception:
            # Best-effort cancellation on timeout or other failures
            try:
                fut.cancel()
            except Exception:
                pass
            raise
