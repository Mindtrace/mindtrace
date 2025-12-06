import uuid
from collections import defaultdict
from typing import Callable, Dict, Union


class EventBus:
    """A simple event bus that allows for subscribing to and emitting events.

    Example:
    ```python
    from mindtrace.core import EventBus

    bus = EventBus()

    def handler(**kwargs):
        print(kwargs)

    bus.subscribe("event", handler)
    bus.emit("event", x="1", y="2")

    # Output:
    # {'x': '1', 'y': '2'}

    bus.unsubscribe("event", handler)
    bus.emit("event", x="1", y="2")
    ```
        # Output:
        # No output
    """

    def __init__(self):
        """Initialize the event bus."""
        self._subscribers: Dict[str, Dict[str, Callable]] = defaultdict(dict)

    def subscribe(self, handler: Callable, event_name: str) -> str:
        """Subscribe to an event.

        Args:
            handler: The handler to call when the event is emitted.
            event_name: The name of the event to subscribe to.

        Returns:
            The handler ID.
        """
        handler_id = str(uuid.uuid4())
        self._subscribers[event_name][handler_id] = handler
        return handler_id

    def unsubscribe(self, handler_or_id: Union[Callable, str], event_name: str):
        """Unsubscribe from an event.

        Args:
            handler_or_id: The handler or ID to unsubscribe from.
            event_name: The name of the event to unsubscribe from.
        """
        subs = self._subscribers[event_name]
        if isinstance(handler_or_id, str):
            subs.pop(handler_or_id, None)
        else:
            for k, v in list(subs.items()):
                if v == handler_or_id:
                    subs.pop(k)

    def emit(self, event_name: str, **kwargs):
        """Emit an event.

        Args:
            event_name: The name of the event to emit.
            **kwargs: The keyword arguments to pass to the handlers.
        """
        for handler in self._subscribers[event_name].values():
            handler(**kwargs)
