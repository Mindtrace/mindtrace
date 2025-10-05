import logging
import os
import structlog
from collections import OrderedDict
from logging import Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Generator, Callable, Any
from contextlib import asynccontextmanager

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
    file_level: int = logging.DEBUG,
    file_mode: str = "a",
    propagate: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    use_structlog: Optional[bool] = None,
    structlog_json: Optional[bool] = True,
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
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(stream_level)
        stream_handler.setFormatter(default_formatter())
        logger.addHandler(stream_handler)

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
                    "event",
                    "service",
                    "duration_ms",
                    "metrics",
                    "level",
                    "logger",
                    "timestamp",
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
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(stream_level)
    # Use standard formatter to preserve [timestamp] level: logger: message format
    stream_handler.setFormatter(default_formatter())
    stdlib_logger.addHandler(stream_handler)

    # Add file handler
    file_handler = RotatingFileHandler(
        filename=str(log_file_path), maxBytes=max_bytes, backupCount=backup_count, mode=file_mode
    )
    file_handler.setLevel(file_level)
    # Use standard formatter to preserve [timestamp] level: logger: message format
    file_handler.setFormatter(default_formatter())
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


def get_logger(name: str | None = "mindtrace", use_structlog: bool | None = None, **kwargs) -> logging.Logger | object:
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
        logging.Logger or structlog.BoundLogger: A configured logger instance.

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
            setup_logger(parent_name, use_structlog=use_structlog, **kwargs)
        for part in parts[1:-1]:
            parent_name = f"{parent_name}.{part}"
            parent_logger = logging.getLogger(parent_name)
            if parent_logger.handlers:
                setup_logger(parent_name, use_structlog=use_structlog, **kwargs)
    return setup_logger(full_name, use_structlog=use_structlog, **kwargs)

@asynccontextmanager
async def track_operation(
    name: str,
    timeout: float | None = None,
    logger: Any | None = None,
    logger_name: str | None = None,
    **context: Any,
) -> Generator[Any, None, None]:
    """Asynchronously track an operation, logging start, completion, timeout, and errors.
    
    This context manager provides structured logging for async operations, automatically
    logging operation start, completion, timeouts, and errors with duration metrics.
    Requires structlog to be installed.
    
    Args:
        name: The name of the operation being tracked.
        timeout: Optional timeout in seconds. If provided, raises asyncio.TimeoutError
            when exceeded. If FastAPI is available, raises HTTPException(504) instead.
        logger: Optional structlog logger instance. If None, creates a new logger.
        logger_name: Optional logger name. If None, uses "mindtrace.operations.{name}".
        **context: Additional context fields to bind to the logger for this operation.
    
    Yields:
        structlog.BoundLogger: A bound logger with operation context for logging.
    
    Raises:
        asyncio.TimeoutError: If timeout is exceeded and FastAPI is not available.
        HTTPException: If timeout is exceeded and FastAPI is available (status_code=504).
        Exception: Re-raises any exception that occurs during operation execution.
    
    Examples:
        Basic usage:
        .. code-block:: python
        
            import asyncio
            from mindtrace.core.logging.logger import track_operation
            
            async def fetch_data():
                async with track_operation("fetch_data", user_id="123") as log:
                    # Your async operation here
                    result = await some_async_operation()
                    log.info("Data fetched successfully", records_count=len(result))
                    return result
        
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
        
        With custom logger:
        .. code-block:: python
            from mindtrace.core.logging.logger import get_logger
            custom_logger = get_logger("my_service", use_structlog=True)
            async with track_operation("process_data", logger=custom_logger, batch_id="batch_123") as log:
                await process_batch()
                log.info("Batch processed", status="completed")
        
        With custom logger name:
        .. code-block:: python
        
            async with track_operation("fetch_data", logger_name="api.data_fetcher", user_id="123") as log:
                result = await fetch_from_api()
                log.info("Data fetched", records_count=len(result))
                return result
    """
    import time as _time
    import asyncio as _asyncio
    try:
        from fastapi import HTTPException as _HTTPException
    except Exception:
        _HTTPException = None  # type: ignore

    bound = (logger or get_logger(logger_name or f"mindtrace.operations.{name}", use_structlog=True)).bind(operation=name, **context)
    start_time = _time.time()

    try:
        bound.info(f"{name}_started")
        if timeout:
            async with _asyncio.timeout(timeout):
                yield bound
        else:
            yield bound

        duration = _time.time() - start_time
        bound.info(f"{name}_completed", duration=duration, duration_ms=round(duration * 1000, 2))
    except _asyncio.TimeoutError:
        duration = _time.time() - start_time
        bound.error(f"{name}_timeout", timeout_after=timeout, duration=duration, duration_ms=round(duration * 1000, 2))
        if _HTTPException is not None:
            raise _HTTPException(status_code=504, detail="Operation timed out")  # type: ignore
        raise
    except Exception as e:  # noqa: BLE001
        duration = _time.time() - start_time
        bound.error(
            f"{name}_failed",
            error=str(e),
            error_type=type(e).__name__,
            duration=duration,
            duration_ms=round(duration * 1000, 2),
        )
        raise


def track_method(operation_name: str | None = None, include_args: list[str] | None = None, logger_name: str | None = None) -> Callable:
    """Decorator to track execution of sync/async methods with structured logs.
    
    This decorator automatically logs method execution with start, completion, and error
    events, including duration metrics. Works with both synchronous and asynchronous
    methods. Requires structlog to be installed.
    
    Args:
        operation_name: Custom name for the operation. If None, uses the method name.
        include_args: List of argument names to include in the log context. If None,
            no arguments are logged. Only works with bound methods (self as first arg).
        logger_name: Optional logger name. If None, uses "mindtrace.methods.{class_name}".
    
    Returns:
        Callable: The decorated method with automatic logging.
    
    Raises:
        ImportError: If structlog is not installed.
        Exception: Re-raises any exception that occurs during method execution.
    
    Examples:
        Basic usage on a class method:
        .. code-block:: python
        
            from mindtrace.core.logging.logger import track_method
            import structlog
            
            class DataProcessor:
                def __init__(self):
                    self.logger = structlog.get_logger("data_processor")
                
                @track_method()
                async def process_data(self, data: list, batch_id: str):
                    # Method execution is automatically logged
                    return [item.upper() for item in data]
        
        With custom operation name and argument tracking:
        .. code-block:: python
        
            class APIClient:
                def __init__(self):
                    self.logger = structlog.get_logger("api_client")
                
                @track_method("api_request", include_args=["endpoint", "method"])
                async def make_request(self, endpoint: str, method: str, data: dict):
                    # Logs will include endpoint and method in context
                    response = await self._send_request(endpoint, method, data)
                    return response
        
        On synchronous methods:
        .. code-block:: python
        
            class Calculator:
                def __init__(self):
                    self.logger = structlog.get_logger("calculator")
                
                @track_method("calculation", include_args=["operation"])
                def calculate(self, operation: str, x: float, y: float):
                    if operation == "add":
                        return x + y
                    elif operation == "multiply":
                        return x * y
                    else:
                        raise ValueError(f"Unknown operation: {operation}")
        
        With custom logger name:
        .. code-block:: python
        
            class DataProcessor:
                @track_method("process", logger_name="data.processor", include_args=["batch_id"])
                async def process_batch(self, batch_id: str, data: list):
                    # Uses logger name "data.processor" instead of default
                    return await self._process_data(data)
        
        The decorator automatically logs:
        - {operation_name}_started: When method execution begins
        - {operation_name}_completed: When method completes successfully (with duration)
        - {operation_name}_failed: When method raises an exception (with error details)
        
        All log entries include duration in seconds and milliseconds.
    """

    def decorator(func: Callable) -> Callable:
        op_name = operation_name or func.__name__

        def extract_context(inner_func: Callable, args: tuple, kwargs: dict) -> dict[str, Any]:
            from inspect import signature

            sig = signature(inner_func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            wanted = include_args or []
            return {name: bound_args.arguments[name] for name in wanted if name in bound_args.arguments}

        async def _async_impl(self, *args, **kwargs):
            import time as _time

            context = extract_context(func, (self,) + args, kwargs)
            base_logger = getattr(self, "logger", None)
            if not base_logger or not hasattr(base_logger, "bind"):
                default_name = logger_name or f"mindtrace.methods.{self.__class__.__name__}"
                base_logger = get_logger(default_name, use_structlog=True)
            bound = base_logger.bind(operation=op_name, **context)
            start = _time.time()
            bound.info(f"{op_name}_started")
            try:
                result = await func(self, *args, **kwargs)
                duration = _time.time() - start
                bound.info(f"{op_name}_completed", duration=duration, duration_ms=round(duration * 1000, 2))
                return result
            except Exception as e:  # noqa: BLE001
                duration = _time.time() - start
                bound.error(
                    f"{op_name}_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    duration=duration,
                    duration_ms=round(duration * 1000, 2),
                )
                raise

        def _sync_impl(self, *args, **kwargs):
            import time as _time

            context = extract_context(func, (self,) + args, kwargs)
            base_logger = getattr(self, "logger", None)
            if not base_logger or not hasattr(base_logger, "bind"):
                default_name = logger_name or f"mindtrace.methods.{self.__class__.__name__}"
                base_logger = get_logger(default_name, use_structlog=True)
            bound = base_logger.bind(operation=op_name, **context)
            start = _time.time()
            bound.info(f"{op_name}_started")
            try:
                result = func(self, *args, **kwargs)
                duration = _time.time() - start
                bound.info(f"{op_name}_completed", duration=duration, duration_ms=round(duration * 1000, 2))
                return result
            except Exception as e:  # noqa: BLE001
                duration = _time.time() - start
                bound.error(
                    f"{op_name}_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    duration=duration,
                    duration_ms=round(duration * 1000, 2),
                )
                raise

        import asyncio as _asyncio
        return _async_impl if _asyncio.iscoroutinefunction(func) else _sync_impl  # type: ignore[name-defined]

    return decorator

