"""Unit tests for mindtrace.core.utils.async_runner module."""

import asyncio
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.core import AsyncRunner
from mindtrace.core.utils import async_runner as async_runner_module


class TestAsyncRunnerClassMethods:
    """Test suite for AsyncRunner class-level (shared loop) methods."""

    def test_is_async_context_from_sync(self):
        """Test is_async_context returns False from sync context."""
        assert AsyncRunner.is_async_context() is False

    @pytest.mark.asyncio
    async def test_is_async_context_from_async(self):
        """Test is_async_context returns True from async context."""
        assert AsyncRunner.is_async_context() is True

    def test_run_async_simple_coroutine(self):
        """Test run_async executes a simple coroutine from sync context."""

        async def simple_coro():
            return 42

        result = AsyncRunner.run_async(simple_coro())
        assert result == 42

    def test_run_async_coroutine_with_args(self):
        """Test run_async works with coroutines that take arguments."""

        async def add(a, b):
            await asyncio.sleep(0.01)
            return a + b

        result = AsyncRunner.run_async(add(3, 4))
        assert result == 7

    def test_run_async_coroutine_with_await(self):
        """Test run_async works with coroutines that await other coroutines."""

        async def inner():
            await asyncio.sleep(0.01)
            return "inner"

        async def outer():
            result = await inner()
            return f"outer-{result}"

        result = AsyncRunner.run_async(outer())
        assert result == "outer-inner"

    def test_run_async_with_timeout_success(self):
        """Test run_async with timeout that doesn't expire."""

        async def fast_coro():
            await asyncio.sleep(0.01)
            return "done"

        result = AsyncRunner.run_async(fast_coro(), timeout=5.0)
        assert result == "done"

    def test_run_async_with_timeout_exceeded(self):
        """Test run_async raises TimeoutError when timeout is exceeded."""

        async def slow_coro():
            await asyncio.sleep(10)
            return "done"

        with pytest.raises(FuturesTimeoutError):
            AsyncRunner.run_async(slow_coro(), timeout=0.1)

    def test_run_async_propagates_exceptions(self):
        """Test run_async propagates exceptions from the coroutine."""

        async def failing_coro():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            AsyncRunner.run_async(failing_coro())

    def test_run_async_multiple_calls(self):
        """Test run_async can be called multiple times (shared loop reuse)."""

        async def coro(x):
            return x * 2

        results = [AsyncRunner.run_async(coro(i)) for i in range(5)]
        assert results == [0, 2, 4, 6, 8]

    @pytest.mark.asyncio
    async def test_run_sync_simple_function(self):
        """Test run_sync executes a simple sync function from async context."""

        def sync_func():
            return 42

        result = await AsyncRunner.run_sync(sync_func)
        assert result == 42

    @pytest.mark.asyncio
    async def test_run_sync_with_args(self):
        """Test run_sync works with functions that take arguments."""

        def add(a, b):
            return a + b

        result = await AsyncRunner.run_sync(add, 3, 4)
        assert result == 7

    @pytest.mark.asyncio
    async def test_run_sync_with_kwargs(self):
        """Test run_sync works with keyword arguments."""

        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}!"

        result = await AsyncRunner.run_sync(greet, "World", greeting="Hi")
        assert result == "Hi, World!"

    @pytest.mark.asyncio
    async def test_run_sync_blocking_function(self):
        """Test run_sync properly offloads blocking work."""

        def blocking_func():
            time.sleep(0.1)
            return "done"

        start = time.perf_counter()
        result = await AsyncRunner.run_sync(blocking_func)
        elapsed = time.perf_counter() - start

        assert result == "done"
        assert elapsed >= 0.1

    @pytest.mark.asyncio
    async def test_run_sync_propagates_exceptions(self):
        """Test run_sync propagates exceptions from the function."""

        def failing_func():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await AsyncRunner.run_sync(failing_func)

    @pytest.mark.asyncio
    async def test_run_sync_concurrent_calls(self):
        """Test run_sync can handle concurrent calls."""

        def slow_func(x):
            time.sleep(0.1)
            return x * 2

        start = time.perf_counter()
        results = await asyncio.gather(
            AsyncRunner.run_sync(slow_func, 1),
            AsyncRunner.run_sync(slow_func, 2),
            AsyncRunner.run_sync(slow_func, 3),
        )
        elapsed = time.perf_counter() - start

        assert results == [2, 4, 6]
        # Should run in parallel, so total time should be ~0.1s, not ~0.3s
        assert elapsed < 0.25


class TestAsyncRunnerInstance:
    """Test suite for AsyncRunner instance-level (dedicated loop) methods."""

    def test_instance_run_simple_coroutine(self):
        """Test instance run method executes a coroutine."""
        with AsyncRunner() as runner:

            async def simple_coro():
                return 42

            result = runner.run(simple_coro())
            assert result == 42

    def test_instance_run_with_timeout_success(self):
        """Test instance run with timeout that doesn't expire."""
        with AsyncRunner() as runner:

            async def fast_coro():
                await asyncio.sleep(0.01)
                return "done"

            result = runner.run(fast_coro(), timeout=5.0)
            assert result == "done"

    def test_instance_run_with_timeout_exceeded(self):
        """Test instance run raises TimeoutError when timeout is exceeded."""
        with AsyncRunner() as runner:

            async def slow_coro():
                await asyncio.sleep(10)
                return "done"

            with pytest.raises(FuturesTimeoutError):
                runner.run(slow_coro(), timeout=0.1)

    def test_instance_run_propagates_exceptions(self):
        """Test instance run propagates exceptions from the coroutine."""
        with AsyncRunner() as runner:

            async def failing_coro():
                raise ValueError("test error")

            with pytest.raises(ValueError, match="test error"):
                runner.run(failing_coro())

    def test_instance_run_after_close_raises(self):
        """Test instance run raises RuntimeError after close."""
        runner = AsyncRunner()
        runner.close()

        async def simple_coro():
            return 42

        coro = simple_coro()
        try:
            with pytest.raises(RuntimeError, match="has been closed"):
                runner.run(coro)
        finally:
            coro.close()  # Clean up unawaited coroutine

    def test_instance_call_sync(self):
        """Test instance call_sync executes a sync function in the loop thread."""
        with AsyncRunner() as runner:

            def sync_func(x):
                return x * 2

            result = runner.call_sync(sync_func, 21)
            assert result == 42

    def test_instance_call_sync_propagates_exceptions(self):
        """Test instance call_sync propagates exceptions."""
        with AsyncRunner() as runner:

            def failing_func():
                raise ValueError("test error")

            with pytest.raises(ValueError, match="test error"):
                runner.call_sync(failing_func)

    def test_instance_call_sync_after_close_raises(self):
        """Test instance call_sync raises RuntimeError after close."""
        runner = AsyncRunner()
        runner.close()

        def sync_func():
            return 42

        with pytest.raises(RuntimeError, match="has been closed"):
            runner.call_sync(sync_func)

    def test_instance_context_manager(self):
        """Test instance works as context manager and cleans up properly."""
        with AsyncRunner() as runner:

            async def simple_coro():
                return 42

            result = runner.run(simple_coro())
            assert result == 42
            assert not runner._closed

        # After exiting context, runner should be closed
        assert runner._closed

    def test_instance_close_is_idempotent(self):
        """Test calling close multiple times is safe."""
        runner = AsyncRunner()
        runner.close()
        runner.close()  # Should not raise
        assert runner._closed

    def test_multiple_instances_are_independent(self):
        """Test multiple instances have independent loops."""
        results = []

        async def coro(x):
            await asyncio.sleep(0.01)
            return x

        with AsyncRunner() as runner1:
            with AsyncRunner() as runner2:
                results.append(runner1.run(coro(1)))
                results.append(runner2.run(coro(2)))

        assert results == [1, 2]

    def test_instance_with_existing_loop(self):
        """Test instance can use an existing loop."""
        import threading

        # Create a loop in another thread
        external_loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(
            target=lambda: (asyncio.set_event_loop(external_loop), external_loop.run_forever()),
            daemon=True,
        )
        loop_thread.start()

        # Give the loop time to start
        import time

        time.sleep(0.1)

        try:
            # Create runner with the existing loop
            runner = AsyncRunner(loop=external_loop)
            assert runner._loop is external_loop
            assert not runner._owns_loop
            assert runner._thread is None

            async def simple_coro():
                return 42

            result = runner.run(simple_coro())
            assert result == 42

            # Close should not stop the loop (we don't own it)
            runner.close()
            assert external_loop.is_running()

        finally:
            # Clean up
            external_loop.call_soon_threadsafe(external_loop.stop)
            loop_thread.join(timeout=1.0)


class TestAsyncRunnerShutdown:
    """Test suite for AsyncRunner shutdown functionality."""

    def test_shutdown_class_method(self):
        """Test shutdown class method can be called without error."""

        # First make sure the shared loop is started
        async def simple_coro():
            return 42

        AsyncRunner.run_async(simple_coro())

        # Now shutdown
        AsyncRunner.shutdown()

        # Loop should be recreated on next run_async call
        result = AsyncRunner.run_async(simple_coro())
        assert result == 42


class TestAsyncRunnerThreadSafety:
    """Test suite for AsyncRunner thread safety."""

    def test_run_async_from_multiple_threads(self):
        """Test run_async can be called from multiple threads concurrently."""
        import threading

        results = []
        errors = []

        async def coro(x):
            await asyncio.sleep(0.01)
            return x * 2

        def thread_func(value):
            try:
                result = AsyncRunner.run_async(coro(value))
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=thread_func, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert sorted(results) == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]


class TestAsyncRunnerEdgeCases:
    """Test suite for AsyncRunner edge cases and exception handling."""

    def test_instance_run_scheduling_failure(self):
        """Test instance run handles scheduling failure gracefully."""
        runner = AsyncRunner()

        async def simple_coro():
            return 42

        coro = simple_coro()

        # Mock run_coroutine_threadsafe to fail
        with patch("asyncio.run_coroutine_threadsafe", side_effect=RuntimeError("Scheduling failed")):
            with pytest.raises(RuntimeError, match="Scheduling failed"):
                runner.run(coro)

        runner.close()

    def test_run_async_scheduling_failure(self):
        """Test run_async handles scheduling failure gracefully."""

        async def simple_coro():
            return 42

        coro = simple_coro()

        # Mock run_coroutine_threadsafe to fail
        with patch("asyncio.run_coroutine_threadsafe", side_effect=RuntimeError("Scheduling failed")):
            with pytest.raises(RuntimeError, match="Scheduling failed"):
                AsyncRunner.run_async(coro)

    def test_instance_close_handles_exceptions(self):
        """Test instance close handles exceptions during cleanup."""
        runner = AsyncRunner()

        # Mock to raise exception during stop
        runner._loop.call_soon_threadsafe = MagicMock(side_effect=RuntimeError("Stop failed"))

        # Should not raise, just silently handle
        runner.close()
        assert runner._closed

    def test_instance_close_handles_join_exception(self):
        """Test instance close handles thread join exception."""
        runner = AsyncRunner()

        # Mock thread join to raise
        runner._thread.join = MagicMock(side_effect=RuntimeError("Join failed"))

        # Should not raise, just silently handle
        runner.close()
        assert runner._closed

    def test_instance_del_handles_exceptions(self):
        """Test instance __del__ handles exceptions gracefully."""
        runner = AsyncRunner()

        # Mock close to raise
        runner.close = MagicMock(side_effect=RuntimeError("Close failed"))

        # __del__ should not raise
        runner.__del__()

    def test_shared_loop_double_check_path(self):
        """Test the double-check locking path in _get_shared_loop."""
        # Reset shared loop state to test initialization
        original_loop = async_runner_module._shared_loop
        original_thread = async_runner_module._shared_thread

        try:
            async_runner_module._shared_loop = None
            async_runner_module._shared_thread = None

            # First call initializes the loop
            loop1 = async_runner_module._get_shared_loop()
            assert loop1 is not None
            assert loop1.is_running()

            # Second call returns the same loop (fast path)
            loop2 = async_runner_module._get_shared_loop()
            assert loop2 is loop1

        finally:
            # Cleanup - stop the loop we created
            if async_runner_module._shared_loop is not None and async_runner_module._shared_loop is not original_loop:
                try:
                    async_runner_module._shared_loop.call_soon_threadsafe(async_runner_module._shared_loop.stop)
                    if async_runner_module._shared_thread is not None:
                        async_runner_module._shared_thread.join(timeout=1.0)
                except Exception:
                    pass

            # Restore original state
            async_runner_module._shared_loop = original_loop
            async_runner_module._shared_thread = original_thread

    def test_shutdown_shared_loop_handles_exceptions(self):
        """Test _shutdown_shared_loop handles exceptions gracefully."""
        # Save original state
        original_loop = async_runner_module._shared_loop
        original_thread = async_runner_module._shared_thread

        try:
            # Create a mock loop that raises on call_soon_threadsafe
            mock_loop = MagicMock()
            mock_loop.call_soon_threadsafe.side_effect = RuntimeError("Stop failed")

            mock_thread = MagicMock()
            mock_thread.join.side_effect = RuntimeError("Join failed")

            async_runner_module._shared_loop = mock_loop
            async_runner_module._shared_thread = mock_thread

            # Should not raise
            async_runner_module._shutdown_shared_loop()

        finally:
            # Restore original state
            async_runner_module._shared_loop = original_loop
            async_runner_module._shared_thread = original_thread

    def test_shutdown_with_none_loop(self):
        """Test _shutdown_shared_loop handles None loop gracefully."""
        # Save original state
        original_loop = async_runner_module._shared_loop
        original_thread = async_runner_module._shared_thread

        try:
            async_runner_module._shared_loop = None
            async_runner_module._shared_thread = None

            # Should not raise
            async_runner_module._shutdown_shared_loop()

        finally:
            # Restore original state
            async_runner_module._shared_loop = original_loop
            async_runner_module._shared_thread = original_thread

    def test_instance_run_cancel_exception_on_timeout(self):
        """Test instance run handles exception during future cancellation."""
        runner = AsyncRunner()

        async def slow_coro():
            await asyncio.sleep(10)
            return "done"

        # Create a mock future that raises on cancel
        mock_future = MagicMock()
        mock_future.result.side_effect = FuturesTimeoutError("Timeout")
        mock_future.cancel.side_effect = RuntimeError("Cancel failed")

        coro = slow_coro()
        try:
            with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
                with pytest.raises(FuturesTimeoutError):
                    runner.run(coro, timeout=0.1)
        finally:
            coro.close()
            runner.close()

    def test_run_async_cancel_exception_on_timeout(self):
        """Test run_async handles exception during future cancellation."""

        async def slow_coro():
            await asyncio.sleep(10)
            return "done"

        # Create a mock future that raises on cancel
        mock_future = MagicMock()
        mock_future.result.side_effect = FuturesTimeoutError("Timeout")
        mock_future.cancel.side_effect = RuntimeError("Cancel failed")

        coro = slow_coro()
        try:
            with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
                with pytest.raises(FuturesTimeoutError):
                    AsyncRunner.run_async(coro, timeout=0.1)
        finally:
            coro.close()

    def test_shared_loop_double_check_race_condition(self):
        """Test the double-check path when loop exists but isn't running yet."""
        import threading

        original_loop = async_runner_module._shared_loop
        original_thread = async_runner_module._shared_thread

        try:
            # Reset state
            async_runner_module._shared_loop = None
            async_runner_module._shared_thread = None

            results = []
            errors = []

            def get_loop():
                try:
                    loop = async_runner_module._get_shared_loop()
                    results.append(loop)
                except Exception as e:
                    errors.append(e)

            # Start multiple threads that all try to get the loop simultaneously
            threads = [threading.Thread(target=get_loop) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0
            # All threads should get the same loop
            assert len(set(id(r) for r in results)) == 1

        finally:
            # Cleanup
            if async_runner_module._shared_loop is not None and async_runner_module._shared_loop is not original_loop:
                try:
                    async_runner_module._shared_loop.call_soon_threadsafe(async_runner_module._shared_loop.stop)
                    if async_runner_module._shared_thread is not None:
                        async_runner_module._shared_thread.join(timeout=1.0)
                except Exception:
                    pass

            async_runner_module._shared_loop = original_loop
            async_runner_module._shared_thread = original_thread
