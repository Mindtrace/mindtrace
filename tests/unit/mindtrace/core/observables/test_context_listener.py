"""Unit test methods for mindtrace.core.observables.context_listener module."""

from unittest.mock import MagicMock

import pytest

from mindtrace.core import ContextListener, ObservableContext


@ObservableContext(vars={"x": int, "y": int})
class Example:
    def __init__(self):
        self.x = 0
        self.y = 0


def test_auto_logger_for_watched_var():
    obj = Example()
    listener = ContextListener(autolog=["x"])
    listener.logger = MagicMock()
    obj.add_listener(listener)

    obj.x = 42

    assert listener.logger.log.call_count == 1
    assert "x changed: 0 → 42" in listener.logger.log.call_args[0][-1]

def test_custom_var_method_overrides_autolog():
    obj = Example()

    class MyListener(ContextListener):
        def __init__(self):
            super().__init__(autolog=["x"])
        def x_changed(self, source, old, new):
            self.logger.debug(f"x manually handled: {old} → {new}")

    listener = MyListener()
    listener.logger = MagicMock()
    obj.add_listener(listener)
    obj.x = 5

    assert listener.logger.debug.call_count == 1
    assert "x manually handled: 0 → 5" in listener.logger.debug.call_args[0][-1]
