from abc import abstractmethod
import logging
from typing import Any

from mindtrace.core import ifnone, Mindtrace


class ContextListener(Mindtrace):
    def __init__(self, autolog: list[str] = None, log_level: int = logging.ERROR, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
