import logging
import os
from collections import OrderedDict
from logging import Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import structlog

from mindtrace.core.config import CoreSettings
from mindtrace.core.utils import ifnone


def default_formatter(fmt: Optional[str] = None) -> logging.Formatter:
    """Returns a logging formatter with a default format if none is specified."""
    default_fmt = "[%(asctime)s] %(levelname)s: %(name)s: %(message)s"
    return logging.Formatter(fmt or default_fmt)


def setup_logger(
    name: str = "mindtrace",
    *,
    log_dir: Optional[Path] = None,
    logger_level: int = logging.DEBUG,
    stream_level: int = logging.ERROR,
    add_stream_handler: bool = True,
    file_level: int = logging.DEBUG,
    file_mode: str = "a",
    add_file_handler: bool = True,
    propagate: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    use_structlog: Optional[bool] = None,
    structlog_json: Optional[bool] = True,
    structlog_pre_chain: Optional[list] = None,
    structlog_processors: Optional[list] = None,
    structlog_renderer: Optional[object] = None,
    structlog_bind: Optional[object] = None,
) -> Logger | structlog.BoundLogger:
    """Configure and initialize logging for Mindtrace components programmatically.

    Sets up a rotating file handler and a console handler on the given logger.
    Log file defaults to ~/.cache/mindtrace/{name}.log.

    Args:
        name: Logger name, defaults to "mindtrace".
        log_dir: Custom directory for log file.
        logger_level: Overall logger level.
        stream_level: StreamHandler level (e.g., ERROR).
        add_stream_handler: Whether to add a stream handler.
        file_level: FileHandler level (e.g., DEBUG).
        file_mode: Mode for file handler, default is 'a' (append).
        add_file_handler: Whether to add a file handler.
        propagate: Whether the logger should propagate messages to ancestor loggers.
        max_bytes: Maximum size in bytes before rotating log file.
        backup_count: Number of backup files to retain.
        use_structlog: Optional bool. If True, configure and return a structlog BoundLogger.
        structlog_json: Optional bool. If True, render JSON; otherwise use console/dev renderer.
        structlog_pre_chain: Optional list of pre-processors for stdlib log records.
        structlog_processors: Optional list of processors after pre_chain (before render).
        structlog_renderer: Optional custom renderer processor. Overrides `structlog_json`.
        structlog_bind: Optional dict or callable(name)->dict to bind fields.

    Returns:
        Logger | structlog.BoundLogger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logger_level)
    logger.propagate = propagate

    # Get config
    default_config = CoreSettings()
    use_structlog = ifnone(use_structlog, default_config.MINDTRACE_LOGGER.USE_STRUCTLOG)

    # Determine log file path
    if name == "mindtrace":
        child_log_path = f"{name}.log"
    else:
        child_log_path = os.path.join("modules", f"{name}.log")

    if log_dir:
        log_file_path = os.path.join(log_dir, child_log_path)
    else:
        if use_structlog:
            log_file_path = os.path.join(default_config.MINDTRACE_DIR_PATHS.STRUCT_LOGGER_DIR, child_log_path)
        else:
            log_file_path = os.path.join(default_config.MINDTRACE_DIR_PATHS.LOGGER_DIR, child_log_path)

    os.makedirs(Path(log_file_path).parent, exist_ok=True)

    if not use_structlog:
        # Standard logging setup
        if add_stream_handler:
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(stream_level)
            stream_handler.setFormatter(default_formatter())
            logger.addHandler(stream_handler)

        if add_file_handler:
            file_handler = RotatingFileHandler(
                filename=str(log_file_path), maxBytes=max_bytes, backupCount=backup_count, mode=file_mode
            )
            file_handler.setLevel(file_level)
            file_handler.setFormatter(default_formatter())
            logger.addHandler(file_handler)

        return logger

    pre_chain = (
        list(structlog_pre_chain)
        if structlog_pre_chain is not None
        else [
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="ISO"),
        ]
    )

    renderer = (
        structlog_renderer
        if structlog_renderer is not None
        else (structlog.processors.JSONRenderer() if structlog_json else structlog.dev.ConsoleRenderer())
    )

    processors = (
        list(structlog_processors)
        if structlog_processors is not None
        else [
            structlog.stdlib.filter_by_level,
            getattr(structlog.contextvars, "merge_contextvars", None)
            or (lambda logger, method_name, event_dict: event_dict),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _enforce_key_order_processor(
                [
                    "timestamp",
                    "event",
                    "service",
                    "duration_ms",
                    "metrics",
                    "level",
                    "logger",
                ]
            ),
            renderer,
        ]
    )

    # Configure structlog with proper processors
    structlog.configure(
        processors=pre_chain + processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Set up handlers on the underlying stdlib logger
    stdlib_logger = logging.getLogger(name)
    stdlib_logger.handlers.clear()
    stdlib_logger.setLevel(logger_level)
    stdlib_logger.propagate = propagate

    # Add stream handler
    if add_stream_handler:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(stream_level)
        # Use JSON renderer for pure JSON output without prefix
        stream_handler.setFormatter(logging.Formatter("%(message)s"))
        stdlib_logger.addHandler(stream_handler)

    # Add file handler
    if add_file_handler:
        file_handler = RotatingFileHandler(
            filename=str(log_file_path), maxBytes=max_bytes, backupCount=backup_count, mode=file_mode
        )
        file_handler.setLevel(file_level)
        # Use JSON renderer for pure JSON output without prefix
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        stdlib_logger.addHandler(file_handler)

    # Get the bound logger
    bound_logger = structlog.get_logger(name)
    if structlog_bind is not None:
        try:
            bind_dict = structlog_bind(name) if callable(structlog_bind) else dict(structlog_bind)
        except Exception:
            bind_dict = {}
        if bind_dict:
            bound_logger = bound_logger.bind(**bind_dict)

    return bound_logger


def _enforce_key_order_processor(key_order: list[str]):
    def _processor(_logger, _method_name, event_dict):
        ordered = OrderedDict()
        for key in key_order:
            if key in event_dict:
                ordered[key] = event_dict.pop(key)
        for k in sorted(event_dict.keys()):
            ordered[k] = event_dict[k]
        return ordered

    return _processor


def get_logger(
    name: str | None = "mindtrace", use_structlog: bool | None = None, **kwargs
) -> logging.Logger | structlog.BoundLogger:
    """
    Create or retrieve a named logger instance.

    This function wraps Python's built-in ``logging.getLogger()`` to provide a
    standardized logger for Mindtrace components. If the logger with the given
    name already exists, it returns the existing instance; otherwise, it creates
    a new one with optional configuration overrides.

    Args:
        name (str): The name of the logger. Defaults to "mindtrace".
        use_structlog (bool): Whether to use structured logging. If None, uses config default.
        **kwargs: Additional keyword arguments to be passed to `setup_logger`.

    Returns:
        logging.Logger | structlog.BoundLogger: A configured logger instance.

    Example:
        .. code-block:: python

            from mindtrace.core.logging.logger import get_logger

            logger = get_logger("core.module")
            logger.info("Logger configured with custom settings.")

            slogger = get_logger(
                "core.module",
                use_structlog=True,
                structlog_bind={"service": "my-service"},
            )
            slogger.info("Structured log", user_id="123")
    """
    if not name:
        name = "mindtrace"

    full_name = name if name.startswith("mindtrace") else f"mindtrace.{name}"
    kwargs.setdefault("propagate", True)

    default_config = CoreSettings()
    use_structlog = ifnone(use_structlog, default_config.MINDTRACE_LOGGER.USE_STRUCTLOG)

    if kwargs.get("propagate"):
        parts = full_name.split(".") if "." in full_name else [full_name]
        parent_name = parts[0]
        parent_logger = logging.getLogger(parent_name)
        if parent_logger.handlers:
            setup_logger(parent_name, add_stream_handler=False, use_structlog=use_structlog, **kwargs)
        for part in parts[1:-1]:
            parent_name = f"{parent_name}.{part}"
            parent_logger = logging.getLogger(parent_name)
            if parent_logger.handlers:
                setup_logger(parent_name, add_stream_handler=False, use_structlog=use_structlog, **kwargs)
    return setup_logger(full_name, use_structlog=use_structlog, **kwargs)
