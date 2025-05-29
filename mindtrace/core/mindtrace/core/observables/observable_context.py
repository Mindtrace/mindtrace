from functools import wraps
from typing import Dict, Type

from mindtrace.core import EventBus


class ObservableContext:
    def __init__(self, vars: Dict[str, Type]):
        self.vars = vars

    def __call__(self, cls):
        for var_name in self.vars:
            private_name = f"_{var_name}"

            def getter(self, name=private_name):
                return getattr(self, name, None)

            def setter(self, value, name=private_name, var=var_name):
                old = getattr(self, name, None)
                setattr(self, name, value)
                if old != value:
                    self._notify_listeners(source=self.__class__.__name__, var=var, old=old, new=value)
                    self._event_bus.emit(
                        "context_updated", source=self.__class__.__name__, var=var, old=old, new=value)
                    self._event_bus.emit(f"{var}_changed", source=self.__class__.__name__, old=old, new=value)

            setattr(cls, var_name, property(getter, setter))

        original_init = cls.__init__

        @wraps(original_init)
        def new_init(self, *args, **kwargs):
            self._listeners = []
            self._event_bus = EventBus()
            original_init(self, *args, **kwargs)

        def add_listener(self, listener):
            if hasattr(listener, "context_updated"):
                self._listeners.append(listener)

            for attr in dir(listener):
                if attr.endswith("_changed") and callable(getattr(listener, attr)):
                    var = attr[:-8]
                    self._event_bus.subscribe(f"{var}_changed", getattr(listener, attr))

        def remove_listener(self, listener):
            if listener in self._listeners:
                self._listeners.remove(listener)

        def _notify_listeners(self, source, var, old, new):
            for l in self._listeners:
                if hasattr(l, "context_updated"):
                    l.context_updated(source, var, old, new)

        def set_context(self, **updates):
            for key, value in updates.items():
                if hasattr(self.__class__, key):
                    setattr(self, key, value)

        def subscribe(self, event_name, handler):
            return self._event_bus.subscribe(event_name, handler)

        def unsubscribe(self, event_name, handler_or_id):
            self._event_bus.unsubscribe(event_name, handler_or_id)

        cls.__init__ = new_init
        cls.add_listener = add_listener
        cls.remove_listener = remove_listener
        cls._notify_listeners = _notify_listeners
        cls.set_context = set_context
        cls.subscribe = subscribe
        cls.unsubscribe = unsubscribe
        return cls
