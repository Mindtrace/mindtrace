from collections import defaultdict
from typing import Callable, Dict, Union


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, Dict[str, Callable]] = defaultdict(dict)

    def subscribe(self, event_name: str, handler: Callable) -> str:
        handler_id = f"{id(handler)}"
        self._subscribers[event_name][handler_id] = handler
        return handler_id

    def unsubscribe(self, event_name: str, handler_or_id: Union[Callable, str]):
        subs = self._subscribers[event_name]
        if isinstance(handler_or_id, str):
            subs.pop(handler_or_id, None)
        else:
            for k, v in list(subs.items()):
                if v == handler_or_id:
                    subs.pop(k)

    def emit(self, event_name: str, **kwargs):
        for handler in self._subscribers[event_name].values():
            handler(**kwargs)
