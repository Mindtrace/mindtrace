import json
import logging

from mindtrace.core.utils import ifnone


class RequestFilter(logging.Filter):
    """Filter to remove unwanted request logs based on predefined ignored paths."""

    default_ignored_paths = {"/favicon.ico", "/docs", "/openapi.json"}

    def __init__(self, ignored_paths=None):
        """Initialize the RequestFilter with customizable ignored paths.

        Args:
            ignored_paths: Paths to be ignored. If None, it will use default paths.
        """
        super().__init__()
        self.ignored_paths = ifnone(ignored_paths, default=RequestFilter.default_ignored_paths)

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter out logs matching the ignored paths.

        Args:
            record: Log record to filter.

        Returns:
            True if the record should be logged, False otherwise.
        """
        try:
            log_dict = json.loads(record.getMessage())
            if "path" in log_dict and log_dict["path"] in self.ignored_paths:
                return False
            return True
        except Exception:
            return True