from functools import wraps
from typing import Dict, List, Type

from mindtrace.core import EventBus


class ObservableContext:
    """A class decorator that allows listeners to subscribe to changes in the class properties.

    Example:
    ```python
    from mindtrace.core import ContextListener, ObservableContext

    @ObservableContext(vars={"x": int, "y": int})
    class MyContext:
        def __init__(self):
            self.x = 0
            self.y = 0
            self.z = 0  # Not observable because it's not in the vars list

    my_context = MyContext()
    my_context.subscribe(ContextListener(autolog=["x", "y"]))
    # my_context.subscribe(ContextListener(autolog=["z"]))  # Raises ValueError

    my_context.x = 1
    my_context.y = 2

    # Logs:
    # [MyContext] x changed: 0 → 1
    # [MyContext] y changed: 0 → 2
    ```
    """

    def __init__(self, vars: str | List[str] | Dict[str, Type]):
        """Initialize the observable context.

        Args:
            vars: A list of variable names to be made observable, or a dictionary of variable names and their types.
        """
        if isinstance(vars, str):
            self.vars = [vars]
        elif isinstance(vars, list):
            self.vars = vars
        elif isinstance(vars, dict):
            self.vars = list(vars.keys())
        else:
            raise ValueError(
                f"Invalid vars argument: {vars}, vars must be a str variable name, list of variable names "
                "or a dictionary of variable names and their types."
            )

    def __call__(self, cls):
        cls._observable_vars = self.vars
        for var_name in self.vars:
            private_name = f"_{var_name}"

            def getter(self, name=private_name):
                return getattr(self, name, None)

            def setter(self, value, name=private_name, var=var_name):
                old = getattr(self, name, None)
                setattr(self, name, value)
                if old != value:
                    self._event_bus.emit("context_updated", source=self.__class__.__name__, var=var, old=old, new=value)
                    self._event_bus.emit(f"{var}_changed", source=self.__class__.__name__, old=old, new=value)

            setattr(cls, var_name, property(getter, setter))

        original_init = cls.__init__

        @wraps(original_init)
        def new_init(self, *args, **kwargs):
            self._event_bus = EventBus()
            original_init(self, *args, **kwargs)

        def subscribe(self, target, event_name: str | None = None):
            """Register a handler or listener object for context events.

            - If `target` is a callable and `event_name` is provided, subscribes the callable to the event.
            - If `target` is an object, inspects it for `context_updated` and `{var}_changed` methods and subscribes them.

            Args:
                target: A callable or an object with `context_updated` and/or `{var}_changed` methods.
                event_name: The name of the event to subscribe to. May be omitted if the target is an object.

            Returns:
                Uuid: The subscription ID.
            """
            if callable(target) and event_name:
                return self._event_bus.subscribe(target, event_name)
            elif hasattr(target, "__class__"):
                num_subscriptions = 0
                if hasattr(target, "context_updated"):
                    self._event_bus.subscribe(target.context_updated, "context_updated")
                    num_subscriptions += 1
                for attr in dir(target):
                    if attr.endswith("_changed") and callable(getattr(target, attr)):
                        var = attr[:-8]
                        if var not in self.__class__._observable_vars:
                            raise ValueError(f"Listener cannot subscribe to unknown variable '{var}'")
                        self._event_bus.subscribe(getattr(target, attr), f"{var}_changed")
                        num_subscriptions += 1
                if num_subscriptions == 0:
                    raise ValueError(
                        "Listener did not subscribe to any observable variables. Must subscribe to at "
                        f"least one of: context_updated, {
                            ', '.join([f'{var}_changed' for var in self.__class__._observable_vars])
                        }."
                    )

        def unsubscribe(self, target, event_name: str | None = None):
            """Unsubscribe a handler or listener object from context events.

            Args:
                target: A callable or an object with `context_updated` and/or `{var}_changed` methods.
                event_name: The name of the event to unsubscribe from. May be omitted if the target is an object.

            - If `target` is a callable and `event_name` is provided, unsubscribes the callable from the event.
            - If `target` is an object, removes it from listeners and unsubscribes its `{var}_changed` methods.
            """
            unsubscribed = False
            if callable(target) and event_name:
                self._event_bus.unsubscribe(target, event_name)
                unsubscribed = True
            elif hasattr(target, "__class__"):
                if hasattr(target, "context_updated"):
                    self._event_bus.unsubscribe(target.context_updated, "context_updated")
                    unsubscribed = True
                for attr in dir(target):
                    if attr.endswith("_changed") and callable(getattr(target, attr)):
                        var = attr[:-8]
                        if var in self.__class__._observable_vars:
                            self._event_bus.unsubscribe(getattr(target, attr), f"{var}_changed")
                            unsubscribed = True
            if not unsubscribed:
                raise ValueError("Subscription not found, unable to unsubscribe.")

        cls.__init__ = new_init
        cls.subscribe = subscribe
        cls.unsubscribe = unsubscribe
        return cls
