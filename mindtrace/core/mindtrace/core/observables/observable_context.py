from functools import wraps
from typing import Any, Dict, List, Type

from mindtrace.core import EventBus


class ObservableContext:
    """A class decorator that allows listeners to subscribe to changes in the class properties.
    
    Example::

        from mindtrace.core import ContextListener, ObservableContext

        @ObservableContext(vars={"x": int, "y": int})
        class MyContext:
            def __init__(self):
                self.x = 0
                self.y = 0
                self.z = 0  # Not observable because it's not in the vars list

        my_context = MyContext()
        my_context.add_listener(ContextListener(autolog=["x", "y"]))
        # my_context.add_listener(ContextListener(autolog=["z"]))  # Raises ValueError

        my_context.x = 1
        my_context.y = 2

        # Logs:
        # [MyContext] x changed: 0 → 1
        # [MyContext] y changed: 0 → 2
    """

    def __init__(self, vars: List[str] | Dict[str, Type]):
        """Initialize the observable context.
        
        Args:
            vars: A list of variable names to be made observable, or a dictionary of variable names and their types.
        """
        self.vars = list(vars) if isinstance(vars, list) else list(vars.keys())

    def __call__(self, cls):
        cls._observable_vars = self.vars  # Attach observable vars to the class
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
            self._event_bus._observable_vars = self.__class__._observable_vars
            original_init(self, *args, **kwargs)

        def add_listener(self, listener: Any):
            """Add a listener to observe context variable changes.

            Args:
                listener: An object with a `context_updated` method and/or methods named `<var>_changed`.
            Raises:
                ValueError: If the listener subscribes to a variable not in the observable context.
            """
            if hasattr(listener, "context_updated"):
                self._listeners.append(listener)

            for attr in dir(listener):
                if attr.endswith("_changed") and callable(getattr(listener, attr)):
                    var = attr[:-8]
                    if var not in self.__class__._observable_vars:  # Use class attribute
                        raise ValueError(f"Listener cannot subscribe to unknown variable '{var}'")
                    self._event_bus.subscribe(f"{var}_changed", getattr(listener, attr))

        def remove_listener(self, listener: Any):
            """Remove a previously added listener.

            Args:
                listener: The listener object to remove.
            """
            if listener in self._listeners:
                self._listeners.remove(listener)

        def _notify_listeners(self, source: str, var: str, old: Any, new: Any):
            for l in self._listeners:
                if hasattr(l, "context_updated"):
                    l.context_updated(source, var, old, new)

        def set_context(self, **updates):
            """Set multiple observable variables at once.

            Args:
                **updates: Key-value pairs of variable names and their new values.
            """
            for key, value in updates.items():
                if hasattr(self.__class__, key):
                    setattr(self, key, value)

        def subscribe(self, event_name: str, handler: Callable):
            """Subscribe a handler to a specific event.

            Args:
                event_name (str): The name of the event to subscribe to.
                handler (callable): The function to call when the event is emitted.

            Returns:
                Any: The subscription ID or handler reference, depending on EventBus implementation.
            """
            return self._event_bus.subscribe(event_name, handler)

        def unsubscribe(self, event_name: str, handler_or_id: str | Callable):
            """Unsubscribe a handler or subscription ID from a specific event.

            Args:
                event_name (str): The name of the event.
                handler_or_id: The handler function or subscription ID to remove.
            """
            self._event_bus.unsubscribe(event_name, handler_or_id)

        cls.__init__ = new_init
        cls.add_listener = add_listener
        cls.remove_listener = remove_listener
        cls._notify_listeners = _notify_listeners
        cls.set_context = set_context
        cls.subscribe = subscribe
        cls.unsubscribe = unsubscribe
        return cls
