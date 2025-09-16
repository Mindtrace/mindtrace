import logging
import os
from logging import Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from mindtrace.core.config import Config
from mindtrace.core.utils import ifnone


def default_formatter(fmt: Optional[str] = None) -> logging.Formatter:
    """
    Returns a logging formatter with a default format if none is specified.
    """
    default_fmt = "[%(asctime)s] %(levelname)s: %(name)s: %(message)s"
    return logging.Formatter(fmt or default_fmt)


def setup_logger(
    name: str = "mindtrace",
    *,
    log_dir: Optional[Path] = None,
    logger_level: int = logging.DEBUG,
    stream_level: int = logging.ERROR,
    file_level: int = logging.DEBUG,
    file_mode: str = "a",
    propagate: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    use_structlog: Optional[bool] = None,
    structlog_json: Optional[bool] = None,
    structlog_pre_chain: Optional[list] = None,
    structlog_processors: Optional[list] = None,
    structlog_renderer: Optional[object] = None,
    structlog_bind: Optional[object] = None,
) -> Logger | object:
    """Configure and initialize logging for Mindtrace components programmatically.

    Sets up a rotating file handler and a console handler on the given logger.
    Log file defaults to ~/.cache/mindtrace/{name}.log.

    Args:
        name: Logger name, defaults to "mindtrace".
        log_dir: Custom directory for log file.
        logger_level: Overall logger level.
        stream_level: StreamHandler level (e.g., ERROR).
        file_level: FileHandler level (e.g., DEBUG).
        file_mode: Mode for file handler, default is 'a' (append).
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

    # Set up stream handler
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(stream_level)
    stream_handler.setFormatter(default_formatter())
    logger.addHandler(stream_handler)

    # Set up file handler
    default_config = Config()
    use_structlog = ifnone(use_structlog, default_config["MINDTRACE_LOGGER_USE_STRUCTLOG"])
    structlog_json = ifnone(structlog_json, default_config["MINDTRACE_LOGGER_USE_STRUCTLOG"])
    
    if name == "mindtrace":
        child_log_path = f"{name}.log"
    else:
        child_log_path = os.path.join("modules", f"{name}.log")

    if log_dir:
        log_file_path = os.path.join(log_dir, child_log_path)
    else:
        if use_structlog:
            log_file_path = os.path.join(default_config["MINDTRACE_LOGGER_STRUCTLOG_DIR"], child_log_path)
        else:
            log_file_path = os.path.join(default_config["MINDTRACE_LOGGER_DIR"], child_log_path)

    os.makedirs(Path(log_file_path).parent, exist_ok=True)
    file_handler = RotatingFileHandler(
        filename=str(log_file_path), maxBytes=max_bytes, backupCount=backup_count, mode=file_mode
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(default_formatter())
    logger.addHandler(file_handler)
    if not use_structlog:
        return logger


    try:
        import structlog
    except ImportError as e:
        raise ImportError(
            "structlog is not installed. Install it with 'pip install structlog' or disable use_structlog."
        ) from e

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

    chosen_formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=pre_chain,
        fmt="%(asctime)s,%(msecs)03d:%(levelname)s:%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    processors = (
        list(structlog_processors)
        if structlog_processors is not None
        else [
            structlog.stdlib.filter_by_level,
            getattr(structlog.contextvars, "merge_contextvars", None) or (lambda logger, method_name, event_dict: event_dict),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
    )

    structlog.configure(
        processors=pre_chain + processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Prepare the return bound logger (binding if requested)
    bound_logger = structlog.get_logger(name)
    if structlog_bind is not None:
        try:
            bind_dict = structlog_bind(name) if callable(structlog_bind) else dict(structlog_bind)
        except Exception:
            bind_dict = {}
        if bind_dict:
            bound_logger = bound_logger.bind(**bind_dict)

    # Ensure stdlib handlers render via structlog
    stream_handler.setFormatter(chosen_formatter)
    file_handler.setFormatter(chosen_formatter)

    # Return appropriate logger
    return bound_logger


def get_logger(name: str | None = "mindtrace", **kwargs) -> logging.Logger | object:
    """
    Create or retrieve a named logger instance.

    This function wraps Python's built-in ``logging.getLogger()`` to provide a
    standardized logger for Mindtrace components. If the logger with the given
    name already exists, it returns the existing instance; otherwise, it creates
    a new one with optional configuration overrides.

    Args:
        name (str): The name of the logger. Defaults to "mindtrace".
        **kwargs: Additional keyword arguments to be passed to `setup_logger`.
            Supported extras include `use_structlog=True`, `structlog_json=True`,
            `structlog_pre_chain`, `structlog_processors`, `structlog_renderer`, and
            `structlog_bind` (dict or callable returning a dict).

    Returns:
        logging.Logger or structlog.BoundLogger: A configured logger instance.

    Example:
        .. code-block:: python

            from mindtrace.core.logging.logger import get_logger

            logger = get_logger("core.module", stream_level=logging.INFO, propagate=True)
            logger.info("Logger configured with custom settings.")

            slogger = get_logger(
                "core.module",
                use_structlog=True,
                structlog_json=True,
                structlog_pre_chain=[],
                structlog_processors=[],
                structlog_bind={"service": "my-service"},
            )
            slogger.info("Structured log", user_id="123")
    """
    if not name:
        name = "mindtrace"

    full_name = name if name.startswith("mindtrace") else f"mindtrace.{name}"
    kwargs.setdefault("propagate", True)
    return setup_logger(full_name, **kwargs)