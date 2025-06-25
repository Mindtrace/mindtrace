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