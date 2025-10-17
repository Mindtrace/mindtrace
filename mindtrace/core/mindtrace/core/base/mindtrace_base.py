"""Mindtrace class. Provides unified configuration, logging and context management."""

import inspect
import logging
import time
import traceback
from abc import ABC, ABCMeta
from functools import wraps
from typing import Callable, Optional

from mindtrace.core.config import CoreConfig, SettingsLike
from mindtrace.core.logging.logger import get_logger
from mindtrace.core.utils import SystemMetricsCollector, ifnone


class MindtraceMeta(type):
    """Metaclass for Mindtrace class.

    The MindtraceMeta metaclass enables classes deriving from Mindtrace to automatically use the same default logger within
    class methods as it does within instance methods. I.e. consider the following class:

    Example, logging in both class methods and instance methods::

        from mindtrace.core import Mindtrace

        class MyClass(Mindtrace):
            def __init__(self):
                super().__init__()

            def instance_method(self):
                self.logger.info(f"Using logger: {self.logger.name}")  # Using logger: mindtrace.my_module.MyClass

            @classmethod
            def class_method(cls):
                cls.logger.info(f"Using logger: {cls.logger.name}")  # Using logger: mindtrace.my_module.MyClass
    """

    def __init__(cls, name, bases, attr_dict):
        super().__init__(name, bases, attr_dict)
        cls._logger = None
        cls._config = None
        cls._logger_kwargs = None
        cls._cached_logger_kwargs = None  # Store the kwargs used to create the current logger

    @property
    def logger(cls):
        # Check if we need to recreate the logger due to kwargs changes
        current_kwargs = cls._logger_kwargs or {}
        
        # Compare current kwargs with cached kwargs
        if (cls._logger is not None and 
            cls._cached_logger_kwargs is not None and 
            cls._cached_logger_kwargs != current_kwargs):
            # Logger exists but kwargs have changed - recreate it
            cls._logger = None
            cls._cached_logger_kwargs = None
        
        if cls._logger is None:
            # Use stored logger kwargs if available, otherwise use defaults
            kwargs = current_kwargs
            cls._logger = get_logger(cls.unique_name, **kwargs)
            cls._cached_logger_kwargs = kwargs.copy()  # Store a copy for comparison
        return cls._logger

    @logger.setter
    def logger(cls, new_logger):
        cls._logger = new_logger

    @property
    def unique_name(self) -> str:
        return self.__module__ + "." + self.__name__

    @property
    def config(cls):
        if cls._config is None:
            cls._config = CoreConfig()
        return cls._config

    @config.setter
    def config(cls, new_config):
        cls._config = new_config


class Mindtrace(metaclass=MindtraceMeta):
    """Base class for all Mindtrace package core classes.

    The Mindtrace class adds default context manager and logging methods. All classes that derive from Mindtrace can be
    used as context managers and will use a unified logging format.

    The class automatically provides logging capabilities for both class methods and instance methods.
    For example:

    .. code-block:: python

        from mindtrace.core import Mindtrace

        class MyClass(Mindtrace):
            def __init__(self):
                super().__init__()

            def instance_method(self):
                self.logger.info(f"Using logger: {self.logger.name}")  # Using logger: mindtrace.my_module.MyClass

            @classmethod
            def class_method(cls):
                cls.logger.info(f"Using logger: {cls.logger.name}")  # Using logger: mindtrace.my_module.MyClass

    The logging functionality is automatically provided through the MindtraceMeta metaclass,
    which ensures consistent logging behavior across all method types.
    """

    def __init__(self, suppress: bool = False, *, config_overrides: SettingsLike | None = None, **kwargs):
        """
        Initialize the Mindtrace object.

        Args:
            suppress: Whether to suppress exceptions in context manager use.
            config_overrides: Additional settings to override the default config.
            **kwargs: Additional keyword arguments. Logger-related kwargs are passed to `get_logger`.
                Valid logger kwargs: log_dir, logger_level, stream_level, file_level,
                file_mode, propagate, max_bytes, backup_count
        """
        # Initialize parent classes first (cooperative inheritance)
        self.config = CoreConfig(config_overrides)
        try:
            super().__init__(**kwargs)
        except TypeError:
            # If parent classes don't accept some kwargs, try without logger-specific ones
            logger_param_names = {
                "log_dir",
                "logger_level",
                "stream_level",
                "file_level",
                "file_mode",
                "propagate",
                "max_bytes",
                "backup_count",
                "use_structlog",
                "structlog_json",
                "structlog_pre_chain",
                "structlog_processors",
                "structlog_renderer",
                "structlog_bind",
            }
            remaining_kwargs = {k: v for k, v in kwargs.items() if k not in logger_param_names}
            try:
                super().__init__(**remaining_kwargs)
            except TypeError:
                # If that still fails, try with no kwargs
                super().__init__()

        # Set Mindtrace-specific attributes
        self.suppress = suppress

        # Filter logger-specific kwargs for logger setup
        logger_param_names = {
            "log_dir",
            "logger_level",
            "stream_level",
            "file_level",
            "file_mode",
            "propagate",
            "max_bytes",
            "backup_count",
            "use_structlog",
            "structlog_json",
            "structlog_pre_chain",
            "structlog_processors",
            "structlog_renderer",
            "structlog_bind",
        }
        logger_kwargs = {k: v for k, v in kwargs.items() if k in logger_param_names}

        # Store logger kwargs in the class for class-level logger
        type(self)._logger_kwargs = logger_kwargs

        # Set up the logger
        self.logger = get_logger(self.unique_name, **logger_kwargs)

    @property
    def unique_name(self) -> str:
        return self.__module__ + "." + type(self).__name__

    @property
    def name(self) -> str:
        return type(self).__name__

    def __enter__(self):
        self.logger.debug(f"Initializing {self.name} as a context manager.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.debug(f"Exiting context manager for {self.name}.")
        if exc_type is not None:
            info = (exc_type, exc_val, exc_tb)
            self.logger.exception("Exception occurred", exc_info=info)
            return self.suppress
        return False

    @classmethod
    def autolog(
        cls,
        log_level=logging.DEBUG,
        prefix_formatter: Optional[Callable] = None,
        suffix_formatter: Optional[Callable] = None,
        exception_formatter: Optional[Callable] = None,
        self: Optional["Mindtrace"] = None,
        include_duration: bool = True,
        include_system_metrics: bool = False,
        system_metrics: Optional[list[str]] = None,
    ):
        """Decorator that adds logger.log calls to the decorated method before and after the method is called.

        By default, the autolog decorator will log the method name, arguments and keyword arguments before the method
        is called, and the method name and result after the method completes. This behavior can be modified by passing
        in prefix and suffix formatters.

        The autolog decorator will also catch and log all Exceptions, re-raising any exception after logging it. The
        behavior for autologging exceptions can be modified by passing in an exception_formatter.

        The autolog decorator expects a logger to exist at self.logger, and hence can only be used by Mindtrace
        subclasses or classes that have a logger attribute.

        Args:
            log_level: The log_level passed to logger.log().
            prefix_formatter: The formatter used to log the command before the wrapped method runs. The prefix_formatter
                will be given (and must accept) three arguments, in the following order:
                - function: The function being wrapped.
                - args: The args passed into the function.
                - kwargs: The kwargs passed into the function.
            suffix_formatter: The formatter used to log the command after the wrapped method runs. The suffix_formatter
                will be given (and must accept) two arguments, in the following order:
                - function: The function being wrapped.
                - result: The result returned from the wrapped method.
            exception_formatter: The formatter used to log any errors. The exception_formatter will be given (and must
                accept) three arguments, in the following order:
                - function: The function being wrapped.
                - error: The caught Exception.
                - stack trace: The stack trace, as provided by traceback.format_exc().
            self: The instance of the class that the method is being called on. Self only needs to be passed in if the
                wrapped method does not have self as the first argument. Refer to the example below for more details.
            include_duration: If True, append the duration of the wrapped method to each log record.
            include_system_metrics: If True, append a snapshot of system metrics to each log record.
            system_metrics: Optional list of metric names from SystemMetricsCollector.AVAILABLE_METRICS to include. If
                None, include all available metrics.


        Example::

            from mindtrace.core import Mindtrace

            class MyClass(Mindtrace):
                def __init__(self):
                    super().__init__()

                @Mindtrace.autolog()
                def divide(self, arg1, arg2):
                    self.logger.info("We are about to divide")
                    result = arg1 / arg2
                    self.logger.info("We have divided")
                    return result

            my_instance = MyClass()
            my_instance.divide(1, 2)
            my_instance.divide(1, 0)

        The resulting log file should contain something similar to the following:

        .. code-block:: text

            MyClass - DEBUG - Calling divide with args: (1, 2) and kwargs: {}
            MyClass - INFO - We are about to divide
            MyClass - INFO - We have divided
            MyClass - DEBUG - Finished divide with result: 0.5
            MyClass - DEBUG - Calling divide with args: (1, 0) and kwargs: {}
            MyClass - INFO - We are about to divide
            MyClass - ERROR - division by zero
            Traceback (most recent call last):
            ...

        If the wrapped method does not have self as the first argument, self must be passed in as an argument to the
        autolog decorator.

        .. code-block:: python

            from mindtrace.core import Mindtrace

            class Calculator(Mindtrace):
                def __init__(self):
                    super().__init__()

                @Mindtrace.autolog()
                def add(self, a, b):
                    return a + b

                @Mindtrace.autolog(self=self)
                def multiply(x, y):
                    return x * y

            calc = Calculator()
            result = calc.add(5, 3)
            product = calc.multiply(4, 6)
        """
        prefix_formatter = ifnone(
            prefix_formatter,
            default=lambda function,
            args,
            kwargs: f"Operation {function.__name__} started with args: {args} and kwargs: {kwargs}",
        )
        suffix_formatter = ifnone(
            suffix_formatter,
            default=lambda function, result: f"Operation {function.__name__} completed with result: {result}",
        )
        exception_formatter = ifnone(
            exception_formatter,
            default=lambda function,
            e,
            stack_trace: f"Operation {function.__name__} failed with the following error: {e}\n{stack_trace}",
        )

        def decorator(function):
            is_async = inspect.iscoroutinefunction(function)

            # Check if we can use track_operation (requires structlog logger)
            def _can_use_track_operation(logger_obj):
                """Check if the logger supports structlog and we can use track_operation."""
                return hasattr(logger_obj, "bind") and hasattr(logger_obj, "log")

            # If we can use track_operation, use it for cleaner implementation
            if self is None:
                # For instance methods, we need to check the logger at runtime
                def _get_logger_and_use_track_operation(instance):
                    if _can_use_track_operation(instance.logger):
                        # Use track_operation for structlog loggers
                        from mindtrace.core.logging.logger import track_operation
                        
                        # Extract argument names for include_args
                        sig = inspect.signature(function)
                        param_names = list(sig.parameters.keys())
                        # Remove 'self' if present
                        if param_names and param_names[0] == 'self':
                            param_names = param_names[1:]
                        
                        return track_operation(
                            name=function.__name__,
                            logger=instance.logger,
                            include_args=param_names,
                            log_level=log_level,
                            include_system_metrics=include_system_metrics,
                            system_metrics=system_metrics,
                        )
                    return None
            else:
                # For static methods, check the provided logger
                if _can_use_track_operation(self.logger):
                    from mindtrace.core.logging.logger import track_operation
                    
                    # Extract argument names for include_args
                    sig = inspect.signature(function)
                    param_names = list(sig.parameters.keys())
                    
                    return track_operation(
                        name=function.__name__,
                        logger=self.logger,
                        include_args=param_names,
                        log_level=log_level,
                        include_system_metrics=include_system_metrics,
                        system_metrics=system_metrics,
                    )

            # Fallback to original implementation for non-structlog loggers
            metrics_collector = (
                SystemMetricsCollector(metrics_to_collect=system_metrics) if include_system_metrics else None
            )

            # _emit_log handles both structured and stdlib emission; no separate message transformers needed

            def _emit_log(
                level: int,
                logger_obj,
                event_text: str,
                *,
                started_at: float | None = None,
                is_error: bool = False,
                add_duration: bool = False,
                function=None,
                args=None,
                kwargs=None,
                result=None,
                exception=None,
                stack_trace=None,
            ):
                """Emit a log entry, using structured keys if logger is a structlog BoundLogger."""
                # Collect metrics snapshot if enabled
                metrics_snapshot = None
                if metrics_collector is not None:
                    try:
                        metrics_snapshot = metrics_collector()
                    except Exception:
                        metrics_snapshot = None

                # Detect structlog by presence of 'bind'
                is_structlog = hasattr(logger_obj, "bind")

                if is_structlog:
                    # For structlog, use structured fields and concise messages
                    fields = {}

                    # Add function name and status
                    if function is not None:
                        fields["function_name"] = function.__name__
                        if is_error:
                            fields["status"] = "failed"
                        elif result is not None:
                            fields["status"] = "completed"
                        else:
                            fields["status"] = "started"

                    # Add args and kwargs as separate dictionary fields
                    if args is not None:
                        fields["args"] = list(args)
                    if kwargs is not None:
                        fields["kwargs"] = dict(kwargs)

                    # Add result for completed operations
                    if result is not None:
                        fields["result"] = result

                    # Add exception details for failed operations
                    if exception is not None:
                        fields["exception"] = str(exception)
                        fields["exception_type"] = type(exception).__name__
                    if stack_trace is not None:
                        fields["stack_trace"] = stack_trace

                    # Add metrics and duration
                    if metrics_snapshot is not None:
                        fields["metrics"] = metrics_snapshot
                    if include_duration and add_duration and started_at is not None:
                        try:
                            fields["duration_ms"] = (time.perf_counter() - started_at) * 1000.0
                        except Exception:
                            pass

                    # Create concise event message for structlog
                    if function is not None:
                        if is_error:
                            event_msg = f"{function.__name__} failed"
                        elif result is not None:
                            event_msg = f"{function.__name__} completed"
                        else:
                            event_msg = f"{function.__name__} started"
                    else:
                        event_msg = event_text

                    if is_error:
                        try:
                            logger_obj.error(event_msg, **fields)
                            return
                        except Exception:
                            pass
                    try:
                        logger_obj.log(level, event_msg, **fields)
                        return
                    except Exception:
                        # Fallback to stdlib-style string if structured emit fails
                        pass

                # Stdlib fallback: use original formatters and append into message (UNCHANGED)
                msg = event_text
                if metrics_snapshot is not None:
                    msg = f"{msg} | metrics={metrics_snapshot}"
                if include_duration and add_duration and started_at is not None:
                    try:
                        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                        msg = f"{msg} | duration_ms={elapsed_ms:.2f}"
                    except Exception:
                        pass
                if is_error:
                    logger_obj.error(msg)
                else:
                    logger_obj.log(level, msg)

            if self is None:
                if is_async:

                    @wraps(function)
                    async def wrapper(self, *args, **kwargs):
                        # Try to use track_operation if logger supports it
                        track_op = _get_logger_and_use_track_operation(self)
                        if track_op is not None:
                            # Use track_operation for structlog loggers
                            decorated_func = track_op(function)
                            result = await decorated_func(self, *args, **kwargs)
                            return result
                        else:
                            # Fallback to original implementation for non-structlog loggers
                            started_at = time.perf_counter() if include_duration else None
                            _emit_log(
                                log_level,
                                self.logger,
                                prefix_formatter(function, args, kwargs),
                                started_at=started_at,
                                is_error=False,
                                add_duration=False,
                                function=function,
                                args=args,
                                kwargs=kwargs,
                            )
                            try:
                                result = await function(self, *args, **kwargs)
                            except Exception as e:
                                _emit_log(
                                    log_level,
                                    self.logger,
                                    exception_formatter(function, e, traceback.format_exc()),
                                    started_at=started_at,
                                    is_error=True,
                                    add_duration=True,
                                    function=function,
                                    args=args,
                                    kwargs=kwargs,
                                    exception=e,
                                    stack_trace=traceback.format_exc(),
                                )
                                raise
                            else:
                                _emit_log(
                                    log_level,
                                    self.logger,
                                    suffix_formatter(function, result),
                                    started_at=started_at,
                                    is_error=False,
                                    add_duration=True,
                                    function=function,
                                    args=args,
                                    kwargs=kwargs,
                                    result=result,
                                )
                                return result
                else:

                    @wraps(function)
                    def wrapper(self, *args, **kwargs):
                        # Try to use track_operation if logger supports it
                        track_op = _get_logger_and_use_track_operation(self)
                        if track_op is not None:
                            # Use track_operation for structlog loggers
                            decorated_func = track_op(function)
                            result = decorated_func(self, *args, **kwargs)
                            return result
                        else:
                            # Fallback to original implementation for non-structlog loggers
                            started_at = time.perf_counter() if include_duration else None
                            _emit_log(
                                log_level,
                                self.logger,
                                prefix_formatter(function, args, kwargs),
                                started_at=started_at,
                                is_error=False,
                                add_duration=False,
                                function=function,
                                args=args,
                                kwargs=kwargs,
                            )
                            try:
                                result = function(self, *args, **kwargs)
                            except Exception as e:
                                _emit_log(
                                    log_level,
                                    self.logger,
                                    exception_formatter(function, e, traceback.format_exc()),
                                    started_at=started_at,
                                    is_error=True,
                                    add_duration=True,
                                    function=function,
                                    args=args,
                                    kwargs=kwargs,
                                    exception=e,
                                    stack_trace=traceback.format_exc(),
                                )
                                raise
                            else:
                                _emit_log(
                                    log_level,
                                    self.logger,
                                    suffix_formatter(function, result),
                                    started_at=started_at,
                                    is_error=False,
                                    add_duration=True,
                                    function=function,
                                    args=args,
                                    kwargs=kwargs,
                                    result=result,
                                )
                                return result

            else:
                # For static methods, check if we can use track_operation
                track_op = None
                if _can_use_track_operation(self.logger):
                    from mindtrace.core.logging.logger import track_operation
                    
                    # Extract argument names for include_args
                    sig = inspect.signature(function)
                    param_names = list(sig.parameters.keys())
                    
                    track_op = track_operation(
                        name=function.__name__,
                        logger=self.logger,
                        include_args=param_names,
                        log_level=log_level,
                        include_system_metrics=include_system_metrics,
                        system_metrics=system_metrics,
                    )

                if is_async:

                    @wraps(function)
                    async def wrapper(*args, **kwargs):
                        if track_op is not None:
                            # Use track_operation for structlog loggers
                            decorated_func = track_op(function)
                            result = await decorated_func(*args, **kwargs)
                            return result
                        else:
                            # Fallback to original implementation for non-structlog loggers
                            started_at = time.perf_counter() if include_duration else None
                            _emit_log(
                                log_level,
                                self.logger,
                                prefix_formatter(function, args, kwargs),
                                started_at=started_at,
                                is_error=False,
                                add_duration=False,
                                function=function,
                                args=args,
                                kwargs=kwargs,
                            )
                            try:
                                result = await function(*args, **kwargs)
                            except Exception as e:
                                _emit_log(
                                    log_level,
                                    self.logger,
                                    exception_formatter(function, e, traceback.format_exc()),
                                    started_at=started_at,
                                    is_error=True,
                                    add_duration=True,
                                    function=function,
                                    args=args,
                                    kwargs=kwargs,
                                    exception=e,
                                    stack_trace=traceback.format_exc(),
                                )
                                raise
                            else:
                                _emit_log(
                                    log_level,
                                    self.logger,
                                    suffix_formatter(function, result),
                                    started_at=started_at,
                                    is_error=False,
                                    add_duration=True,
                                    function=function,
                                    args=args,
                                    kwargs=kwargs,
                                    result=result,
                                )
                                return result
                else:

                    @wraps(function)
                    def wrapper(*args, **kwargs):
                        if track_op is not None:
                            # Use track_operation for structlog loggers
                            decorated_func = track_op(function)
                            result = decorated_func(*args, **kwargs)
                            return result
                        else:
                            # Fallback to original implementation for non-structlog loggers
                            started_at = time.perf_counter() if include_duration else None
                            _emit_log(
                                log_level,
                                self.logger,
                                prefix_formatter(function, args, kwargs),
                                started_at=started_at,
                                is_error=False,
                                add_duration=False,
                                function=function,
                                args=args,
                                kwargs=kwargs,
                            )
                            try:
                                result = function(*args, **kwargs)
                            except Exception as e:
                                _emit_log(
                                    log_level,
                                    self.logger,
                                    exception_formatter(function, e, traceback.format_exc()),
                                    started_at=started_at,
                                    is_error=True,
                                    add_duration=True,
                                    function=function,
                                    args=args,
                                    kwargs=kwargs,
                                    exception=e,
                                    stack_trace=traceback.format_exc(),
                                )
                                raise
                            else:
                                _emit_log(
                                    log_level,
                                    self.logger,
                                    suffix_formatter(function, result),
                                    started_at=started_at,
                                    is_error=False,
                                    add_duration=True,
                                    function=function,
                                    args=args,
                                    kwargs=kwargs,
                                    result=result,
                                )
                                return result

            return wrapper

        return decorator


class MindtraceABCMeta(MindtraceMeta, ABCMeta):
    """Metaclass that combines MindtraceMeta and ABC metaclasses.

    This metaclass resolves metaclass conflicts when creating classes that need to be both
    abstract (using ABC) and have MindtraceMeta functionality. Python only allows a class to
    have one metaclass, so this combined metaclass allows classes to inherit from both
    Mindtrace class and ABC simultaneously.

    Without this combined metaclass, trying to create a class that inherits from both Mindtrace class
    and ABC would raise a metaclass conflict error since they each have different metaclasses.
    """

    pass


class MindtraceABC(Mindtrace, ABC, metaclass=MindtraceABCMeta):
    """Abstract base class combining Mindtrace class functionality with ABC support.

    This class enables creating abstract classes that also have access to all Mindtrace features
    such as logging, configuration, and context management. Use this class instead of
    Mindtrace when you need to define abstract methods or properties in your class.

    Example:
        from mindtrace.core import MindtraceABC
        from abc import abstractmethod

        class MyAbstractService(MindtraceABC):
            def __init__(self):
                super().__init__()

            @abstractmethod
            def process_data(self, data):
                '''Must be implemented by concrete subclasses.'''
                pass

    Note:
        Without this class, attempting to create a class that inherits from both Mindtrace class and ABC
        would fail due to metaclass conflicts. MindtraceABC resolves this by using the CombinedABCMeta.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
