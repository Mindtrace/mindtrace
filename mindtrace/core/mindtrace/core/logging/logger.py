import logging
import os
import warnings
from collections import OrderedDict
from logging import Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Optional

import structlog

from mindtrace.core.config import CoreSettings
from mindtrace.core.utils import ifnone


def default_formatter(fmt: Optional[str] = None) -> logging.Formatter:
    """Create a logging formatter with a standardized default format.

    This function returns a Python logging Formatter instance configured with
    a default format string that includes timestamp, log level, logger name,
    and message. If a custom format string is provided, it will be used instead.

    Args:
        fmt: Optional custom format string. If None, uses the default format:
            `"[%(asctime)s] %(levelname)s: %(name)s: %(message)s"`
            - `%(asctime)s`: Timestamp when the log record was created
            - `%(levelname)s`: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            - `%(name)s`: Name of the logger
            - `%(message)s`: The actual log message

    Returns:
        logging.Formatter: Configured formatter instance ready to use with handlers.

    Examples:
        Use default format:
        ```python
        formatter = default_formatter()
        handler.setFormatter(formatter)
        # Output: [2024-01-15 10:30:45,123] INFO: mindtrace.core: Operation completed
        ```

        Use custom format:
        ```python
        custom_fmt = "%(levelname)s - %(message)s"
        formatter = default_formatter(fmt=custom_fmt)
        handler.setFormatter(formatter)
        # Output: INFO - Operation completed
        ```
    """
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
    ```python
    from mindtrace.core.logging.logger import get_logger

    logger = get_logger("core.module", stream_level=logging.INFO, propagate=True)
    logger.info("Logger configured with custom settings.")
    ```
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


def track_operation(
    name: str = None,
    timeout: float | None = None,
    logger: Any | None = None,
    logger_name: str | None = None,
    include_args: list[str] | None = None,
    log_level: int = logging.DEBUG,
    include_system_metrics: bool = False,
    system_metrics: list[str] | None = None,
    **context: Any,
):
    """Unified function that works as both context manager and decorator.

    This function can be used in two ways:
    1. As a context manager: `async with track_operation("name") as log:`
    2. As a decorator: `@track_operation("name")`

    Provides structured logging for operations, automatically logging start, completion,
    timeout, and errors with duration metrics. Requires structlog to be installed.

    Args:
        name: The name of the operation being tracked. When used as decorator,
            defaults to the function name if not provided.
        timeout: Optional timeout in seconds. If provided, raises asyncio.TimeoutError
            when exceeded. If FastAPI is available, raises HTTPException(504) instead.
        logger: Optional structlog logger instance. If None, creates a new logger.
        logger_name: Optional logger name. If None, uses "mindtrace.operations.{name}"
            for context manager or "mindtrace.methods.{name}" for decorator.
        include_args: List of argument names to include in the log context (decorator only).
            If None, no arguments are logged. Only works with bound methods (self as first arg).
        log_level: Log level for the operation logs. Defaults to logging.DEBUG.
        include_system_metrics: If True, include system metrics in the log context.
        system_metrics: Optional list of metric names to include. If None, include all available metrics.
        **context: Additional context fields to bind to the logger for this operation.

    Yields (context manager):
        structlog.BoundLogger: A bound logger with operation context for logging.

    Returns (decorator):
        Callable: The decorated method with automatic logging.

    Raises:
        asyncio.TimeoutError: If timeout is exceeded and FastAPI is not available.
        HTTPException: If timeout is exceeded and FastAPI is available (status_code=504).
        Exception: Re-raises any exception that occurs during operation execution.

    Examples:
        Context manager usage:
        .. code-block:: python

            import asyncio
            from mindtrace.core.logging.logger import track_operation

            async def fetch_data():
                async with track_operation("fetch_data", user_id="123") as log:
                    # Your async operation here
                    result = await some_async_operation()
                    log.info("Data fetched successfully", records_count=len(result))
                    return result

        Decorator usage on async function:
        .. code-block:: python

            @track_operation("process_data", batch_id="batch_123", timeout=5.0)
            async def process_data(data: list) -> list:
                # Method execution is automatically logged
                return [item.upper() for item in data]

        Decorator usage on class method:
        .. code-block:: python

            class DataProcessor:
                def __init__(self):
                    self.logger = structlog.get_logger("data_processor")

                @track_operation("process_batch", include_args=["batch_id"])
                async def process_batch(self, batch_id: str, data: list):
                    # Logs will include batch_id in context
                    return await self._process_data(data)

        With timeout:
        .. code-block:: python

            async def fetch_with_timeout():
                try:
                    async with track_operation("fetch_data", timeout=30.0, service="api") as log:
                        result = await slow_operation()
                        return result
                except asyncio.TimeoutError:
                    # Operation timed out after 30 seconds
                    return None
    """
    import asyncio as _asyncio
    import time as _time
    from functools import wraps
    from inspect import signature

    try:
        from fastapi import HTTPException as _HTTPException
    except Exception:
        _HTTPException = None  # type: ignore

    class UnifiedTrack:
        """Unified object that can act as both context manager and decorator."""

        def __init__(
            self,
            name,
            timeout,
            logger,
            logger_name,
            include_args,
            log_level,
            include_system_metrics,
            system_metrics,
            context,
        ):
            self.name = name
            self.timeout = timeout
            self.logger = logger
            self.logger_name = logger_name
            self.include_args = include_args
            self.log_level = log_level
            self.include_system_metrics = include_system_metrics
            self.system_metrics = system_metrics
            self.context = context
            self.start_time = None
            self._structlog_logger = None  # Cache for structlog logger
            self._metrics_collector = None

        def _get_structlog_logger(self):
            """Get a structlog logger, caching the result and warning only once."""
            if self._structlog_logger is not None:
                return self._structlog_logger

            # Check if provided logger supports .bind()
            if self.logger and hasattr(self.logger, "bind"):
                self._structlog_logger = self.logger
            else:
                if self.logger:
                    warnings.warn(
                        f"Logger {self.logger} does not support .bind() method. Creating new structlog logger.",
                        UserWarning,
                    )

                # Get a proper structlog logger
                logger_name = self.logger_name or f"mindtrace.operations.{self.name}"
                self._structlog_logger = get_logger(logger_name, use_structlog=True)

            return self._structlog_logger

        def _get_metrics_collector(self):
            """Get a metrics collector, caching the result."""
            if self._metrics_collector is not None:
                return self._metrics_collector

            if self.include_system_metrics:
                try:
                    from mindtrace.core.utils import SystemMetricsCollector

                    self._metrics_collector = SystemMetricsCollector(metrics_to_collect=self.system_metrics)
                except Exception as e:
                    self._metrics_collector = None
                    warnings.warn(
                        f"Failed to initialize SystemMetricsCollector; metrics will be omitted: {e}",
                        UserWarning,
                    )

            return self._metrics_collector

        def _get_metrics_snapshot(self):
            """Get current metrics snapshot if available."""
            collector = self._get_metrics_collector()
            if collector is not None:
                try:
                    return collector()
                except Exception as e:
                    warnings.warn(
                        f"Failed to collect system metrics snapshot; omitting metrics: {e}",
                        UserWarning,
                    )
                    return None
            return None

        def _determine_logger(self, args, op_name):
            """Determine the appropriate logger for the operation."""
            if self.logger and hasattr(self.logger, "bind"):
                return self.logger

            # For class methods, try to use the class's logger if it exists
            if args and hasattr(args[0], "__class__") and hasattr(args[0], "logger"):
                # This is a class method with a logger attribute, use it
                class_logger = args[0].logger
                if hasattr(class_logger, "bind"):
                    return class_logger
                else:
                    # Class logger doesn't support bind, create new one with same name
                    warnings.warn(
                        f"Logger {class_logger} does not support .bind() method. Creating new structlog logger.",
                        UserWarning,
                    )
                    logger_name = (
                        getattr(class_logger, "name", None) or f"mindtrace.{args[0].__class__.__name__.lower()}"
                    )
                    return get_logger(logger_name, use_structlog=True)
            elif self.logger_name:
                return get_logger(self.logger_name, use_structlog=True)
            else:
                # Only issue warning if we have a logger that doesn't support bind and no class logger to use
                if self.logger:
                    warnings.warn(
                        f"Logger {self.logger} does not support .bind() method. Creating new structlog logger.",
                        UserWarning,
                    )

                # Fallback to the original pattern for standalone functions
                return get_logger(f"mindtrace.methods.{op_name}", use_structlog=True)

        # Context manager methods
        async def __aenter__(self):
            """Async context manager entry."""
            # Get structlog logger (with caching and single warning)
            logger = self._get_structlog_logger()

            # Add metrics to context if enabled
            context = dict(self.context)
            metrics_snapshot = self._get_metrics_snapshot()
            if metrics_snapshot is not None:
                context["metrics"] = metrics_snapshot

            bound = logger.bind(operation=self.name, **context)

            self.start_time = _time.time()
            bound.log(self.log_level, f"{self.name}_started")
            return bound

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            """Async context manager exit."""
            # Get structlog logger (with caching and single warning)
            logger = self._get_structlog_logger()

            # Add metrics to context if enabled
            context = dict(self.context)
            metrics_snapshot = self._get_metrics_snapshot()
            if metrics_snapshot is not None:
                context["metrics"] = metrics_snapshot

            bound = logger.bind(operation=self.name, **context)

            duration = _time.time() - self.start_time

            if exc_type is None:
                bound.log(
                    self.log_level, f"{self.name}_completed", duration=duration, duration_ms=round(duration * 1000, 2)
                )
            elif isinstance(exc_val, _asyncio.TimeoutError):
                bound.error(
                    f"{self.name}_timeout",
                    timeout_after=self.timeout,
                    duration=duration,
                    duration_ms=round(duration * 1000, 2),
                )
                if _HTTPException is not None:
                    raise _HTTPException(status_code=504, detail="Operation timed out")  # type: ignore
                raise
            else:
                bound.error(
                    f"{self.name}_failed",
                    error=str(exc_val),
                    error_type=type(exc_val).__name__,
                    duration=duration,
                    duration_ms=round(duration * 1000, 2),
                )
                raise

        # Decorator method
        def __call__(self, func: Callable) -> Callable:
            """Make the decorator callable."""
            op_name = self.name or func.__name__

            def extract_context(inner_func: Callable, args: tuple, kwargs: dict) -> dict[str, Any]:
                sig = signature(inner_func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
                wanted = self.include_args or []
                return {name: bound_args.arguments[name] for name in wanted if name in bound_args.arguments}

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = _time.time()

                # Extract context from arguments if needed
                extracted_context = extract_context(func, args, kwargs)

                # Determine the appropriate logger
                base_logger = self._determine_logger(args, op_name)

                # Add metrics to context if enabled
                context = dict(self.context)
                metrics_snapshot = self._get_metrics_snapshot()
                if metrics_snapshot is not None:
                    context["metrics"] = metrics_snapshot

                bound = base_logger.bind(operation=op_name, **extracted_context, **context)
                bound.log(self.log_level, f"{op_name}_started")

                try:
                    if self.timeout:
                        async with _asyncio.timeout(self.timeout):
                            result = await func(*args, **kwargs)
                    else:
                        result = await func(*args, **kwargs)

                    duration = _time.time() - start_time
                    bound.log(
                        self.log_level, f"{op_name}_completed", duration=duration, duration_ms=round(duration * 1000, 2)
                    )
                    return result

                except _asyncio.TimeoutError:
                    duration = _time.time() - start_time
                    bound.error(
                        f"{op_name}_timeout",
                        timeout_after=self.timeout,
                        duration=duration,
                        duration_ms=round(duration * 1000, 2),
                    )
                    if _HTTPException is not None:
                        raise _HTTPException(status_code=504, detail="Operation timed out")  # type: ignore
                    raise
                except Exception as e:
                    duration = _time.time() - start_time
                    bound.error(
                        f"{op_name}_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                        duration=duration,
                        duration_ms=round(duration * 1000, 2),
                    )
                    raise

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = _time.time()

                # Extract context from arguments if needed
                extracted_context = extract_context(func, args, kwargs)

                # Determine the appropriate logger
                base_logger = self._determine_logger(args, op_name)

                # Add metrics to context if enabled
                context = dict(self.context)
                metrics_snapshot = self._get_metrics_snapshot()
                if metrics_snapshot is not None:
                    context["metrics"] = metrics_snapshot

                bound = base_logger.bind(operation=op_name, **extracted_context, **context)
                bound.log(self.log_level, f"{op_name}_started")

                try:
                    result = func(*args, **kwargs)
                    duration = _time.time() - start_time
                    bound.log(
                        self.log_level, f"{op_name}_completed", duration=duration, duration_ms=round(duration * 1000, 2)
                    )
                    return result
                except Exception as e:
                    duration = _time.time() - start_time
                    bound.error(
                        f"{op_name}_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                        duration=duration,
                        duration_ms=round(duration * 1000, 2),
                    )
                    raise

            # Return appropriate wrapper based on function type
            return async_wrapper if _asyncio.iscoroutinefunction(func) else sync_wrapper

    return UnifiedTrack(
        name, timeout, logger, logger_name, include_args, log_level, include_system_metrics, system_metrics, context
    )
