"""Unit test methods for mindtrace.core.observables.observable_context module."""

import pytest

from mindtrace.core import ContextListener, ObservableContext


@ObservableContext(vars="x")
class ExampleStr:
    def __init__(self):
        self.x = 0


@pytest.fixture
def example_str():
    return ExampleStr()


@ObservableContext(vars=["x", "y"])
class ExampleList:
    def __init__(self):
        self.x = 0
        self.y = 0


@pytest.fixture
def example_list():
    return ExampleList()


@ObservableContext(vars={"x": int, "y": int})
class ExampleDict:
    def __init__(self):
        self.x = 0
        self.y = 0


@pytest.fixture
def example_dict():
    return ExampleDict()


def test_vars_as_str(example_str):
    assert example_str.x == 0


def test_vars_as_list(example_list):
    assert example_list.x == 0
    assert example_list.y == 0


def test_vars_as_dict(example_dict):
    assert example_dict.x == 0
    assert example_dict.y == 0


def test_raise_error_if_vars_is_not_str_list_or_dict():
    with pytest.raises(
        ValueError,
        match="Invalid vars argument: 42, vars must be a str variable name, list of variable names "
        "or a dictionary of variable names and their types.",
    ):

        @ObservableContext(vars=42)  # type: ignore
        class Example:
            pass


def test_context_listener_called(example_dict):
    results = []

    class Listener:
        def context_updated(self, source, var, old, new):
            results.append((var, old, new))

    example_dict.subscribe(Listener())
    example_dict.x = 1
    example_dict.y = 2
    assert example_dict.x == 1
    assert results == [("x", 0, 1), ("y", 0, 2)]


def test_specific_variable_handler(example_dict):
    results = []

    class Listener:
        def x_changed(self, source, old, new):
            results.append(("x", old, new))

    example_dict.subscribe(Listener())
    example_dict.x = 5
    assert results == [("x", 0, 5)]


def test_function_subscription(example_dict):
    called = []

    def handler(source, old, new):
        called.append((old, new))

    example_dict.subscribe(handler, "x_changed")
    example_dict.x = 10
    assert called == [(0, 10)]

    example_dict.unsubscribe(handler, "x_changed")
    example_dict.x = 20
    assert called == [(0, 10)]


def test_raise_error_if_subscribe_with_invalid_args(example_dict):
    with pytest.raises(ValueError):
        example_dict.subscribe("42")


def test_unsubscribe(example_dict):
    log = []

    class TestListener:
        def context_updated(self, source, var, old, new):
            log.append((var, old, new))

        def x_changed(self, source, old, new):
            log.append((source, old, new))

    listener = TestListener()
    example_dict.subscribe(listener)
    example_dict.x = 1
    assert ("x", 0, 1) in log and ("ExampleDict", 0, 1) in log

    example_dict.unsubscribe(listener)
    example_dict.x = 2
    assert ("x", 0, 1) in log and ("ExampleDict", 0, 1) in log


def test_unsubscribe_with_invalid_args(example_dict):
    with pytest.raises(ValueError):
        example_dict.unsubscribe("not a listener")


def test_listener_cannot_subscribe_to_unknown_variable(example_dict):
    """Assert that an error is raised if a listener tries to subscribe to a non-observable variable."""

    class GoodListener:
        def just_a_method(self, source, old, new):  # Not a reserved event name.
            pass

        def context_updated(self, source, var, old, new):  # Still needs to subscribe to at least one event.
            pass

    class BadListener:
        def z_changed(self, source, old, new):  # "{var}_changed" is a reserved event name.
            pass

    example_dict.subscribe(GoodListener())  # Should succeed

    with pytest.raises(ValueError, match="Listener cannot subscribe to unknown variable 'z'"):
        example_dict.subscribe(BadListener())

    with pytest.raises(ValueError, match="Listener cannot subscribe to unknown variable 'z'"):
        example_dict.subscribe(ContextListener(autolog=["z"]))
