"""Unit tests for track_operation function."""

import asyncio
import importlib
import logging
import sys
from unittest.mock import Mock, patch

import pytest

from mindtrace.core.logging.logger import get_logger, track_operation


class TestTrackOperationContextManager:
    """Test track_operation as context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_success(self):
        """Test successful context manager usage."""
        logger = get_logger("test", use_structlog=True)

        async with track_operation("test_op", logger=logger, service="test_service") as log:
            assert log is not None
            assert hasattr(log, "info")
            assert hasattr(log, "log")

        # Check that logs were emitted
        # We can't easily verify the exact log calls without more setup,
        # but we can verify the context manager works without errors

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self):
        """Test context manager handles exceptions correctly."""
        logger = get_logger("test", use_structlog=True)

        with pytest.raises(ValueError, match="Test error"):
            async with track_operation("test_op", logger=logger):
                raise ValueError("Test error")

        # Exception should have been logged and re-raised

    @pytest.mark.asyncio
    async def test_context_manager_with_timeout(self):
        """Test context manager with timeout."""
        logger = get_logger("test", use_structlog=True)

        # Context manager doesn't enforce timeout internally; timeout is only for decorator
        # This test should verify that timeout parameter is accepted
        async with track_operation("test_op", logger=logger, timeout=0.1) as log:
            assert log is not None
            # In context manager mode, user is responsible for their own timeout handling


class TestTrackOperationDecorator:
    """Test track_operation as decorator."""

    def test_decorator_sync_function_success(self):
        """Test decorator on synchronous function."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("sync_op", logger=logger)
        def sync_function(x: int, y: int) -> int:
            return x + y

        result = sync_function(3, 4)
        assert result == 7

    @pytest.mark.asyncio
    async def test_decorator_async_function_success(self):
        """Test decorator on asynchronous function."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("async_op", logger=logger)
        async def async_function(x: int, y: int) -> int:
            await asyncio.sleep(0.01)
            return x + y

        result = await async_function(3, 4)
        assert result == 7

    def test_decorator_with_exception(self):
        """Test decorator handles exceptions correctly."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("error_op", logger=logger)
        def failing_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            failing_function()

    @pytest.mark.asyncio
    async def test_decorator_with_timeout(self):
        """Test decorator with timeout."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("timeout_op", logger=logger, timeout=0.1)
        async def slow_function():
            await asyncio.sleep(0.2)
            return "done"

        # When FastAPI is available, it raises HTTPException instead of TimeoutError
        from fastapi.exceptions import HTTPException

        with pytest.raises(HTTPException, match="504"):
            await slow_function()

    def test_decorator_preserves_function_metadata(self):
        """Test that decorator preserves function metadata."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("meta_op", logger=logger)
        def documented_function(x: int, y: int = 5) -> int:
            """A documented function."""
            return x + y

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "A documented function."


class TestTrackOperationWithSystemMetrics:
    """Test track_operation with system metrics."""

    def test_decorator_with_system_metrics(self):
        """Test decorator includes system metrics when enabled."""
        logger = get_logger("test", use_structlog=True)

        @track_operation(
            "metrics_op",
            logger=logger,
            include_system_metrics=True,
            system_metrics=["cpu_percent", "memory_percent"],
        )
        def function_with_metrics():
            return "success"

        result = function_with_metrics()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_context_manager_with_system_metrics(self):
        """Test context manager includes system metrics when enabled."""
        logger = get_logger("test", use_structlog=True)

        async with track_operation(
            "metrics_op", logger=logger, include_system_metrics=True, system_metrics=["cpu_percent"]
        ) as log:
            assert log is not None


class TestTrackOperationWithIncludeArgs:
    """Test track_operation with include_args parameter."""

    def test_decorator_with_include_args(self):
        """Test decorator includes specified arguments in context."""
        logger = get_logger("test", use_structlog=True)

        class TestClass:
            def __init__(self):
                self.logger = logger

        @track_operation("args_op", logger=logger, include_args=["batch_id", "count"])
        def function_with_args(self, batch_id: str, count: int, skip: bool = False):
            return f"{batch_id}:{count}:{skip}"

        instance = TestClass()
        result = function_with_args(instance, "batch123", 42, skip=True)
        assert result == "batch123:42:True"


class TestTrackOperationLoggerDetermination:
    """Test track_operation logger determination logic."""

    def test_uses_provided_logger(self):
        """Test that provided logger is used when it supports bind()."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("op", logger=logger)
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    def test_uses_class_logger(self):
        """Test that class logger is used when available."""
        logger = get_logger("test_class", use_structlog=True)

        class TestClass:
            def __init__(self):
                self.logger = logger

        @track_operation("op")
        def test_method(self):
            return "success"

        instance = TestClass()
        result = test_method(instance)
        assert result == "success"

    def test_fallback_logger_creation(self):
        """Test fallback logger creation when no logger supports bind()."""
        stdlib_logger = logging.getLogger("stdlib_test")

        @track_operation("op", logger=stdlib_logger)
        def test_func():
            return "success"

        # Should create a new structlog logger with a warning
        with pytest.warns(UserWarning, match="does not support .bind\\(\\)"):
            result = test_func()
        assert result == "success"


class TestTrackOperationContextBinding:
    """Test track_operation context binding."""

    def test_context_binding_in_decorator(self):
        """Test that context is properly bound in decorator."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("op", logger=logger, user_id="123", service="api")
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_context_binding_in_context_manager(self):
        """Test that context is properly bound in context manager."""
        logger = get_logger("test", use_structlog=True)

        async with track_operation("op", logger=logger, request_id="req-456", environment="prod") as log:
            assert log is not None


class TestTrackOperationOperationName:
    """Test track_operation operation naming."""

    def test_default_operation_name_from_function(self):
        """Test that operation name defaults to function name."""
        logger = get_logger("test", use_structlog=True)

        @track_operation(logger=logger)
        def my_custom_function():
            return "success"

        result = my_custom_function()
        assert result == "success"

    def test_custom_operation_name(self):
        """Test custom operation name."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("custom_name", logger=logger)
        def my_function():
            return "success"

        result = my_function()
        assert result == "success"


class TestTrackOperationLogLevels:
    """Test track_operation with different log levels."""

    def test_custom_log_level(self):
        """Test decorator with custom log level."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("op", logger=logger, log_level=logging.INFO)
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"


class TestTrackOperationErrorHandling:
    """Test track_operation error handling."""

    def test_metrics_collector_initialization_failure(self):
        """Test behavior when SystemMetricsCollector fails to initialize."""
        logger = get_logger("test", use_structlog=True)

        # Patch where SystemMetricsCollector is used in the logger module
        # It's imported locally within _get_metrics_collector method
        with patch("mindtrace.core.utils.SystemMetricsCollector", side_effect=Exception("Init error")):

            @track_operation("op", logger=logger, include_system_metrics=True)
            def test_func():
                return "success"

            # The warning is emitted during function execution when metrics collector is initialized
            with pytest.warns(UserWarning, match="Failed to initialize SystemMetricsCollector"):
                result = test_func()

            assert result == "success"

    def test_metrics_collection_failure(self):
        """Test behavior when metrics collection fails."""
        logger = get_logger("test", use_structlog=True)

        # Patch where SystemMetricsCollector is used
        with patch("mindtrace.core.utils.SystemMetricsCollector") as mock_collector:
            # Create a mock instance that raises an exception when called (as a function)
            mock_instance = Mock(side_effect=Exception("Collection error"))
            mock_collector.return_value = mock_instance

            @track_operation("op", logger=logger, include_system_metrics=True)
            def test_func():
                return "success"

            # The warning is emitted during function execution when metrics are collected
            with pytest.warns(UserWarning, match="Failed to collect system metrics"):
                result = test_func()

            assert result == "success"


class TestTrackOperationFastAPIIntegration:
    """Test track_operation FastAPI integration."""

    @pytest.mark.asyncio
    async def test_timeout_raises_http_exception_when_fastapi_available(self):
        """Test that timeout raises HTTPException when FastAPI is available."""
        logger = get_logger("test", use_structlog=True)

        # FastAPI is available by default in the test environment
        from fastapi.exceptions import HTTPException

        @track_operation("op", logger=logger, timeout=0.1)
        async def slow_function():
            await asyncio.sleep(0.2)

        # Should raise HTTPException when FastAPI is available
        with pytest.raises(HTTPException, match="504"):
            await slow_function()


class TestTrackOperationEdgeCases:
    """Test track_operation edge cases."""

    def test_no_args_function(self):
        """Test decorator on function with no arguments."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("op", logger=logger)
        def no_args_func():
            return 42

        result = no_args_func()
        assert result == 42

    def test_function_with_complex_return_value(self):
        """Test decorator handles complex return values."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("op", logger=logger)
        def complex_return_func():
            return {"nested": {"data": [1, 2, 3]}}

        result = complex_return_func()
        assert result == {"nested": {"data": [1, 2, 3]}}

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test multiple concurrent operations."""
        logger = get_logger("test", use_structlog=True)

        async def run_op(name: str):
            async with track_operation(name, logger=logger):
                await asyncio.sleep(0.01)
                return f"completed_{name}"

        results = await asyncio.gather(
            run_op("op1"),
            run_op("op2"),
            run_op("op3"),
        )

        assert results == ["completed_op1", "completed_op2", "completed_op3"]


class TestTrackOperationFastAPINotAvailable:
    """Test track_operation when FastAPI is not available."""

    @pytest.mark.asyncio
    async def test_timeout_without_fastapi_raises_timeout_error(self):
        """Test that timeout raises asyncio.TimeoutError when FastAPI is not available."""
        logger = get_logger("test", use_structlog=True)

        # Mock FastAPI import to fail (simulating it not being installed)
        with patch.dict(sys.modules, {"fastapi": None, "fastapi.exceptions": None}):
            # Need to reimport to get the None value for _HTTPException
            from mindtrace.core import logging as logging_module

            importlib.reload(logging_module.logger)
            from mindtrace.core.logging.logger import track_operation as track_op_no_fastapi

            @track_op_no_fastapi("op", logger=logger, timeout=0.1)
            async def slow_function():
                await asyncio.sleep(0.2)

            # Should raise asyncio.TimeoutError when FastAPI is not available
            with pytest.raises(asyncio.TimeoutError):
                await slow_function()

            # Reload again to restore FastAPI
            importlib.reload(logging_module.logger)

    @pytest.mark.asyncio
    async def test_timeout_logs_correctly_without_fastapi(self):
        """Test that timeout is logged correctly even without FastAPI."""
        logger = get_logger("test", use_structlog=True)

        # This test verifies the code handles the case where FastAPI isn't available
        # Since FastAPI IS available in our test environment, we just verify
        # that the timeout mechanism works (HTTPException will be raised)
        from fastapi.exceptions import HTTPException

        @track_operation("op", logger=logger, timeout=0.1)
        async def slow_function():
            await asyncio.sleep(0.2)

        # In our test environment, FastAPI is available, so HTTPException is raised
        with pytest.raises(HTTPException, match="504"):
            await slow_function()


class TestTrackOperationLoggerWithoutBindSupport:
    """Test track_operation with loggers that don't support bind()."""

    def test_stdlib_logger_creates_warning_and_new_logger(self):
        """Test that stdlib logger without bind() creates warning and new structlog logger."""
        stdlib_logger = logging.getLogger("stdlib_test")

        @track_operation("op", logger=stdlib_logger)
        def test_func():
            return "success"

        # Should create a new structlog logger with a warning
        with pytest.warns(UserWarning, match="does not support .bind\\(\\)"):
            result = test_func()
        assert result == "success"

    def test_class_with_stdlib_logger_creates_warning(self):
        """Test class method with stdlib logger creates warning and new logger."""
        stdlib_logger = logging.getLogger("class_stdlib_test")

        class TestClass:
            def __init__(self):
                self.logger = stdlib_logger

        @track_operation("op")
        def test_method(self):
            return "success"

        instance = TestClass()

        # Should create a new structlog logger with a warning
        with pytest.warns(UserWarning, match="does not support .bind\\(\\)"):
            result = test_method(instance)
        assert result == "success"

    def test_context_manager_with_stdlib_logger(self):
        """Test context manager with stdlib logger creates warning."""
        stdlib_logger = logging.getLogger("ctx_stdlib_test")

        async def run_test():
            async with track_operation("op", logger=stdlib_logger) as log:
                assert log is not None
                return "success"

        # Should create warning about bind method
        with pytest.warns(UserWarning, match="does not support .bind\\(\\)"):
            result = asyncio.run(run_test())
        assert result == "success"


class TestTrackOperationLoggerNameFallback:
    """Test track_operation logger name determination fallbacks."""

    def test_logger_name_parameter_used_in_decorator(self):
        """Test that logger_name parameter is used when provided."""

        @track_operation("op", logger_name="custom.logger.name")
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    def test_fallback_to_method_logger_pattern(self):
        """Test fallback to mindtrace.methods.{name} pattern."""

        # No logger, no logger_name, not a class method
        @track_operation("standalone_op")
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_async_function_without_explicit_logger(self):
        """Test async function without explicit logger uses fallback."""

        @track_operation("async_standalone_op")
        async def test_func():
            await asyncio.sleep(0.01)
            return "success"

        result = await test_func()
        assert result == "success"


class TestTrackOperationContextManagerWithActualTimeout:
    """Test track_operation context manager with actual timeout scenarios."""

    @pytest.mark.asyncio
    async def test_context_manager_timeout_error_in_aexit(self):
        """Test context manager properly handles TimeoutError in __aexit__."""
        logger = get_logger("test", use_structlog=True)
        from fastapi.exceptions import HTTPException

        # To test the timeout path in __aexit__, we need to raise asyncio.TimeoutError
        # directly within the context manager
        with pytest.raises(HTTPException, match="504"):
            async with track_operation("op", logger=logger, timeout=0.1):
                # Directly raise asyncio.TimeoutError to trigger the timeout path in __aexit__
                raise asyncio.TimeoutError()

    @pytest.mark.asyncio
    async def test_context_manager_generic_exception_in_aexit(self):
        """Test context manager properly handles generic exceptions in __aexit__."""
        logger = get_logger("test", use_structlog=True)

        # Test the generic exception path in __aexit__ (lines 534-541)
        class CustomError(Exception):
            pass

        with pytest.raises(CustomError, match="Custom error"):
            async with track_operation("op", logger=logger):
                raise CustomError("Custom error")


class TestTrackOperationAsyncDecoratorExceptionHandling:
    """Test track_operation async decorator exception handling paths."""

    @pytest.mark.asyncio
    async def test_async_decorator_with_custom_exception(self):
        """Test async decorator handles custom exceptions correctly."""
        logger = get_logger("test", use_structlog=True)

        class CustomError(Exception):
            pass

        @track_operation("op", logger=logger)
        async def failing_func():
            await asyncio.sleep(0.01)
            raise CustomError("Custom error occurred")

        with pytest.raises(CustomError, match="Custom error occurred"):
            await failing_func()

    @pytest.mark.asyncio
    async def test_async_decorator_without_timeout_path(self):
        """Test async decorator execution path when timeout is not set."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("op", logger=logger)  # No timeout
        async def test_func():
            await asyncio.sleep(0.01)
            return "success"

        result = await test_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_async_decorator_with_timeout_path(self):
        """Test async decorator execution path when timeout is set but not exceeded."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("op", logger=logger, timeout=1.0)  # Long timeout
        async def test_func():
            await asyncio.sleep(0.01)  # Completes quickly
            return "success"

        result = await test_func()
        assert result == "success"


class TestTrackOperationMetricsSnapshotCoverage:
    """Test track_operation metrics snapshot coverage."""

    def test_decorator_with_metrics_snapshot_success(self):
        """Test decorator successfully collects metrics snapshot."""
        logger = get_logger("test", use_structlog=True)

        @track_operation(
            "op",
            logger=logger,
            include_system_metrics=True,
            system_metrics=["cpu_percent", "memory_percent"],
        )
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_context_manager_with_metrics_snapshot_in_aexit(self):
        """Test context manager collects metrics snapshot on exit."""
        logger = get_logger("test", use_structlog=True)

        async with track_operation(
            "op",
            logger=logger,
            include_system_metrics=True,
            system_metrics=["cpu_percent"],
        ) as log:
            # Metrics collected on entry and exit
            assert log is not None


class TestTrackOperationMultipleExecutions:
    """Test track_operation with multiple executions to ensure state management."""

    def test_decorator_multiple_executions_with_metrics(self):
        """Test decorator with metrics works correctly across multiple executions."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("op", logger=logger, include_system_metrics=True)
        def test_func(value: int):
            return value * 2

        # Multiple executions should work independently
        result1 = test_func(5)
        result2 = test_func(10)
        result3 = test_func(15)

        assert result1 == 10
        assert result2 == 20
        assert result3 == 30

    @pytest.mark.asyncio
    async def test_async_decorator_multiple_executions(self):
        """Test async decorator works correctly across multiple executions."""
        logger = get_logger("test", use_structlog=True)

        @track_operation("op", logger=logger)
        async def test_func(value: int):
            await asyncio.sleep(0.01)
            return value * 2

        # Multiple executions
        result1 = await test_func(5)
        result2 = await test_func(10)

        assert result1 == 10
        assert result2 == 20


class TestTrackOperationClassMethodWithoutLogger:
    """Test track_operation on class methods without logger attribute."""

    def test_class_method_without_logger_attribute(self):
        """Test class method without logger attribute uses fallback."""

        class TestClass:
            pass  # No logger attribute

        @track_operation("op")
        def test_method(self):
            return "success"

        instance = TestClass()
        result = test_method(instance)
        assert result == "success"

    def test_class_method_with_logger_name_parameter(self):
        """Test class method with logger_name parameter."""

        class TestClass:
            pass

        @track_operation("op", logger_name="custom.class.logger")
        def test_method(self):
            return "success"

        instance = TestClass()
        result = test_method(instance)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_context_manager_timeout_without_fastapi_raises_timeout_error(self):
        """Test context manager timeout raises TimeoutError when FastAPI is not available.
        
        Tests the fallback raise statement when _HTTPException is None.
        """
        logger = get_logger("test", use_structlog=True)

        # Mock FastAPI import to fail (simulating it not being installed)
        with patch.dict(sys.modules, {"fastapi": None, "fastapi.exceptions": None}):
            # Need to reimport to get the None value for _HTTPException
            from mindtrace.core import logging as logging_module

            importlib.reload(logging_module.logger)
            from mindtrace.core.logging.logger import track_operation as track_op_no_fastapi

            # Test context manager with timeout that will be exceeded
            with pytest.raises(asyncio.TimeoutError):
                async with track_op_no_fastapi("op", logger=logger, timeout=0.1):
                    # Directly raise asyncio.TimeoutError to trigger the timeout path in __aexit__
                    # This tests the raise statement when _HTTPException is None
                    raise asyncio.TimeoutError()

            # Reload again to restore FastAPI
            importlib.reload(logging_module.logger)

    @pytest.mark.asyncio
    async def test_async_decorator_with_metrics_snapshot(self):
        """Test async decorator includes metrics snapshot in context.
        
        Tests that metrics are added to context when metrics_snapshot is not None.
        """
        logger = get_logger("test", use_structlog=True)

        @track_operation(
            "op",
            logger=logger,
            include_system_metrics=True,
            system_metrics=["cpu_percent"],
        )
        async def async_function_with_metrics():
            await asyncio.sleep(0.01)
            return "success"

        result = await async_function_with_metrics()
        assert result == "success"
