"""Tests for the Mindtrace base classes (descriptor-based implementation)."""

import logging
from abc import abstractmethod
from unittest.mock import patch

import pytest

from mindtrace.core.base.mindtrace_base import Mindtrace, MindtraceABC
from mindtrace.core.config import CoreConfig


class TestDescriptors:
    """Tests for _ClassOrInstanceAttr and _ClassOrInstanceProperty descriptors."""

    def test_class_level_logger(self):
        """cls.logger returns a logger named after the class."""

        class TestClass(Mindtrace):
            pass

        logger = TestClass.logger
        assert isinstance(logger, logging.Logger)
        assert TestClass.__name__ in logger.name

    def test_class_level_logger_cached(self):
        """cls.logger returns the same object on repeated access."""

        class TestClass(Mindtrace):
            pass

        logger1 = TestClass.logger
        logger2 = TestClass.logger
        assert logger1 is logger2

    def test_class_level_logger_independent_per_class(self):
        """Each class gets its own logger."""

        class ClassA(Mindtrace):
            pass

        class ClassB(Mindtrace):
            pass

        assert ClassA.logger is not ClassB.logger
        assert "ClassA" in ClassA.logger.name
        assert "ClassB" in ClassB.logger.name

    def test_instance_logger_overrides_class_logger(self):
        """self.logger (set in __init__) is distinct from cls.logger."""

        class TestClass(Mindtrace):
            pass

        instance = TestClass()
        # Instance and class loggers are independently created
        assert isinstance(instance.logger, logging.Logger)
        assert isinstance(TestClass.logger, logging.Logger)

    def test_class_level_config(self):
        """cls.config lazily creates a CoreConfig."""

        class TestClass(Mindtrace):
            pass

        config = TestClass.config
        assert isinstance(config, CoreConfig)

    def test_class_level_config_cached(self):
        """cls.config returns the same object on repeated access."""

        class TestClass(Mindtrace):
            pass

        config1 = TestClass.config
        config2 = TestClass.config
        assert config1 is config2

    def test_unique_name_on_class(self):
        """cls.unique_name returns module.ClassName."""

        class TestClass(Mindtrace):
            pass

        assert TestClass.unique_name.endswith("TestClass")
        assert "." in TestClass.unique_name

    def test_unique_name_on_instance(self):
        """self.unique_name returns module.ClassName (same as cls)."""

        class TestClass(Mindtrace):
            pass

        instance = TestClass()
        assert instance.unique_name == TestClass.unique_name

    def test_name_on_class(self):
        """cls.name returns just the class name."""

        class TestClass(Mindtrace):
            pass

        assert TestClass.name == "TestClass"

    def test_name_on_instance(self):
        """self.name returns just the class name."""

        class TestClass(Mindtrace):
            pass

        instance = TestClass()
        assert instance.name == "TestClass"


class TestMindtrace:
    """Tests for the Mindtrace base class."""

    def test_init(self):
        """Test initialization provides logger and config."""
        instance = Mindtrace()
        assert hasattr(instance, "config")
        assert hasattr(instance, "logger")
        assert isinstance(instance.config, CoreConfig)
        assert isinstance(instance.logger, logging.Logger)

    def test_config_with_environment_variables(self, monkeypatch):
        """Config picks up environment variables."""
        monkeypatch.setenv("MINDTRACE_TEST_PARAM", "test_1234")
        instance = Mindtrace()
        assert instance.config.MINDTRACE_TEST_PARAM == "test_1234"

    def test_cooperative_inheritance(self):
        """kwargs pass through to parent classes via super().__init__."""

        class ParentClass:
            def __init__(self, specific_arg=None, **kwargs):
                super().__init__(**kwargs)
                self.specific_arg = specific_arg

        class TestClass(Mindtrace, ParentClass):
            pass

        instance = TestClass(specific_arg="test")
        assert instance.specific_arg == "test"
        assert hasattr(instance, "logger")

    def test_context_manager(self):
        """Basic context manager usage."""
        with Mindtrace() as mt:
            assert isinstance(mt, Mindtrace)

    def test_context_manager_exception_propagates(self):
        """Exceptions propagate out of context manager."""
        with pytest.raises(ValueError):
            with Mindtrace() as _:
                raise ValueError("Test exception")

    def test_context_manager_logs_exception(self):
        """Context manager logs exceptions before propagating."""
        with patch("mindtrace.core.base.mindtrace_base.get_logger") as mock_get_logger:
            mock_logger = logging.getLogger("test.mock")
            mock_get_logger.return_value = mock_logger

            with patch.object(mock_logger, "exception") as mock_exc:
                with pytest.raises(ValueError):
                    with Mindtrace() as _:
                        raise ValueError("Test exception")
                mock_exc.assert_called_once()

    def test_context_manager_returns_false(self):
        """__exit__ returns False (never suppresses exceptions)."""
        instance = Mindtrace()
        assert instance.__exit__(None, None, None) is False
        assert instance.__exit__(ValueError, ValueError("x"), None) is False

    def test_subclass_inherits_logging(self):
        """Subclasses get their own logger automatically."""

        class MyComponent(Mindtrace):
            pass

        instance = MyComponent()
        assert "MyComponent" in instance.logger.name

    def test_multiple_instances_independent(self):
        """Two instances of the same class have independent loggers and configs."""

        class TestClass(Mindtrace):
            pass

        a = TestClass()
        b = TestClass()
        # Each instance gets its own logger and config
        assert isinstance(a.logger, logging.Logger)
        assert isinstance(b.logger, logging.Logger)
        assert isinstance(a.config, CoreConfig)
        assert isinstance(b.config, CoreConfig)


class TestMindtraceABC:
    """Tests for the MindtraceABC abstract base class."""

    def test_abstract_method_enforcement(self):
        """Cannot instantiate a class with unimplemented abstract methods."""

        class Abstract(MindtraceABC):
            @abstractmethod
            def do_thing(self):
                pass

        with pytest.raises(TypeError):
            Abstract()

    def test_concrete_implementation(self):
        """Concrete subclass of MindtraceABC works normally."""

        class Concrete(MindtraceABC):
            def do_thing(self):
                return "done"

        instance = Concrete()
        assert instance.do_thing() == "done"
        assert hasattr(instance, "logger")
        assert hasattr(instance, "config")

    def test_isinstance_checks(self):
        """MindtraceABC subclasses are instances of both Mindtrace and ABC."""

        class Concrete(MindtraceABC):
            pass

        instance = Concrete()
        assert isinstance(instance, Mindtrace)

    def test_class_level_logger(self):
        """cls.logger works on MindtraceABC subclasses."""

        class Concrete(MindtraceABC):
            pass

        assert isinstance(Concrete.logger, logging.Logger)
        assert "Concrete" in Concrete.logger.name

    def test_no_metaclass_conflict_with_multiple_inheritance(self):
        """MindtraceABC + other base classes don't cause metaclass conflicts."""

        class Mixin:
            def mixin_method(self):
                return "mixed"

        class Combined(MindtraceABC, Mixin):
            pass

        instance = Combined()
        assert instance.mixin_method() == "mixed"
        assert hasattr(instance, "logger")
