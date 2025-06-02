from collections import defaultdict
from typing import Callable, Dict, Union
import uuid


class EventBus:
    """A simple event bus that allows for subscribing to and emitting events.
    
    Example::

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

        # Output:
        # No output
    """

    def __init__(self):
        """Initialize the event bus."""
        self._subscribers: Dict[str, Dict[str, Callable]] = defaultdict(dict)

    def subscribe(self, event_name: str, handler: Callable) -> str:
        """Subscribe to an event.
        
        Args:
            event_name: The name of the event to subscribe to.
            handler: The handler to call when the event is emitted.

        Returns:
            The handler ID.
        """
        handler_id = str(uuid.uuid4())
        self._subscribers[event_name][handler_id] = handler
        return handler_id

    def unsubscribe(self, event_name: str, handler_or_id: Union[Callable, str]):
        """Unsubscribe from an event.
        
        Args:
            event_name: The name of the event to unsubscribe from.
            handler_or_id: The handler or ID to unsubscribe from.
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
