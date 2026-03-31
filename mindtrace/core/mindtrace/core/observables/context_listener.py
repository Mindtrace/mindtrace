import logging
from typing import Any

from mindtrace.core import Mindtrace


class ContextListener(Mindtrace):
    """A context listener that can subscribe to a ObservableContext.

    The ContextListener class provides two main benefits:

    1. Deriving from Mindtrace, it provides for uniform logging of events.

    Example:
    ```python

    from mindtrace.core import ContextListener, Logger

    class MyListener(ContextListener):
        def x_changed(self, source, old, new):
            self.logger.info(f"x changed: {old} → {new}")  # Uses Mindtrace logging by default

    my_listener = MyListener(logger=Logger("MyListener"))  # May pass in a custom logger
    ```

    2. The default ContextListener can be used to automatically log changes to variables.

    Example:
    ```python
    from mindtrace.core import ContextListener, ObservableContext

    @ObservableContext(vars={"x": int, "y": int})
    class MyContext:
        def __init__(self):
            self.x = 0
            self.y = 0

    my_context = MyContext()
    my_context.subscribe(ContextListener(autolog=["x", "y"]))

    my_context.x = 1
    my_context.y = 2

    # Logs:
    # [MyContext] x changed: 0 → 1
    # [MyContext] y changed: 0 → 2
    ```
    """

    def __init__(self, autolog: list[str] | None = None, log_level: int = logging.ERROR, logger: Any = None, **kwargs):
        """Initialize the context listener.

        Args:
            autolog: A list of variables to log automatically.
            log_level: The log level to use for the logger.
        """
        super().__init__(**kwargs)

        if logger is not None:
            self.logger = logger

        if autolog is not None:
            for var in autolog:
                method_name = f"{var}_changed"

                # Only attach if the child class hasn't already defined it
                if not hasattr(self, method_name):
                    # Use a factory to capture var correctly in loop
                    setattr(self, method_name, self._make_auto_logger(var, log_level))

    def _make_auto_logger(self, varname: str, log_level: int):
        def _logger(source: str, old: Any, new: Any):
            self.logger.log(log_level, f"[{source}] {varname} changed: {old} → {new}")

        return _logger
