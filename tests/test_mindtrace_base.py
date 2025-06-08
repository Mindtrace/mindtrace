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
        assert TestClass.logger.name == TestClass.unique_name


class TestMindtrace:
    """Tests for the Mindtrace base class."""

    def test_init(self):
        """Test initialization of Mindtrace class."""
        instance = Mindtrace()
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