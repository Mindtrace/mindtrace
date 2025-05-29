"""Unit test methods for mindtrace.core.observables.observable_context module."""

import pytest

from mindtrace.core import ObservableContext


@ObservableContext(vars={"x": int, "y": int})
class Example:
    def __init__(self):
        self.x = 0
        self.y = 0

@pytest.fixture
def example():
    return Example()

def test_context_listener_called(example):
    results = []

    class Listener:
        def context_updated(self, source, var, old, new):
            results.append((var, old, new))

    example.add_listener(Listener())
    example.x = 1
    example.y = 2
    assert example.x == 1
    assert results == [("x", 0, 1), ("y", 0, 2)]

def test_specific_variable_handler(example):
    results = []

    class Listener:
        def x_changed(self, source, old, new):
            results.append(("x", old, new))

    example.add_listener(Listener())
    example.x = 5
    assert results == [("x", 0, 5)]

def test_function_subscription(example):
    called = []

    def handler(source, old, new):
        called.append((old, new))

    example.subscribe("x_changed", handler)
    example.x = 10
    assert called == [(0, 10)]

    example.unsubscribe("x_changed", handler)
    example.x = 20
    assert called == [(0, 10)]

def test_remove_listener(example):
    log = []

    class TestListener:
        def context_updated(self, source, var, old, new):
            log.append((var, old, new))

    listener = TestListener()
    example.add_listener(listener)
    example.x = 1
    assert log == [("x", 0, 1)]

    example.remove_listener(listener)
    example.x = 2
    assert log == [("x", 0, 1)]

def test_set_context(example):
    example.set_context(x=42, y=99)
    assert example.x == 42
    assert example.y == 99

def test_set_context_with_partial_update(example):
    example.set_context(x=42)
    assert example.x == 42
    assert example.y == 0
