"""Tests for the Mindtrace base classes."""

import pytest
import logging
from unittest.mock import Mock, patch
from abc import abstractmethod

from mindtrace.core.base.mindtrace_base import Mindtrace, MindtraceABC, MindtraceMeta


class TestMindtraceMeta:
    """Tests for the MindtraceMeta metaclass."""

    def test_unique_name_property(self):
        """Test that unique_name property returns correct module path."""
        class TestClass(metaclass=MindtraceMeta):
            pass
        
        assert TestClass.unique_name == "test_mindtrace_base.TestClass"

    def test_logger_property(self):
        """Test that logger property returns a logger instance."""
        class TestClass(metaclass=MindtraceMeta):
            pass
        
        assert isinstance(TestClass.logger, logging.Logger)
        assert TestClass.logger.name == f"mindtrace.{TestClass.unique_name}"

    def test_logger_setter(self):
        """Test that logger setter works correctly."""
        class TestClass(metaclass=MindtraceMeta):
            pass
        
        # Test that logger setter works
        new_logger = logging.getLogger("test_logger")
        TestClass.logger = new_logger
        assert TestClass.logger == new_logger

    def test_logger_setter_functionality(self):
        """Test the logger setter functionality."""
        class TestClass(metaclass=MindtraceMeta):
            pass
        
        # Get the original logger
        original_logger = TestClass.logger
        assert isinstance(original_logger, logging.Logger)
        
        # Create a new mock logger
        new_logger = Mock(spec=logging.Logger)
        new_logger.name = "test.custom.logger"
        
        # Test the setter functionality
        TestClass.logger = new_logger
        
        # Verify the logger was set correctly
        assert TestClass.logger is new_logger
        assert TestClass.logger.name == "test.custom.logger"
        
        # Verify the internal _logger attribute was set correctly
        assert TestClass._logger is new_logger
        
        # Test that we can set it back to None and it will auto-regenerate
        TestClass.logger = None
        assert TestClass._logger is None  # Internal attribute should be None
        
        # When we access the logger property, it should auto-regenerate
        regenerated_logger = TestClass.logger
        assert regenerated_logger is not None
        assert isinstance(regenerated_logger, logging.Logger)
        assert TestClass._logger is regenerated_logger  # Should be set by the getter
        
        # Test setting back to a real logger
        custom_logger = logging.getLogger("custom.test.logger")
        TestClass.logger = custom_logger
        assert TestClass.logger is custom_logger
        assert TestClass._logger is custom_logger

    def test_logger_setter_with_multiple_classes(self):
        """Test that logger setter works independently for different classes."""
        class TestClass1(metaclass=MindtraceMeta):
            pass
            
        class TestClass2(metaclass=MindtraceMeta):
            pass
        
        # Create different loggers for each class
        logger1 = Mock(spec=logging.Logger)
        logger1.name = "logger1"
        logger2 = Mock(spec=logging.Logger)
        logger2.name = "logger2"
        
        # Set different loggers for each class
        TestClass1.logger = logger1
        TestClass2.logger = logger2
        
        # Verify each class has its own logger
        assert TestClass1.logger is logger1
        assert TestClass2.logger is logger2
        assert TestClass1.logger is not TestClass2.logger
        
        # Verify internal attributes are set correctly
        assert TestClass1._logger is logger1
        assert TestClass2._logger is logger2


class TestMindtrace:
    """Tests for the Mindtrace base class."""

    def test_init(self):
        """Test initialization of Mindtrace class."""
        instance = Mindtrace()
        assert hasattr(instance, 'config')
        assert hasattr(instance, 'logger')

    def test_init_with_logger_kwargs(self):
        """Test initialization with logger-specific kwargs."""
        instance = Mindtrace(log_dir="/tmp", logger_level=logging.INFO)
        assert hasattr(instance, 'config')
        assert hasattr(instance, 'logger')
        assert instance.logger.level == logging.INFO

    def test_init_with_parent_class_kwargs_rejection(self):
        """Test initialization when parent class rejects kwargs."""
        # Create a class that inherits from Mindtrace but has a parent that rejects kwargs
        class ParentClass:
            def __init__(self, specific_arg=None):
                self.specific_arg = specific_arg
        
        class TestClass(Mindtrace, ParentClass):
            pass
        
        # This should work without raising TypeError
        instance = TestClass(specific_arg="test")
        assert instance.specific_arg == "test"
        assert hasattr(instance, 'config')
        assert hasattr(instance, 'logger')

    def test_init_with_parent_class_kwargs_rejection_fallback(self):
        """Test initialization when parent class rejects kwargs and fallback to no kwargs."""
        # Create a class that inherits from Mindtrace but has a parent that rejects all kwargs
        class ParentClass:
            def __init__(self):
                pass
        
        class TestClass(Mindtrace, ParentClass):
            pass
        
        # This should work without raising TypeError
        instance = TestClass(some_kwarg="test")
        assert hasattr(instance, 'config')
        assert hasattr(instance, 'logger')

    def test_context_manager(self):
        """Test context manager functionality."""
        with Mindtrace() as mt:
            assert isinstance(mt, Mindtrace)

    def test_context_manager_exception_handling(self):
        """Test context manager exception handling."""
        with pytest.raises(ValueError):
            with Mindtrace() as mt:
                raise ValueError("Test exception")

    def test_context_manager_exception_suppression(self):
        """Test context manager exception suppression."""
        with patch('mindtrace.core.base.mindtrace_base.get_logger') as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            
            with Mindtrace(suppress=True) as mt:
                raise ValueError("Test exception")
            # Exception should be suppressed, so no exception should be raised
            
            # Verify that the exception was logged
            mock_logger.exception.assert_called_once()
            call_args = mock_logger.exception.call_args
            assert call_args[0][0] == "Exception occurred"  # Check the message
            assert call_args[1]['exc_info'] is not None  # Check that exc_info was provided

    def test_init_exception_handling_first_branch(self):
        """Test initialization exception handling - first branch.
        
        This tests the case where super().__init__(**kwargs) fails, but 
        super().__init__(**remaining_kwargs) succeeds after removing logger-specific kwargs.
        """
        # Create a parent class that accepts some kwargs but not logger-specific ones
        class ParentClass:
            def __init__(self, valid_param=None):
                # This parent class only accepts valid_param, not **kwargs
                self.valid_param = valid_param

        class TestClass(Mindtrace, ParentClass):
            def __init__(self, **kwargs):
                # Call Mindtrace.__init__ first - this is where the exception handling happens
                super().__init__(**kwargs)

        # Test with logger-specific kwargs that should trigger first branch
        # ParentClass doesn't accept logger kwargs, so Mindtrace's first super().__init__(**kwargs) will fail
        # But the second call super().__init__(**remaining_kwargs) with valid_param should succeed
        instance = TestClass(valid_param="test", log_dir="/tmp/logs")
        
        # Verify the instance was created successfully
        assert isinstance(instance, TestClass)
        assert isinstance(instance, Mindtrace)
        assert hasattr(instance, 'logger')
        assert instance.valid_param == "test"

    def test_init_exception_handling_second_branch(self):
        """Test initialization exception handling - second branch.
        
        This tests the case where both super().__init__(**kwargs) and 
        super().__init__(**remaining_kwargs) fail, so it falls back to 
        super().__init__() with no arguments.
        """
        # Create a parent class that doesn't accept any arguments at all
        class StrictParentClass:
            def __init__(self):
                # This class accepts no arguments at all
                self.initialized = True

        class TestClass(Mindtrace, StrictParentClass):
            def __init__(self, **kwargs):
                # Call Mindtrace.__init__ first - this is where the exception handling happens
                super().__init__(**kwargs)

        # Test with kwargs - should trigger second branch since StrictParentClass accepts no args
        instance = TestClass(some_param="value", log_dir="/tmp/logs")
        
        # Verify the instance was created successfully using the no-args fallback
        assert isinstance(instance, TestClass)
        assert isinstance(instance, Mindtrace) 
        assert hasattr(instance, 'logger')
        assert hasattr(instance, 'initialized')
        assert instance.initialized is True  # Parent class was initialized with no args

    def test_init_exception_handling_with_multiple_inheritance_order(self):
        """Test that the exception handling works with different inheritance orders."""
        class AnotherParentClass:
            def __init__(self):
                # Simplified - this parent accepts no arguments
                self.parent_initialized = True

        # Test with Mindtrace first in MRO
        class TestClass1(Mindtrace, AnotherParentClass):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)

        # This should work via exception handling (second branch - no args fallback)
        instance1 = TestClass1(log_dir="/tmp/logs", some_param="value")
        assert isinstance(instance1, TestClass1)
        assert isinstance(instance1, Mindtrace)
        assert hasattr(instance1, 'parent_initialized')
        assert instance1.parent_initialized is True

    def test_autolog_decorator(self):
        """Test the autolog decorator functionality."""
        class TestClass(Mindtrace):
            @Mindtrace.autolog()
            def test_method(self, x, y):
                return x + y

        instance = TestClass()
        with patch.object(instance.logger, 'log') as mock_log:
            result = instance.test_method(2, 3)
            assert result == 5
            assert mock_log.call_count == 2  # One for prefix, one for suffix

    def test_autolog_decorator_with_exception(self):
        """Test autolog decorator with exception handling."""
        class TestClass(Mindtrace):
            @Mindtrace.autolog()
            def test_method(self, x, y):
                raise ValueError("Test error")

        instance = TestClass()
        with patch.object(instance.logger, 'error') as mock_error:
            with pytest.raises(ValueError):
                instance.test_method(2, 3)
            assert mock_error.call_count == 1

    def test_autolog_exception_handling_core_functionality(self):
        """Test the exception handling in autolog decorator.
        
        This tests that when a decorated method raises an exception:
        1. The exception is caught
        2. It's logged using the exception formatter
        3. The original exception is re-raised
        """
        class TestClass(Mindtrace):
            @Mindtrace.autolog()
            def method_that_raises(self, should_raise=True):
                if should_raise:
                    raise ValueError("Test exception from decorated method")
                return "success"

        instance = TestClass()
        
        # Test that exception is caught, logged, and re-raised
        with patch.object(instance.logger, 'error') as mock_error, \
             patch.object(instance.logger, 'log') as mock_log:
            
            # This should trigger exception handling in the autolog decorator
            with pytest.raises(ValueError, match="Test exception from decorated method"):
                instance.method_that_raises(should_raise=True)
            
            # Verify exception was logged with proper formatter
            assert mock_error.call_count == 1
            error_call_args = mock_error.call_args[0][0]
            assert "method_that_raises failed to complete" in error_call_args
            assert "Test exception from decorated method" in error_call_args
            assert "Traceback" in error_call_args  # Stack trace included
            
            # Verify prefix log was called (before exception)
            assert mock_log.call_count >= 1  # At least the prefix call

    def test_autolog_exception_handling_with_custom_formatter(self):
        """Test exception handling with custom exception formatter."""
        def custom_exception_formatter(function, error, stack_trace):
            return f"CUSTOM ERROR in {function.__name__}: {error} | {stack_trace[:50]}..."

        class TestClass(Mindtrace):
            @Mindtrace.autolog(exception_formatter=custom_exception_formatter)
            def failing_method(self):
                raise RuntimeError("Custom test error")

        instance = TestClass()
        
        with patch.object(instance.logger, 'error') as mock_error:
            with pytest.raises(RuntimeError):
                instance.failing_method()
            
            # Verify custom formatter was used
            assert mock_error.call_count == 1
            logged_message = mock_error.call_args[0][0]
            assert "CUSTOM ERROR in failing_method" in logged_message
            assert "Custom test error" in logged_message

    def test_autolog_exception_handling_async_method(self):
        """Test exception handling in async decorated methods (async version)."""
        import asyncio

        class TestClass(Mindtrace):
            @Mindtrace.autolog()
            async def async_failing_method(self, error_msg):
                raise ConnectionError(error_msg)

        async def run_test():
            instance = TestClass()
            
            with patch.object(instance.logger, 'error') as mock_error, \
                 patch.object(instance.logger, 'log') as mock_log:
                
                # This should trigger the async version
                with pytest.raises(ConnectionError, match="Async test error"):
                    await instance.async_failing_method("Async test error")
                
                # Verify exception was logged
                assert mock_error.call_count == 1
                error_message = mock_error.call_args[0][0]
                assert "async_failing_method failed to complete" in error_message
                assert "Async test error" in error_message

        asyncio.run(run_test())

    def test_autolog_exception_handling_preserves_exception_details(self):
        """Test that exception handling preserves all exception details."""
        class CustomException(Exception):
            def __init__(self, message, error_code):
                super().__init__(message)
                self.error_code = error_code

        class TestClass(Mindtrace):
            @Mindtrace.autolog()
            def method_with_custom_exception(self):
                raise CustomException("Custom error message", 404)

        instance = TestClass()
        
        with patch.object(instance.logger, 'error'):
            # Verify the original exception is preserved and re-raised
            with pytest.raises(CustomException) as exc_info:
                instance.method_with_custom_exception()
            
            # Check that all exception details are preserved
            assert str(exc_info.value) == "Custom error message"
            assert exc_info.value.error_code == 404
            assert type(exc_info.value) is CustomException

    def test_autolog_exception_handling_with_external_self(self):
        """Test exception handling when self is passed explicitly to autolog decorator."""
        class MyClass(Mindtrace):
            pass

        def create_standalone_function(instance):
            @Mindtrace.autolog(self=instance)  # Testing external self parameter
            def failing_function():
                raise ValueError("Endpoint error")
            return failing_function

        instance = MyClass()
        failing_func = create_standalone_function(instance)
        
        with patch.object(instance.logger, 'error') as mock_error:
            # This should trigger exception handling with external self
            with pytest.raises(ValueError, match="Endpoint error"):
                failing_func()
            
            # Verify the exception was logged using the external self's logger
            assert mock_error.call_count == 1
            
            # Verify the exception was logged with proper formatting
            error_message = mock_error.call_args[0][0]
            assert "failing_function failed to complete" in error_message
            assert "Endpoint error" in error_message

    def test_autolog_decorator_with_async(self):
        """Test autolog decorator with async methods."""
        import asyncio

        class TestClass(Mindtrace):
            @Mindtrace.autolog()
            async def test_method(self, x, y):
                return x + y

        async def run_test():
            instance = TestClass()
            with patch.object(instance.logger, 'log') as mock_log:
                result = await instance.test_method(2, 3)
                assert result == 5
                assert mock_log.call_count == 2

        asyncio.run(run_test())

    def test_autolog_decorator_with_async_exception(self):
        """Test autolog decorator with exception handling in  async methods."""
        import asyncio

        class TestClass(Mindtrace):
            @Mindtrace.autolog()
            async def test_method(self, x, y):
                raise ValueError("Test error")

        async def run_test():
            instance = TestClass()
            with patch.object(instance.logger, 'error') as mock_error:
                with pytest.raises(ValueError):
                    await instance.test_method(2, 3)
                assert mock_error.call_count == 1

        asyncio.run(run_test())

    def test_autolog_with_custom_formatters(self):
        """Test autolog decorator with custom formatters."""
        def custom_prefix(func, args, kwargs):
            return f"Custom prefix for {func.__name__}"

        def custom_suffix(func, result):
            return f"Custom suffix for {func.__name__}"

        class TestClass(Mindtrace):
            @Mindtrace.autolog(
                prefix_formatter=custom_prefix,
                suffix_formatter=custom_suffix
            )
            def test_method(self, x, y):
                return x + y

        instance = TestClass()
        with patch.object(instance.logger, 'log') as mock_log:
            result = instance.test_method(2, 3)
            assert result == 5
            assert mock_log.call_count == 2
            assert "Custom prefix" in mock_log.call_args_list[0][0][1]
            assert "Custom suffix" in mock_log.call_args_list[1][0][1]

    def test_autolog_with_self_parameter_sync(self):
        """Test autolog decorator with self parameter for sync functions."""
        class TestClass(Mindtrace):
            def test_method(self, x, y):
                return x + y

        instance = TestClass()
        # Decorate the method with self parameter
        decorated_method = Mindtrace.autolog(self=instance)(instance.test_method)
        with patch.object(instance.logger, 'log') as mock_log:
            result = decorated_method(2, 3)
            assert result == 5
            assert mock_log.call_count == 2  # One for prefix, one for suffix

    def test_autolog_with_self_parameter_exception_sync(self):
        """Test autolog decorator with self parameter and exception handling for sync functions."""
        class TestClass(Mindtrace):
            def test_method(self, x, y):
                raise ValueError("Test error")

        instance = TestClass()
        decorated_method = Mindtrace.autolog(self=instance)(instance.test_method)
        with patch.object(instance.logger, 'error') as mock_error:
            with pytest.raises(ValueError):
                decorated_method(2, 3)
            assert mock_error.call_count == 1

    def test_autolog_with_self_parameter_async(self):
        """Test autolog decorator with self parameter for async functions."""
        import asyncio
        class TestClass(Mindtrace):
            async def test_method(self, x, y):
                return x + y
        async def run_test():
            instance = TestClass()
            decorated_method = Mindtrace.autolog(self=instance)(instance.test_method)
            with patch.object(instance.logger, 'log') as mock_log:
                result = await decorated_method(2, 3)
                assert result == 5
                assert mock_log.call_count == 2
        asyncio.run(run_test())

    def test_autolog_with_self_parameter_exception_async(self):
        """Test autolog decorator with self parameter and exception handling for async functions."""
        import asyncio
        class TestClass(Mindtrace):
            async def test_method(self, x, y):
                raise ValueError("Test error")
        async def run_test():
            instance = TestClass()
            decorated_method = Mindtrace.autolog(self=instance)(instance.test_method)
            with patch.object(instance.logger, 'error') as mock_error:
                with pytest.raises(ValueError):
                    await decorated_method(2, 3)
                assert mock_error.call_count == 1
        asyncio.run(run_test())

    def test_autolog_async_wrapper_with_external_self_success_branch(self):
        """Test the async wrapper success branch with external self (else clause)."""
        import asyncio

        class LoggerOwner(Mindtrace):
            pass

        async def standalone_async_function(x, y, multiplier=1):
            """A standalone async function for testing."""
            await asyncio.sleep(0.001)  # Simulate async work
            return (x + y) * multiplier

        async def run_test():
            logger_owner = LoggerOwner()
            
            # Apply the autolog decorator with external self
            decorated_func = Mindtrace.autolog(self=logger_owner)(standalone_async_function)
            
            with patch.object(logger_owner.logger, 'log') as mock_log:
                # Test the success branch (else clause)
                result = await decorated_func(3, 7, multiplier=2)
                
                # Verify the result is correct
                assert result == 20  # (3 + 7) * 2
                
                # Verify logging calls - should have prefix and suffix logs
                assert mock_log.call_count == 2
                
                # Verify prefix log (before execution)
                prefix_call = mock_log.call_args_list[0]
                assert "Calling standalone_async_function with args: (3, 7)" in prefix_call[0][1]
                assert "'multiplier': 2" in prefix_call[0][1]
                
                # Verify suffix log (after successful execution)
                suffix_call = mock_log.call_args_list[1]
                assert "Finished standalone_async_function with result: 20" in suffix_call[0][1]

        asyncio.run(run_test())

    def test_autolog_async_wrapper_with_external_self_exception_branch(self):
        """Test the async wrapper exception branch with external self."""
        import asyncio

        class LoggerOwner(Mindtrace):
            pass

        async def failing_async_function(should_fail=True):
            """An async function that raises an exception."""
            await asyncio.sleep(0.001)  # Simulate async work
            if should_fail:
                raise ValueError("Async function failed")
            return "success"

        async def run_test():
            logger_owner = LoggerOwner()
            decorated_func = Mindtrace.autolog(self=logger_owner)(failing_async_function)
            
            with patch.object(logger_owner.logger, 'log') as mock_log, \
                 patch.object(logger_owner.logger, 'error') as mock_error:
                
                # Test the exception branch
                with pytest.raises(ValueError, match="Async function failed"):
                    await decorated_func(should_fail=True)
                
                # Verify prefix log was called (before exception)
                assert mock_log.call_count == 1
                prefix_call = mock_log.call_args_list[0]
                assert "Calling failing_async_function" in prefix_call[0][1]
                
                # Verify exception was logged
                assert mock_error.call_count == 1
                error_call = mock_error.call_args[0][0]
                assert "failing_async_function failed to complete" in error_call
                assert "Async function failed" in error_call

        asyncio.run(run_test())

    def test_autolog_async_wrapper_preserves_function_metadata(self):
        """Test that @wraps(function) preserves the original function's metadata."""
        import asyncio

        class LoggerOwner(Mindtrace):
            pass

        async def documented_async_function(param1: int, param2: str = "default") -> str:
            """This is a documented async function.
            
            Args:
                param1: An integer parameter
                param2: A string parameter with default value
                
            Returns:
                A formatted string
            """
            return f"param1={param1}, param2={param2}"

        logger_owner = LoggerOwner()
        decorated_func = Mindtrace.autolog(self=logger_owner)(documented_async_function)
        
        # Verify metadata is preserved
        assert decorated_func.__name__ == "documented_async_function"
        assert "This is a documented async function" in decorated_func.__doc__
        assert decorated_func.__annotations__ == documented_async_function.__annotations__
        
        # Verify the function still works correctly
        async def run_test():
            result = await decorated_func(42, "test")
            assert result == "param1=42, param2=test"
            
        asyncio.run(run_test())

    def test_autolog_async_wrapper_with_custom_formatters(self):
        """Test async wrapper with custom prefix, suffix, and exception formatters."""
        import asyncio

        def custom_prefix(func, args, kwargs):
            return f"[ASYNC-START] {func.__name__} called with {len(args)} args"

        def custom_suffix(func, result):
            return f"[ASYNC-END] {func.__name__} returned: {type(result).__name__}"

        def custom_exception(func, error, stack_trace):
            return f"[ASYNC-ERROR] {func.__name__} crashed: {error}"

        class LoggerOwner(Mindtrace):
            pass

        async def test_async_function(value):
            await asyncio.sleep(0.001)
            if value < 0:
                raise ValueError("Negative value")
            return {"result": value * 2}

        async def run_test():
            logger_owner = LoggerOwner()
            decorated_func = Mindtrace.autolog(
                self=logger_owner,
                prefix_formatter=custom_prefix,
                suffix_formatter=custom_suffix,
                exception_formatter=custom_exception
            )(test_async_function)
            
            with patch.object(logger_owner.logger, 'log') as mock_log, \
                 patch.object(logger_owner.logger, 'error') as mock_error:
                
                # Test success case
                result = await decorated_func(5)
                assert result == {"result": 10}
                
                # Verify custom formatters were used
                assert mock_log.call_count == 2
                assert "[ASYNC-START] test_async_function called with 1 args" in mock_log.call_args_list[0][0][1]
                assert "[ASYNC-END] test_async_function returned: dict" in mock_log.call_args_list[1][0][1]
                
                # Test exception case
                mock_log.reset_mock()
                with pytest.raises(ValueError):
                    await decorated_func(-1)
                
                # Verify custom exception formatter was used
                assert mock_error.call_count == 1
                assert "[ASYNC-ERROR] test_async_function crashed: Negative value" in mock_error.call_args[0][0]

        asyncio.run(run_test())

    def test_autolog_async_wrapper_with_no_args_and_kwargs(self):
        """Test async wrapper handles functions with no arguments correctly."""
        import asyncio

        class LoggerOwner(Mindtrace):
            pass

        async def no_args_async_function():
            """Function with no arguments."""
            await asyncio.sleep(0.001)
            return "no args result"

        async def run_test():
            logger_owner = LoggerOwner()
            decorated_func = Mindtrace.autolog(self=logger_owner)(no_args_async_function)
            
            with patch.object(logger_owner.logger, 'log') as mock_log:
                result = await decorated_func()
                
                assert result == "no args result"
                assert mock_log.call_count == 2
                
                # Verify args and kwargs are handled correctly (should be empty)
                prefix_call = mock_log.call_args_list[0][0][1]
                assert "with args: ()" in prefix_call
                assert "kwargs: {}" in prefix_call

        asyncio.run(run_test())

    def test_autolog_async_wrapper_integration_with_different_return_types(self):
        """Test async wrapper handles different return types correctly."""
        import asyncio

        class LoggerOwner(Mindtrace):
            pass

        async def return_none():
            await asyncio.sleep(0.001)
            return None

        async def return_complex_object():
            await asyncio.sleep(0.001)
            return {"nested": {"data": [1, 2, 3]}, "count": 42}

        async def run_test():
            logger_owner = LoggerOwner()
            
            # Test None return
            none_func = Mindtrace.autolog(self=logger_owner)(return_none)
            with patch.object(logger_owner.logger, 'log') as mock_log:
                result = await none_func()
                assert result is None
                assert "result: None" in mock_log.call_args_list[1][0][1]
            
            # Test complex object return
            complex_func = Mindtrace.autolog(self=logger_owner)(return_complex_object)
            with patch.object(logger_owner.logger, 'log') as mock_log:
                result = await complex_func()
                assert result["count"] == 42
                assert result["nested"]["data"] == [1, 2, 3]
                # The suffix formatter should handle complex objects
                assert "Finished return_complex_object with result:" in mock_log.call_args_list[1][0][1]

        asyncio.run(run_test())


class TestMindtraceABC:
    """Tests for the MindtraceABC abstract base class."""

    def test_abstract_method_implementation(self):
        """Test that abstract methods must be implemented."""
        class TestAbstractClass(MindtraceABC):
            @abstractmethod
            def test_method(self):
                pass

        with pytest.raises(TypeError):
            TestAbstractClass()

    def test_concrete_implementation(self):
        """Test concrete implementation of abstract class."""
        class TestConcreteClass(MindtraceABC):
            def test_method(self):
                return "implemented"

        instance = TestConcreteClass()
        assert instance.test_method() == "implemented"

    def test_inheritance_chain(self):
        """Test that MindtraceABC inherits both Mindtrace and ABC functionality."""
        class TestClass(MindtraceABC):
            def test_method(self):
                return "test"

        instance = TestClass()
        assert isinstance(instance, Mindtrace)
        assert hasattr(instance, 'logger')
        assert hasattr(instance, 'config')
        assert instance.test_method() == "test"


def test_fastapi_integration():
    """Test integration with FastAPI as shown in the docstring example."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    class MyClass(Mindtrace):
        def create_app(self):
            app_ = FastAPI()

            @Mindtrace.autolog(self=self)
            @app_.post("/status")
            def status():
                return {"status": "Available"}

            return app_

    instance = MyClass()
    app = instance.create_app()
    client = TestClient(app)
    
    response = client.post("/status")
    assert response.status_code == 200
    assert response.json() == {"status": "Available"}


class TestMindtraceSyncWrapper:
    """Tests for the synchronous wrapper functionality in autolog decorator."""

    def test_autolog_sync_wrapper_with_external_self_success_branch(self):
        """Test the synchronous wrapper success branch with external self (else clause)."""
        class LoggerOwner(Mindtrace):
            pass

        def standalone_sync_function(x, y, multiplier=1):
            """A standalone synchronous function for testing."""
            return (x + y) * multiplier

        logger_owner = LoggerOwner()
        
        # Apply the autolog decorator with external self
        decorated_func = Mindtrace.autolog(self=logger_owner)(standalone_sync_function)
        
        with patch.object(logger_owner.logger, 'log') as mock_log:
            # Test the success branch (else clause) - this triggers lines 316-317
            result = decorated_func(3, 7, multiplier=2)
            
            # Verify the result is correct
            assert result == 20  # (3 + 7) * 2
            
            # Verify logging calls - should have prefix and suffix logs
            assert mock_log.call_count == 2
            
            # Verify prefix log (before execution)
            prefix_call = mock_log.call_args_list[0]
            assert "Calling standalone_sync_function with args: (3, 7)" in prefix_call[0][1]
            assert "'multiplier': 2" in prefix_call[0][1]
            
            # Verify suffix log (after successful execution)
            suffix_call = mock_log.call_args_list[1]
            assert "Finished standalone_sync_function with result: 20" in suffix_call[0][1]

    def test_autolog_sync_wrapper_return_value_preservation(self):
        """Test that return result preserves all types of return values."""
        class LoggerOwner(Mindtrace):
            pass

        def return_different_types(return_type):
            """Function that returns different types based on input."""
            if return_type == "string":
                return "test string"
            elif return_type == "list":
                return [1, 2, 3, {"nested": "dict"}]
            elif return_type == "dict":
                return {"key": "value", "number": 42}
            elif return_type == "none":
                return None
            elif return_type == "tuple":
                return (1, "two", 3.0)
            elif return_type == "boolean":
                return True
            else:
                return 999

        logger_owner = LoggerOwner()
        decorated_func = Mindtrace.autolog(self=logger_owner)(return_different_types)
        
        with patch.object(logger_owner.logger, 'log') as mock_log:
            # Test different return types - return statement should preserve them all
            test_cases = [
                ("string", "test string"),
                ("list", [1, 2, 3, {"nested": "dict"}]),
                ("dict", {"key": "value", "number": 42}),
                ("none", None),
                ("tuple", (1, "two", 3.0)),
                ("boolean", True),
                ("other", 999)
            ]
            
            for input_val, expected_result in test_cases:
                mock_log.reset_mock()
                result = decorated_func(input_val)
                
                # Verify return statement preserves the exact same object/value
                assert result == expected_result
                assert type(result) == type(expected_result)
                
                # Verify suffix logging occurred
                assert mock_log.call_count == 2
                suffix_call = mock_log.call_args_list[1][0][1]
                assert f"Finished return_different_types with result: {expected_result}" in suffix_call

    def test_autolog_sync_wrapper_with_custom_suffix_formatter(self):
        """Test suffix logging with custom suffix formatter."""
        def custom_suffix_formatter(function, result):
            return f"[SYNC-SUCCESS] {function.__name__} completed with output: {type(result).__name__}"

        class LoggerOwner(Mindtrace):
            pass

        def simple_function(value):
            """Simple function for testing custom formatter."""
            return {"processed": value}

        logger_owner = LoggerOwner()
        decorated_func = Mindtrace.autolog(
            self=logger_owner,
            suffix_formatter=custom_suffix_formatter
        )(simple_function)
        
        with patch.object(logger_owner.logger, 'log') as mock_log:
            result = decorated_func("test_value")
            
            # Verify return statement returns correct result
            assert result == {"processed": "test_value"}
            
            # Verify suffix logging used custom formatter
            assert mock_log.call_count == 2
            suffix_call = mock_log.call_args_list[1][0][1]
            assert "[SYNC-SUCCESS] simple_function completed with output: dict" in suffix_call

    def test_autolog_sync_wrapper_with_function_that_returns_large_objects(self):
        """Test success branch with functions that return large/complex objects."""
        class LoggerOwner(Mindtrace):
            pass

        def create_large_object():
            """Function that returns a large, complex object."""
            return {
                "data": list(range(100)),
                "metadata": {
                    "created_by": "test_function",
                    "timestamps": {"start": 1234567890, "end": 1234567899},
                    "nested": {
                        "level1": {
                            "level2": {
                                "level3": "deep_value"
                            }
                        }
                    }
                },
                "items": [{"id": i, "value": f"item_{i}"} for i in range(10)]
            }

        logger_owner = LoggerOwner()
        decorated_func = Mindtrace.autolog(self=logger_owner)(create_large_object)
        
        with patch.object(logger_owner.logger, 'log') as mock_log:
            result = decorated_func()
            
            # Verify return statement returns the complete object
            assert len(result["data"]) == 100
            assert result["metadata"]["nested"]["level1"]["level2"]["level3"] == "deep_value"
            assert len(result["items"]) == 10
            assert result["items"][5]["value"] == "item_5"
            
            # Verify suffix logging handles large objects
            assert mock_log.call_count == 2
            suffix_call = mock_log.call_args_list[1][0][1]
            assert "Finished create_large_object with result:" in suffix_call

    def test_autolog_sync_wrapper_execution_order(self):
        """Test that suffix logging and return execute in correct order after successful function completion."""
        class LoggerOwner(Mindtrace):
            pass

        execution_order = []
        
        def tracked_function(value):
            """Function that tracks execution order."""
            execution_order.append("function_start")
            result = value * 2
            execution_order.append("function_end")
            return result

        logger_owner = LoggerOwner()
        
        # Create custom formatters to track execution order
        def tracking_prefix_formatter(func, args, kwargs):
            execution_order.append("prefix_log")
            return f"Starting {func.__name__}"
            
        def tracking_suffix_formatter(func, result):
            execution_order.append("suffix_log")  # This should happen during suffix logging
            return f"Finished {func.__name__}"

        decorated_func = Mindtrace.autolog(
            self=logger_owner,
            prefix_formatter=tracking_prefix_formatter,
            suffix_formatter=tracking_suffix_formatter
        )(tracked_function)
        
        with patch.object(logger_owner.logger, 'log') as mock_log:
            execution_order.clear()
            result = decorated_func(5)
            
            # Verify return statement returned correct result
            assert result == 10
            
            # Verify execution order: prefix -> function -> suffix -> return
            expected_order = ["prefix_log", "function_start", "function_end", "suffix_log"]
            assert execution_order == expected_order
            
            # Verify logging was called in correct order
            assert mock_log.call_count == 2

    def test_autolog_sync_wrapper_with_external_self_vs_internal_self(self):
        """Test that external self is used for logging, not any self from function args."""
        class LoggerOwner(Mindtrace):
            pass
        
        class DummySelf:
            """A dummy object that might be passed as 'self' to the function."""
            def __init__(self):
                self.name = "dummy"

        def function_with_self_param(self, value):
            """Function that takes 'self' as first parameter."""
            return f"{self.name}: {value}"

        logger_owner = LoggerOwner()
        dummy_self = DummySelf()
        
        decorated_func = Mindtrace.autolog(self=logger_owner)(function_with_self_param)
        
        with patch.object(logger_owner.logger, 'log') as mock_log:
            # Call with dummy_self as first argument
            result = decorated_func(dummy_self, "test_value")
            
            # Verify return statement returned correct result
            assert result == "dummy: test_value"
            
            # Verify logging was called with the external logger_owner's logger
            assert mock_log.call_count == 2
            # The external self's logger should be used for all logging
            mock_log.assert_called()  # Verify it was called

    def test_autolog_sync_wrapper_with_zero_arguments_function(self):
        """Test success branch with a function that takes no arguments."""
        class LoggerOwner(Mindtrace):
            pass

        def no_args_function():
            """Function with no arguments."""
            return "no_args_result"

        logger_owner = LoggerOwner()
        decorated_func = Mindtrace.autolog(self=logger_owner)(no_args_function)
        
        with patch.object(logger_owner.logger, 'log') as mock_log:
            result = decorated_func()
            
            # Verify return statement returned correct result
            assert result == "no_args_result"
            
            # Verify suffix logging works correctly with empty args/kwargs
            assert mock_log.call_count == 2
            
            prefix_call = mock_log.call_args_list[0][0][1]
            assert "with args: ()" in prefix_call
            assert "kwargs: {}" in prefix_call
            
            suffix_call = mock_log.call_args_list[1][0][1]
            assert "Finished no_args_function with result: no_args_result" in suffix_call 