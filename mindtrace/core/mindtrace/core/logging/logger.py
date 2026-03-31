from __future__ import annotations

import asyncio
import logging
import os
import time
import warnings
from collections import OrderedDict
from functools import wraps
from inspect import signature
from logging import Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from mindtrace.core.config import get_core_settings
from mindtrace.core.utils import ifnone

if TYPE_CHECKING:
    import structlog


def _get_http_exception():
    """Lazily resolve FastAPI's HTTPException, returning None if unavailable."""
    try:
        from fastapi import HTTPException

        return HTTPException
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_configured_loggers: set[str] = set()
_structlog_configured: bool = False


def reset_logging() -> None:
    """Reset all logging state so loggers can be reconfigured.

    Primarily useful in tests that need fresh logger setup between test cases.
    """
    global _configured_loggers, _structlog_configured
    _configured_loggers = set()
    _structlog_configured = False


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


def default_formatter(fmt: Optional[str] = None) -> logging.Formatter:
    """Create a logging formatter with a standardized default format.

    Args:
        fmt: Optional custom format string. If None, uses the default format:
            ``"[%(asctime)s] %(levelname)s: %(name)s: %(message)s"``

    Returns:
        logging.Formatter: Configured formatter instance ready to use with handlers.
    """
    default_fmt = "[%(asctime)s] %(levelname)s: %(name)s: %(message)s"
    return logging.Formatter(fmt or default_fmt)


# ---------------------------------------------------------------------------
# Key-order processor for structlog
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# setup_logger
# ---------------------------------------------------------------------------


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
        structlog_renderer: Optional custom renderer processor. Overrides ``structlog_json``.
        structlog_bind: Optional dict or callable(name)->dict to bind fields.

    Returns:
        Logger | structlog.BoundLogger: Configured logger instance.
    """
    import structlog

    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logger_level)
    logger.propagate = propagate

    # Get config
    default_config = get_core_settings()
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

        _configured_loggers.add(name)
        return logger

    # -- Structlog setup --

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
                ["timestamp", "event", "service", "duration_ms", "metrics", "level", "logger"]
            ),
            renderer,
        ]
    )

    # Configure structlog exactly once (repeated calls have undefined behavior in structlog)
    global _structlog_configured
    if not _structlog_configured:
        structlog.configure(
            processors=pre_chain + processors,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        _structlog_configured = True

    # Set up handlers on the underlying stdlib logger
    stdlib_logger = logging.getLogger(name)
    stdlib_logger.handlers.clear()
    stdlib_logger.setLevel(logger_level)
    stdlib_logger.propagate = propagate

    # Add stream handler
    if add_stream_handler:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(stream_level)
        stream_handler.setFormatter(logging.Formatter("%(message)s"))
        stdlib_logger.addHandler(stream_handler)

    # Add file handler
    if add_file_handler:
        file_handler = RotatingFileHandler(
            filename=str(log_file_path), maxBytes=max_bytes, backupCount=backup_count, mode=file_mode
        )
        file_handler.setLevel(file_level)
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

    _configured_loggers.add(name)
    return bound_logger


# ---------------------------------------------------------------------------
# get_logger  (simplified — no parent-walking)
# ---------------------------------------------------------------------------


def get_logger(
    name: str | None = "mindtrace", use_structlog: bool | None = None, **kwargs
) -> logging.Logger | structlog.BoundLogger:
    """Create or retrieve a named logger instance.

    Wraps :func:`setup_logger` with sensible defaults.

    Args:
        name: The name of the logger. Defaults to ``"mindtrace"``.
        use_structlog: Whether to use structured logging. If None, uses config default.
        **kwargs: Additional keyword arguments passed to :func:`setup_logger`.

    Returns:
        logging.Logger | structlog.BoundLogger: A configured logger instance.
    """
    if not name:
        name = "mindtrace"

    full_name = name if name.startswith("mindtrace") else f"mindtrace.{name}"
    kwargs.setdefault("propagate", True)

    if use_structlog is None:
        use_structlog = get_core_settings().MINDTRACE_LOGGER.USE_STRUCTLOG

    # Ensure the root "mindtrace" logger exists (lazy init, replaces the old __init__.py side effect)
    if "mindtrace" not in _configured_loggers and full_name != "mindtrace":
        # Pass structlog kwargs so the first configure() call uses the caller's processors
        structlog_kwargs = {k: v for k, v in kwargs.items() if k.startswith("structlog_")}
        setup_logger("mindtrace", add_stream_handler=True, use_structlog=use_structlog, **structlog_kwargs)

    return setup_logger(full_name, use_structlog=use_structlog, **kwargs)


# ---------------------------------------------------------------------------
# _UnifiedTrack  (module-level class for track_operation)
# ---------------------------------------------------------------------------


class _UnifiedTrack:
    """Unified object that can act as both async context manager and decorator.

    Used by :func:`track_operation`.  Defined at module level so the class is
    created once rather than on every ``track_operation()`` call.
    """

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
        self._structlog_logger = None
        self._metrics_collector = None

    def _get_structlog_logger(self):
        """Get a structlog logger, caching the result and warning only once."""
        if self._structlog_logger is not None:
            return self._structlog_logger

        if self.logger and hasattr(self.logger, "bind"):
            self._structlog_logger = self.logger
        else:
            if self.logger:
                warnings.warn(
                    f"Logger {self.logger} does not support .bind() method. Creating new structlog logger.",
                    UserWarning,
                )
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
            class_logger = args[0].logger
            if hasattr(class_logger, "bind"):
                return class_logger
            else:
                warnings.warn(
                    f"Logger {class_logger} does not support .bind() method. Creating new structlog logger.",
                    UserWarning,
                )
                logger_name = getattr(class_logger, "name", None) or f"mindtrace.{args[0].__class__.__name__.lower()}"
                return get_logger(logger_name, use_structlog=True)
        elif self.logger_name:
            return get_logger(self.logger_name, use_structlog=True)
        else:
            if self.logger:
                warnings.warn(
                    f"Logger {self.logger} does not support .bind() method. Creating new structlog logger.",
                    UserWarning,
                )
            return get_logger(f"mindtrace.methods.{op_name}", use_structlog=True)

    # -- Context manager protocol --

    async def __aenter__(self):
        """Async context manager entry."""
        logger = self._get_structlog_logger()

        context = dict(self.context)
        metrics_snapshot = self._get_metrics_snapshot()
        if metrics_snapshot is not None:
            context["metrics"] = metrics_snapshot

        bound = logger.bind(operation=self.name, **context)

        self.start_time = time.time()
        bound.log(self.log_level, f"{self.name}_started")
        return bound

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        logger = self._get_structlog_logger()

        context = dict(self.context)
        metrics_snapshot = self._get_metrics_snapshot()
        if metrics_snapshot is not None:
            context["metrics"] = metrics_snapshot

        bound = logger.bind(operation=self.name, **context)

        duration = time.time() - self.start_time

        if exc_type is None:
            bound.log(
                self.log_level, f"{self.name}_completed", duration=duration, duration_ms=round(duration * 1000, 2)
            )
        elif issubclass(exc_type, asyncio.TimeoutError):
            bound.error(
                f"{self.name}_timeout",
                timeout_after=self.timeout,
                duration=duration,
                duration_ms=round(duration * 1000, 2),
            )
            _http_exc = _get_http_exception()
            if _http_exc is not None:
                raise _http_exc(status_code=504, detail="Operation timed out")

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

    # -- Decorator protocol --

    def __call__(self, func: Callable) -> Callable:
        """Make the object usable as a decorator."""
        op_name = self.name or func.__name__

        def extract_context(inner_func: Callable, args: tuple, kwargs: dict) -> dict[str, Any]:
            sig = signature(inner_func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            wanted = self.include_args or []
            return {name: bound_args.arguments[name] for name in wanted if name in bound_args.arguments}

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time_ = time.time()
            extracted_context = extract_context(func, args, kwargs)
            base_logger = self._determine_logger(args, op_name)

            context = dict(self.context)
            metrics_snapshot = self._get_metrics_snapshot()
            if metrics_snapshot is not None:
                context["metrics"] = metrics_snapshot

            bound = base_logger.bind(operation=op_name, **extracted_context, **context)
            bound.log(self.log_level, f"{op_name}_started")

            try:
                if self.timeout:
                    async with asyncio.timeout(self.timeout):
                        result = await func(*args, **kwargs)
                else:
                    result = await func(*args, **kwargs)

                duration = time.time() - start_time_
                bound.log(
                    self.log_level, f"{op_name}_completed", duration=duration, duration_ms=round(duration * 1000, 2)
                )
                return result

            except asyncio.TimeoutError:
                duration = time.time() - start_time_
                bound.error(
                    f"{op_name}_timeout",
                    timeout_after=self.timeout,
                    duration=duration,
                    duration_ms=round(duration * 1000, 2),
                )
                _http_exc = _get_http_exception()
                if _http_exc is not None:
                    raise _http_exc(status_code=504, detail="Operation timed out")
                raise
            except Exception as e:
                duration = time.time() - start_time_
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
            start_time_ = time.time()
            extracted_context = extract_context(func, args, kwargs)
            base_logger = self._determine_logger(args, op_name)

            context = dict(self.context)
            metrics_snapshot = self._get_metrics_snapshot()
            if metrics_snapshot is not None:
                context["metrics"] = metrics_snapshot

            bound = base_logger.bind(operation=op_name, **extracted_context, **context)
            bound.log(self.log_level, f"{op_name}_started")

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time_
                bound.log(
                    self.log_level, f"{op_name}_completed", duration=duration, duration_ms=round(duration * 1000, 2)
                )
                return result
            except Exception as e:
                duration = time.time() - start_time_
                bound.error(
                    f"{op_name}_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    duration=duration,
                    duration_ms=round(duration * 1000, 2),
                )
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper


# ---------------------------------------------------------------------------
# track_operation  (thin factory)
# ---------------------------------------------------------------------------


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
    1. As a context manager: ``async with track_operation("name") as log:``
    2. As a decorator: ``@track_operation("name")``

    Provides structured logging for operations, automatically logging start, completion,
    timeout, and errors with duration metrics.

    Args:
        name: The name of the operation being tracked. When used as decorator,
            defaults to the function name if not provided.
        timeout: Optional timeout in seconds. If provided, raises asyncio.TimeoutError
            when exceeded. If FastAPI is available, raises HTTPException(504) instead.
        logger: Optional structlog logger instance. If None, creates a new logger.
        logger_name: Optional logger name. If None, uses "mindtrace.operations.{name}"
            for context manager or "mindtrace.methods.{name}" for decorator.
        include_args: List of argument names to include in the log context (decorator only).
        log_level: Log level for the operation logs. Defaults to logging.DEBUG.
        include_system_metrics: If True, include system metrics in the log context.
        system_metrics: Optional list of metric names to include.
        **context: Additional context fields to bind to the logger for this operation.
    """
    return _UnifiedTrack(
        name, timeout, logger, logger_name, include_args, log_level, include_system_metrics, system_metrics, context
    )
