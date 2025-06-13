import logging
import os
import structlog
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from mindtrace.core.utils import ifnone
from mindtrace.core.config import Config
from mindtrace.services.logging.request_filter import RequestFilter



def filter_logs(logger: logging.Logger, method_name: str, event_dict: dict[str, any]) -> dict[str, any]:
    """
    Structlog processor to clean log entries by removing unnecessary fields.

    Args:
        logger : The logger instance.
        method_name : The logging method name (e.g., 'info', 'debug').
        event_dict : The log event dictionary.

    Returns:
        dict[str, any]: The cleaned event dictionary with redundant keys removed.
    """
    keys_to_remove = {
        "level",
        "logger",
        "timestamp",
    }
    for key in keys_to_remove:
        event_dict.pop(key, None)

    return event_dict


class ServiceLogMixin:
    """
    A mixin that enhances an existing `self.logger` with structlog wrapping
    for structured logging support.

    This is typically used in service or job classes that derive from a base
    like `Mindtrace`, which provides a logger. The mixin adds structured logging
    to the existing logger.

    Example:
        .. code-block:: python

            from mindtrace.core.base.mindtrace_base import Mindtrace
            from mindtrace.services.logging.logger import ServiceLogMixin


            class MyService(Mindtrace, ServiceLogMixin):
                def __init__(self):
                    super().__init__()
                    self.logger = self.setup_struct_logger(service_name="my_service")

                def run(self):
                    self.logger.info("Service started", component="my_service")

        .. note::
            This mixin expects `self.logger` to be already defined or configured in the parent class
            before invoking structlog enhancements.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, "logger"):
            raise AttributeError("ServiceLogMixin requires 'self.logger' to be defined in the parent class.")

    def setup_struct_logger(
        self,
        log_dir: str | None = None,
        log_level: int = logging.DEBUG,
        service_name: str = "",
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ) -> logging.Logger | structlog.stdlib.BoundLogger:
        """
        Sets up logging configuration for a specific service using structlog and RotatingFileHandler.

        If no `log_dir` is provided, logs are stored in `~/.cache/mindtrace/logs/{service_name}_{YYYYMMDD}.log`.

        Args:
            log_dir : Custom directory for logs. Defaults to user cache under `.cache/mindtrace/logs/`.
            log_level : Logging level (e.g., logging.DEBUG, logging.INFO).
            service_name : Name of the service for log naming and tagging.
            max_bytes : Maximum size in bytes before rotating the log file.
            backup_count : Number of rotated log files to keep.

        Returns:
            structlog.stdlib.BoundLogger: A structlog-wrapped logger instance for structured logging.

        Raises:
            OSError: If the log directory cannot be created.
        """

        def add_service_name(logger, method_name, event_dict):
            event_dict["service"] = service_name
            return event_dict

        # Setup default log path if not provided
        default_config = Config()
        default_log_dir = os.path.join(default_config.get('LOGGER').get('LOG_DIR'), "services", service_name)
        log_dir = Path(ifnone(log_dir, default_log_dir))
        log_dir.mkdir(parents=True, exist_ok=True)

        # Generate timestamped log filename
        timestamp = datetime.now().strftime("%Y%m%d")
        log_file = log_dir / f"{service_name}_{timestamp}.log"

        # Prevent double propagation of logs
        logging.getLogger("urllib3").propagate = False
        logging.getLogger("requests").propagate = False

        # Setup file handler
        logger = logging.getLogger(service_name)
        logger.handlers.clear()
        logger.setLevel(log_level)

        file_handler = RotatingFileHandler(str(log_file), mode="w", maxBytes=max_bytes, backupCount=backup_count)
        file_handler.addFilter(RequestFilter())
        file_handler.setFormatter(logging.Formatter("%(asctime)s:%(levelname)s:%(message)s"))
        logger.addHandler(file_handler)

        # Configure structlog
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.filter_by_level,
                filter_logs,
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                add_service_name,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        return structlog.wrap_logger(logger)