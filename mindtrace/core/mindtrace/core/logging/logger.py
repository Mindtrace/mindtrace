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
from typing import Any, Callable, Optional

import structlog

from mindtrace.core.config import Config
from mindtrace.core.utils import ifnone


def default_formatter(fmt: Optional[str] = None) -> logging.Formatter:
    """Create a logging formatter with a standardized default format.

    Args:
        fmt: Optional custom format string. If None, uses the default format:
            ``"[%(asctime)s] %(levelname)s: %(name)s: %(message)s"``

    Returns:
        Configured formatter instance.
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
    """Configure and initialize logging for Mindtrace components.

    Sets up a rotating file handler and a console handler on the given logger.
    Log file defaults to ``~/.cache/mindtrace/{name}.log``.

    Args:
        name: Logger name, defaults to ``"mindtrace"``.
        log_dir: Custom directory for log file.
        logger_level: Overall logger level.
        stream_level: StreamHandler level (e.g., ``ERROR``).
        add_stream_handler: Whether to add a stream handler.
        file_level: FileHandler level (e.g., ``DEBUG``).
        file_mode: Mode for file handler, default is ``'a'`` (append).
        add_file_handler: Whether to add a file handler.
        propagate: Whether the logger should propagate messages to ancestor loggers.
        max_bytes: Maximum size in bytes before rotating log file.
        backup_count: Number of backup files to retain.
        use_structlog: If ``True``, configure and return a structlog ``BoundLogger``.
        structlog_json: If ``True``, render JSON; otherwise use console renderer.
        structlog_pre_chain: Optional pre-processors for stdlib log records.
        structlog_processors: Optional processors after pre_chain (before render).
        structlog_renderer: Optional custom renderer processor.
        structlog_bind: Optional dict or callable(name)->dict to bind fields.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logger_level)
    logger.propagate = propagate

    # Get config
    default_config = Config()
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

    # Configure structlog globally — processors are process-wide by design
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
    """Create or retrieve a named logger instance.

    Ensures the root ``"mindtrace"`` logger exists before setting up child
    loggers so that propagated messages are handled correctly.

    Args:
        name: The name of the logger. Defaults to ``"mindtrace"``.
        use_structlog: Whether to use structured logging. If ``None``, uses config default.
        **kwargs: Additional keyword arguments passed to :func:`setup_logger`.

    Returns:
        A configured logger instance.
    """
    if not name:
        name = "mindtrace"

    full_name = name if name.startswith("mindtrace") else f"mindtrace.{name}"
    caller_provided_kwargs = bool(kwargs)
    kwargs.setdefault("propagate", True)

    # Ensure the root "mindtrace" logger exists so propagated messages have a handler.
    root = logging.getLogger("mindtrace")
    if not root.handlers and full_name != "mindtrace":
        setup_logger("mindtrace", add_stream_handler=True, use_structlog=use_structlog)

    # Fast path: return existing logger if caller didn't request specific configuration.
    # Check for structlog by testing whether the existing logger was wrapped (has .bind).
    if not caller_provided_kwargs:
        existing = logging.getLogger(full_name)
        if existing.handlers:
            if use_structlog:
                return structlog.get_logger(full_name)
            return existing

    return setup_logger(full_name, use_structlog=use_structlog, **kwargs)


# ---------------------------------------------------------------------------
# track_operation — context manager / decorator for structured operation logging
# ---------------------------------------------------------------------------


def _get_structlog_logger(logger, logger_name, op_name):
    """Return a structlog-compatible logger, warning once if the provided one lacks ``.bind()``."""
    if logger and hasattr(logger, "bind"):
        return logger
    if logger:
        warnings.warn(
            f"Logger {logger} does not support .bind(). Creating new structlog logger.",
            UserWarning,
            stacklevel=3,
        )
    name = logger_name or f"mindtrace.operations.{op_name}"
    return get_logger(name, use_structlog=True)


def _determine_logger_for_decorator(logger, logger_name, args, op_name):
    """Pick the best structlog logger for a decorated method call."""
    if logger and hasattr(logger, "bind"):
        return logger

    # For bound methods, try the instance's logger
    if args and hasattr(args[0], "logger"):
        class_logger = args[0].logger
        if hasattr(class_logger, "bind"):
            return class_logger
        warnings.warn(
            f"Logger {class_logger} does not support .bind(). Creating new structlog logger.",
            UserWarning,
            stacklevel=3,
        )
        logger_name = getattr(class_logger, "name", None) or f"mindtrace.{args[0].__class__.__name__.lower()}"
        return get_logger(logger_name, use_structlog=True)

    if logger_name:
        return get_logger(logger_name, use_structlog=True)

    if logger:
        warnings.warn(
            f"Logger {logger} does not support .bind(). Creating new structlog logger.",
            UserWarning,
            stacklevel=3,
        )

    return get_logger(f"mindtrace.methods.{op_name}", use_structlog=True)


class _OperationTracker:
    """Tracks a named operation as both an async context manager and a decorator."""

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
        if self._structlog_logger is None:
            self._structlog_logger = _get_structlog_logger(self.logger, self.logger_name, self.name)
        return self._structlog_logger

    def _get_metrics_collector(self):
        if self._metrics_collector is not None:
            return self._metrics_collector
        if self.include_system_metrics:
            try:
                from mindtrace.core.utils import SystemMetricsCollector

                self._metrics_collector = SystemMetricsCollector(metrics_to_collect=self.system_metrics)
            except Exception as e:
                warnings.warn(f"Failed to initialize SystemMetricsCollector: {e}", UserWarning, stacklevel=2)
        return self._metrics_collector

    def _get_metrics_snapshot(self):
        collector = self._get_metrics_collector()
        if collector is not None:
            try:
                return collector()
            except Exception as e:
                warnings.warn(f"Failed to collect system metrics: {e}", UserWarning, stacklevel=2)
        return None

    def _build_context(self):
        ctx = dict(self.context)
        snapshot = self._get_metrics_snapshot()
        if snapshot is not None:
            ctx["metrics"] = snapshot
        return ctx

    # --- Async context manager ---

    async def __aenter__(self):
        bound = self._get_structlog_logger().bind(operation=self.name, **self._build_context())
        self.start_time = time.time()
        bound.log(self.log_level, f"{self.name}_started")
        return bound

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        bound = self._get_structlog_logger().bind(operation=self.name, **self._build_context())
        duration = time.time() - self.start_time
        dur_ms = round(duration * 1000, 2)

        if exc_type is None:
            bound.log(self.log_level, f"{self.name}_completed", duration=duration, duration_ms=dur_ms)
        elif issubclass(exc_type, TimeoutError):
            bound.error(f"{self.name}_timeout", timeout_after=self.timeout, duration=duration, duration_ms=dur_ms)
            raise
        else:
            bound.error(
                f"{self.name}_failed",
                error=str(exc_val),
                error_type=type(exc_val).__name__,
                duration=duration,
                duration_ms=dur_ms,
            )
            raise

    # --- Decorator ---

    def __call__(self, func: Callable) -> Callable:
        op_name = self.name or func.__name__

        def _extract_context(inner_func, args, kwargs):
            sig = signature(inner_func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            wanted = self.include_args or []
            return {name: bound_args.arguments[name] for name in wanted if name in bound_args.arguments}

        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def wrapper(*args, **kwargs):
                extracted = _extract_context(func, args, kwargs)
                base_logger = _determine_logger_for_decorator(self.logger, self.logger_name, args, op_name)
                bound = base_logger.bind(operation=op_name, **extracted, **self._build_context())
                bound.log(self.log_level, f"{op_name}_started")
                start = time.time()
                try:
                    if self.timeout:
                        async with asyncio.timeout(self.timeout):
                            result = await func(*args, **kwargs)
                    else:
                        result = await func(*args, **kwargs)
                    dur = time.time() - start
                    bound.log(self.log_level, f"{op_name}_completed", duration=dur, duration_ms=round(dur * 1000, 2))
                    return result
                except TimeoutError:
                    dur = time.time() - start
                    bound.error(
                        f"{op_name}_timeout", timeout_after=self.timeout, duration=dur, duration_ms=round(dur * 1000, 2)
                    )
                    raise
                except Exception as e:
                    dur = time.time() - start
                    bound.error(
                        f"{op_name}_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                        duration=dur,
                        duration_ms=round(dur * 1000, 2),
                    )
                    raise

        else:

            @wraps(func)
            def wrapper(*args, **kwargs):
                extracted = _extract_context(func, args, kwargs)
                base_logger = _determine_logger_for_decorator(self.logger, self.logger_name, args, op_name)
                bound = base_logger.bind(operation=op_name, **extracted, **self._build_context())
                bound.log(self.log_level, f"{op_name}_started")
                start = time.time()
                try:
                    result = func(*args, **kwargs)
                    dur = time.time() - start
                    bound.log(self.log_level, f"{op_name}_completed", duration=dur, duration_ms=round(dur * 1000, 2))
                    return result
                except Exception as e:
                    dur = time.time() - start
                    bound.error(
                        f"{op_name}_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                        duration=dur,
                        duration_ms=round(dur * 1000, 2),
                    )
                    raise

        return wrapper


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
    """Track an operation as either an async context manager or a decorator.

    Usage as context manager::

        async with track_operation("fetch_data", user_id="123") as log:
            result = await some_operation()
            log.info("fetched", count=len(result))

    Usage as decorator::

        @track_operation("process", timeout=5.0)
        async def process(data): ...

    Args:
        name: Operation name. Defaults to function name when used as decorator.
        timeout: Optional timeout in seconds (raises ``TimeoutError``).
        logger: Optional structlog logger. If ``None``, creates one automatically.
        logger_name: Optional logger name override.
        include_args: Argument names to include in log context (decorator only).
        log_level: Log level for operation events.
        include_system_metrics: If ``True``, include system metrics in context.
        system_metrics: Specific metric names to collect. ``None`` = all.
        **context: Additional fields bound to the logger for this operation.
    """
    return _OperationTracker(
        name, timeout, logger, logger_name, include_args, log_level, include_system_metrics, system_metrics, context
    )
