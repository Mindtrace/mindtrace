"""Mindtrace class. Provides unified configuration, logging and context management."""

import inspect
import logging
import traceback
from abc import ABC, ABCMeta
from functools import wraps
from typing import Callable, Optional

from mindtrace.core.config import CoreConfig, SettingsLike
from mindtrace.core.logging.logger import get_logger
from mindtrace.core.utils import ifnone


class MindtraceMeta(type):
    """Metaclass for Mindtrace class.

    The MindtraceMeta metaclass enables classes deriving from Mindtrace to automatically use the same default logger within
    class methods as it does within instance methods. i.e. consider the following class:

    Usage:
        ```python
        from mindtrace.core import Mindtrace

        class MyClass(Mindtrace):
            def __init__(self):
                super().__init__()

            def instance_method(self):
                self.logger.info(f"Using logger: {self.logger.name}")  # Using logger: mindtrace.my_module.MyClass

            @classmethod
            def class_method(cls):
                cls.logger.info(f"Using logger: {cls.logger.name}")  # Using logger: mindtrace.my_module.MyClass
        ```
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
        if (
            cls._logger is not None
            and cls._cached_logger_kwargs is not None
            and cls._cached_logger_kwargs != current_kwargs
        ):
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

    Usage:
        ```python
        from mindtrace.core import Mindtrace

        class MyClass(Mindtrace):
            def __init__(self):
                super().__init__()

            def instance_method(self):
                self.logger.info(f"Using logger: {self.logger.name}")  # Using logger: mindtrace.my_module.MyClass

            @classmethod
            def class_method(cls):
                cls.logger.info(f"Using logger: {cls.logger.name}")  # Using logger: mindtrace.my_module.MyClass
        ```
    The logging functionality is automatically provided through the MindtraceMeta metaclass,
    which ensures consistent logging behavior across all method types.
    """

    _LOGGER_PARAM_NAMES = frozenset({
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
    })

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
        self.config = CoreConfig(config_overrides)

        # Separate logger kwargs from remaining kwargs before passing to super
        logger_kwargs = {k: v for k, v in kwargs.items() if k in self._LOGGER_PARAM_NAMES}
        remaining_kwargs = {k: v for k, v in kwargs.items() if k not in self._LOGGER_PARAM_NAMES}

        # Initialize parent classes (cooperative inheritance)
        try:
            super().__init__(**remaining_kwargs)
        except TypeError:
            super().__init__()

        self.suppress = suppress

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
            prefix_formatter: The formatter used to log the command before the wrapped method runs.
            suffix_formatter: The formatter used to log the command after the wrapped method runs.
            exception_formatter: The formatter used to log any errors.
            self: The instance of the class that the method is being called on. Self only needs to be passed in if the
                wrapped method does not have self as the first argument (e.g., FastAPI route decorators).
        """
        prefix_formatter = ifnone(
            prefix_formatter,
            default=lambda function, args, kwargs: (
                f"Calling {function.__name__} with args: {args} and kwargs: {kwargs}"
            ),
        )
        suffix_formatter = ifnone(
            suffix_formatter, default=lambda function, result: f"Finished {function.__name__} with result: {result}"
        )
        exception_formatter = ifnone(
            exception_formatter,
            default=lambda function, e, stack_trace: (
                f"{function.__name__} failed to complete with the following error: {e}\n{stack_trace}"
            ),
        )

        def decorator(function):
            is_async = inspect.iscoroutinefunction(function)

            if self is not None:
                # Logger source is the captured `self` from the decorator argument
                if is_async:
                    @wraps(function)
                    async def wrapper(*args, **kwargs):
                        self.logger.log(log_level, prefix_formatter(function, args, kwargs))
                        try:
                            result = await function(*args, **kwargs)
                        except Exception as e:
                            self.logger.error(exception_formatter(function, e, traceback.format_exc()))
                            raise
                        self.logger.log(log_level, suffix_formatter(function, result))
                        return result
                else:
                    @wraps(function)
                    def wrapper(*args, **kwargs):
                        self.logger.log(log_level, prefix_formatter(function, args, kwargs))
                        try:
                            result = function(*args, **kwargs)
                        except Exception as e:
                            self.logger.error(exception_formatter(function, e, traceback.format_exc()))
                            raise
                        self.logger.log(log_level, suffix_formatter(function, result))
                        return result
            else:
                # Logger source is the first argument (self) of the bound method
                if is_async:
                    @wraps(function)
                    async def wrapper(instance, *args, **kwargs):
                        instance.logger.log(log_level, prefix_formatter(function, args, kwargs))
                        try:
                            result = await function(instance, *args, **kwargs)
                        except Exception as e:
                            instance.logger.error(exception_formatter(function, e, traceback.format_exc()))
                            raise
                        instance.logger.log(log_level, suffix_formatter(function, result))
                        return result
                else:
                    @wraps(function)
                    def wrapper(instance, *args, **kwargs):
                        instance.logger.log(log_level, prefix_formatter(function, args, kwargs))
                        try:
                            result = function(instance, *args, **kwargs)
                        except Exception as e:
                            instance.logger.error(exception_formatter(function, e, traceback.format_exc()))
                            raise
                        instance.logger.log(log_level, suffix_formatter(function, result))
                        return result

            return wrapper

        return decorator


class MindtraceABCMeta(MindtraceMeta, ABCMeta):
    """Metaclass that combines MindtraceMeta and ABC metaclasses.

    This metaclass resolves metaclass conflicts when creating classes that need to be both
    abstract (using ABC) and have MindtraceMeta functionality.
    """

    pass


class MindtraceABC(Mindtrace, ABC, metaclass=MindtraceABCMeta):
    """Abstract base class combining Mindtrace class functionality with ABC support.

    This class enables creating abstract classes that also have access to all Mindtrace features
    such as logging, configuration, and context management. Use this class instead of
    Mindtrace when you need to define abstract methods or properties in your class.

    Usage:
        ```python
        from mindtrace.core import MindtraceABC
        from abc import abstractmethod

        class MyAbstractService(MindtraceABC):
            def __init__(self):
                super().__init__()

            @abstractmethod
            def process_data(self, data):
                '''Must be implemented by concrete subclasses.'''
                pass
        ```
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
