"""Async/Sync bridging utilities.

This module provides a single `AsyncRunner` class that handles all async/sync
interop with a minimal API:

- `AsyncRunner.run_async(coro)` - Run a coroutine from sync context
- `AsyncRunner.run_sync(func, *args)` - Run a sync function from async context

Example:
    ```python
    from mindtrace.core import AsyncRunner

    # Sync code calling async
    async def fetch_data():
        await asyncio.sleep(1)
        return "data"

    result = AsyncRunner.run_async(fetch_data())

    # Async code calling sync
    def blocking_io():
        time.sleep(1)
        return "done"

    async def main():
        result = await AsyncRunner.run_sync(blocking_io)
    ```
"""

from __future__ import annotations

import asyncio
import atexit
import threading
from concurrent.futures import Future
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")

# Module-level shared loop state
_shared_loop: asyncio.AbstractEventLoop | None = None
_shared_thread: threading.Thread | None = None
_shared_lock = threading.Lock()


def _get_shared_loop() -> asyncio.AbstractEventLoop:
    """Get or create the shared background event loop.

    This lazily initializes a daemon thread with its own event loop that persists
    for the lifetime of the interpreter. Thread-safe.
    """
    global _shared_loop, _shared_thread

    if _shared_loop is not None and _shared_loop.is_running():
        return _shared_loop

    with _shared_lock:
        # Double-check after acquiring lock
        if _shared_loop is not None and _shared_loop.is_running():
            return _shared_loop

        _shared_loop = asyncio.new_event_loop()

        def _run_loop():
            asyncio.set_event_loop(_shared_loop)
            _shared_loop.run_forever()

        _shared_thread = threading.Thread(target=_run_loop, name="AsyncRunner-SharedLoop", daemon=True)
        _shared_thread.start()

        return _shared_loop


def _shutdown_shared_loop():
    """Cleanup the shared loop on interpreter exit."""
    global _shared_loop, _shared_thread

    if _shared_loop is not None:
        try:
            _shared_loop.call_soon_threadsafe(_shared_loop.stop)
        except Exception:
            pass
        if _shared_thread is not None:
            try:
                _shared_thread.join(timeout=1.0)
            except Exception:
                pass


# Register cleanup on interpreter exit
atexit.register(_shutdown_shared_loop)


class AsyncRunner:
    """Unified async/sync bridging utility.

    Provides both class-level methods (using a shared background loop) and
    instance-level methods (using a dedicated loop) for async/sync interop.

    Class-level usage (recommended for most cases):
        ```python
        from mindtrace.core import AsyncRunner

        # Sync -> Async
        result = AsyncRunner.run_async(some_coroutine())

        # Async -> Sync
        result = await AsyncRunner.run_sync(blocking_function, arg1, arg2)
        ```

    Instance-level usage (for isolated loops):
        ```python
        with AsyncRunner() as runner:
            result = runner.run(some_coroutine())
        ```

    Attributes:
        Class-level:
            run_async: Run a coroutine from sync context using shared loop
            run_sync: Run a sync function from async context
            is_async_context: Check if currently in an async context
            shutdown: Explicitly shutdown the shared loop

        Instance-level:
            run: Run a coroutine on the instance's dedicated loop
            close: Shutdown the instance's dedicated loop
    """

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None):
        """Create an AsyncRunner instance.

        Args:
            loop: Optional existing event loop to use. If provided, the runner will
                use this loop (which must already be running in another thread).
                If None, creates a dedicated background loop.

        Use this when you need isolation from the shared loop, or when you want
        to integrate with an existing event loop.
        """
        self._owns_loop = loop is None
        self._closed = False

        if loop is not None:
            # Use the provided loop (must already be running)
            self._loop = loop
            self._thread = None
        else:
            # Create our own dedicated loop in a background thread
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._run_loop, name="runner-loop", daemon=True)
            self._thread.start()

    def _run_loop(self):
        """Run the event loop in the background thread."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    # ===== Instance methods (dedicated loop) =====

    def run(self, coro: Awaitable[T], timeout: float | None = None) -> T:
        """Run a coroutine on this instance's dedicated loop.

        Args:
            coro: The coroutine to run.
            timeout: Optional timeout in seconds.

        Returns:
            The result of the coroutine.

        Raises:
            RuntimeError: If the runner has been closed.
            TimeoutError: If the timeout is exceeded.
            Exception: Any exception raised by the coroutine.
        """
        if self._closed:
            raise RuntimeError("AsyncRunner has been closed")

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

    def call_sync(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute a synchronous function in the loop thread.

        Useful for thread-affine operations that must run in the same thread
        as the event loop.

        Args:
            func: The synchronous function to call.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            The result of the function.

        Raises:
            RuntimeError: If the runner has been closed.
            Exception: Any exception raised by the function.
        """
        if self._closed:
            raise RuntimeError("AsyncRunner has been closed")

        result_future: Future = Future()

        def _run():
            try:
                result_future.set_result(func(*args, **kwargs))
            except Exception as e:
                result_future.set_exception(e)

        self._loop.call_soon_threadsafe(_run)
        return result_future.result()

    def close(self):
        """Shutdown this instance's loop and thread (if we own them)."""
        if self._closed:
            return

        self._closed = True

        # Only cleanup if we created the loop ourselves
        if self._owns_loop:
            try:
                if self._loop.is_running():
                    self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass
            if self._thread is not None:
                try:
                    self._thread.join(timeout=1.0)
                except Exception:
                    pass

    def __enter__(self) -> "AsyncRunner":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # ===== Class methods (shared loop) =====

    @staticmethod
    def is_async_context() -> bool:
        """Check if currently running inside an async context.

        Returns:
            True if there's a running event loop, False otherwise.
        """
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False

    @staticmethod
    def run_async(coro: Awaitable[T], timeout: float | None = None) -> T:
        """Run a coroutine from synchronous context.

        Uses a shared background event loop that persists for the interpreter
        lifetime. Thread-safe and efficient for multiple calls.

        Note:
            This always uses a background loop (in a separate thread), even if
            there's a running loop in the current thread. This is intentional -
            blocking on the current thread's loop would cause a deadlock.

        Args:
            coro: The coroutine to run.
            timeout: Optional timeout in seconds.

        Returns:
            The result of the coroutine.

        Raises:
            TimeoutError: If the timeout is exceeded.
            Exception: Any exception raised by the coroutine.

        Example:
            ```python
            async def fetch_data(url):
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        return await resp.json()

            # Call from sync code
            data = AsyncRunner.run_async(fetch_data("https://api.example.com"))

            # With timeout
            data = AsyncRunner.run_async(fetch_data("https://api.example.com"), timeout=5.0)
            ```
        """
        # Always use the shared background loop (runs in a separate thread).
        # This works correctly whether or not there's a running loop in the current thread:
        # - No running loop: background loop handles it efficiently
        # - Running loop in THIS thread: we can't use it (would deadlock), so background loop is correct
        # - Running loop in ANOTHER thread: background loop is still safe and simple
        loop = _get_shared_loop()

        try:
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
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

    @staticmethod
    async def run_sync(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run a synchronous function from async context.

        Offloads the function to a thread pool to avoid blocking the event loop.

        Args:
            func: The synchronous function to call.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            The result of the function.

        Raises:
            Exception: Any exception raised by the function.

        Example:
            ```python
            def cpu_intensive_work(data):
                # Some blocking computation
                return process(data)

            async def main():
                result = await AsyncRunner.run_sync(cpu_intensive_work, my_data)
            ```
        """
        # asyncio.to_thread handles kwargs properly in Python 3.9+
        return await asyncio.to_thread(func, *args, **kwargs)

    @staticmethod
    def shutdown():
        """Explicitly shutdown the shared background loop.

        This is automatically called on interpreter exit, but can be called
        manually if needed for testing or explicit cleanup.

        Note:
            After calling this, the shared loop will be recreated on the next
            call to `run_async()`.
        """
        _shutdown_shared_loop()
