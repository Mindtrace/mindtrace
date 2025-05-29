import pytest

from mindtrace.core import EventBus


def test_eventbus_subscribe_emit():
    bus = EventBus()
    result = {}

    def handler(**kwargs):
        result.update(kwargs)

    bus.subscribe("test_event", handler)
    bus.emit("test_event", key="value")
    assert result == {"key": "value"}

def test_eventbus_unsubscribe_by_function():
    bus = EventBus()
    called = []

    def handler(**kwargs):
        called.append(True)

    bus.subscribe("event", handler)
    bus.emit("event")
    assert len(called) == 1

    bus.unsubscribe("event", handler)
    bus.emit("event")
    assert len(called) == 1

def test_eventbus_unsubscribe_by_id():
    bus = EventBus()
    called = []

    def handler(**kwargs):
        called.append(True)

    handler_id = bus.subscribe("event", handler)

    bus.emit("event")   
    assert len(called) == 1

    bus.unsubscribe("event", handler_id)
    bus.emit("event")
    assert len(called) == 1
