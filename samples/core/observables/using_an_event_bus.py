from mindtrace.core import EventBus


class Source:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus

    def emit(self):
        self.event_bus.emit(event_name="event", data={"key": "value"})


class Listener:
    def __init__(self, event_bus: EventBus):
        event_bus.subscribe(self.on_event, "event")

    def on_event(self, **kwargs):
        print(f"Received event: {kwargs}")


event_bus = EventBus()
source = Source(event_bus)
listener = Listener(event_bus)

source.emit()


# Output:
# Received event: {'data': {'key': 'value'}}
