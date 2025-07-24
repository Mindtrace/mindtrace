import logging
import os
from logging import Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from mindtrace.core.config import Config


def default_formatter(fmt: Optional[str] = None) -> logging.Formatter:
    """
    Returns a logging formatter with a default format if none is specified.
    """
    default_fmt = "[%(asctime)s] %(levelname)s: %(name)s: %(message)s"
    return logging.Formatter(fmt or default_fmt)


def setup_logger(
    name: str = "mindtrace",
    log_dir: Optional[Path] = None,
    logger_level: int = logging.DEBUG,
    stream_level: int = logging.ERROR,
    file_level: int = logging.DEBUG,
    file_mode: str = "a",
    propagate: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> Logger:
    """Configure and initialize logging for Mindtrace components programmatically.

    Sets up a rotating file handler and a console handler on the given logger.
    Log file defaults to ~/.cache/mindtrace/{name}.log.

    Args:
        name (str): Logger name, defaults to "mindtrace".
        log_dir (Optional[Path]): Custom directory for log file.
        logger_level (int): Overall logger level.
        stream_level (int): StreamHandler level (e.g., ERROR).
        file_level (int): FileHandler level (e.g., DEBUG).
        file_mode (str): Mode for file handler, default is 'a' (append).
        propagate (bool): Whether the logger should propagate messages to ancestor loggers.
        max_bytes (int): Maximum size in bytes before rotating log file.
        backup_count (int): Number of backup files to retain.

    Returns:
        Logger: Configured logger instance.
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
    if name == "mindtrace":
        child_log_path = f"{name}.log"
    else:
        child_log_path = os.path.join("modules", f"{name}.log")

    if log_dir:
        log_file_path = os.path.join(log_dir, child_log_path)
    else:
        log_file_path = os.path.join(default_config["MINDTRACE_LOGGER_DIR"], child_log_path)

    os.makedirs(Path(log_file_path).parent, exist_ok=True)
    file_handler = RotatingFileHandler(
        filename=str(log_file_path), maxBytes=max_bytes, backupCount=backup_count, mode=file_mode
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(default_formatter())
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str | None = "mindtrace", **kwargs) -> logging.Logger:
    """
    Create or retrieve a named logger instance.

    This function wraps Python's built-in ``logging.getLogger()`` to provide a
    standardized logger for Mindtrace components. If the logger with the given
    name already exists, it returns the existing instance; otherwise, it creates
    a new one with optional configuration overrides.

    Args:
        name (str): The name of the logger. Defaults to "mindtrace".
        **kwargs: Additional keyword arguments to be passed to `setup_logger`.

    Returns:
        logging.Logger: A configured logger instance.

    Example:
        .. code-block:: python

            from mindtrace.core.logging.logger import get_logger

            logger = get_logger("core.module", stream_level=logging.INFO, propagate=True)
            logger.info("Logger configured with custom settings.")
    """
    if not name:
        name = "mindtrace"

    full_name = name if name.startswith("mindtrace") else f"mindtrace.{name}"
    kwargs.setdefault("propagate", True)
    return setup_logger(full_name, **kwargs)
