"""Request filtering module for logging.

This module provides a custom logging filter that can be used to filter out unwanted request logs
based on predefined paths. It's particularly useful for filtering out common noise in web application
logs like favicon requests and documentation endpoints.
"""

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

        This method checks if the log record contains a path that should be ignored.
        If the log message is not in JSON format or doesn't contain a path, it will
        be allowed to pass through. The method handles all exceptions gracefully by
        allowing the log to pass through (returning True) if any error occurs during
        processing.

        Args:
            record: Log record to filter.

        Returns:
            True if the record should be logged, False otherwise.

        Example:
            .. code-block:: python

                import logging
                from mindtrace.services.logging import RequestFilter

                # Create a logger
                logger = logging.getLogger("my_app")
                
                # Add the filter
                request_filter = RequestFilter(ignored_paths={"/health"})
                logger.addFilter(request_filter)

                # These logs will be filtered out
                logger.info('{"path": "/health", "status": 200}')
                logger.info('{"path": "/favicon.ico", "status": 404}')

                # This log will pass through
                logger.info('{"path": "/api/data", "status": 200}')

                # Non-JSON logs will also pass through
                logger.info("This is a regular log message")
        """
        try:
            log_dict = json.loads(record.getMessage())
            if "path" in log_dict and log_dict["path"] in self.ignored_paths:
                return False
            return True
        except Exception:
            return True