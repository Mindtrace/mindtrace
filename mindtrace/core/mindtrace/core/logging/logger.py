import logging
import logging.config
from pathlib import Path
from typing import Optional
from mindtrace.core.logging.config import default_logging_config


def setup_logging(log_config: dict = None, log_dir: Optional[Path] = None) -> None:
    """
    Configure and initialize logging for Mindtrace components.

    This function sets up a default logging configuration that includes a file handler
    to write logs to a persistent log file and a console handler for error-level messages.
    If no custom configuration is provided, a default configuration is used. The log
    file path defaults to `~/.cache/mindtrace/mindtrace.log` and the directory is created
    if it does not exist.

    Args:
        log_config (dict, optional): A custom logging configuration dictionary following
            Python's ``logging.config.dictConfig`` format. If provided, it will be used as-is.
        log_dir (Optional[Path]): Optional custom directory for the log file. If not set,
            defaults to ``~/.cache/mindtrace``.

    Returns:
        None

    Raises:
        OSError: If the log directory cannot be created.
        ValueError: If the logging configuration is invalid.

    Example:
        .. code-block:: python

            from mindtrace.core.logging.utils import setup_logging
            setup_logging()

        This will produce logs in the default file location and print errors to the console.

    """
    if log_config:
        logging.config.dictConfig(config=log_config)
        return

    log_file_path = (log_dir or Path.home() / ".cache/mindtrace") / "mindtrace.log"
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    merged_config = default_logging_config.copy()
    merged_config["handlers"]["file"]["filename"] = str(log_file_path)

    logging.config.dictConfig(config=merged_config)

def Logger(name: str = "Mindtrace") -> logging.Logger:
    """
    Create or retrieve a named logger instance.

    This function wraps Python's built-in ``logging.getLogger()`` to provide a
    standardized logger for Mindtrace components. If the logger with the given
    name already exists, it returns the existing instance; otherwise, it creates
    a new one.

    Args:
        name (str): The name of the logger. Defaults to "Mindtrace".

    Returns:
        logging.Logger: A configured logger instance for the given name.

    Example:
        .. code-block:: python

            from mindtrace.core.logging.logger import Logger

            logger = Logger("mindtrace.core.base")
            logger.info("This will be recorded with the correct namespace.")

    See also:
        Python logging documentation:
        `logging.getLogger <https://docs.python.org/3/library/logging.html#logging.getLogger>`_

    """
    return logging.getLogger(name)