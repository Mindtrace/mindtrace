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

        Usage:
            ```python
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
            ```
        The resulting log file should contain something similar to the following:

        ```text

            MyClass - DEBUG - Calling divide with args: (1, 2) and kwargs: {}
            MyClass - INFO - We are about to divide
            MyClass - INFO - We have divided
            MyClass - DEBUG - Finished divide with result: 0.5
            MyClass - DEBUG - Calling divide with args: (1, 0) and kwargs: {}
            MyClass - INFO - We are about to divide
            MyClass - ERROR - division by zero
            Traceback (most recent call last):
            ...
        ```
        If the wrapped method does not have self as the first argument, self must be passed in as an argument to the
        autolog decorator.

        Usage:
            ```python
                from fastapi import FastAPI
                from mindtrace.core import Mindtrace

                class MyClass(Mindtrace):
                    def __init__():
                        super().__init__()

                    def create_app(self):
                        app_ = FastAPI()

                        @Mindtrace.autolog(self=self)  # self must be passed in as an argument as it is not captured in status()
                        @app_.post("/status")
                        def status():
                            return {"status": "Available"}

                        return app_

            ```
        """
        prefix_formatter = ifnone(
            prefix_formatter,
            default=lambda function,
            args,
            kwargs: f"Calling {function.__name__} with args: {args} and kwargs: {kwargs}",
        )
        suffix_formatter = ifnone(
            suffix_formatter, default=lambda function, result: f"Finished {function.__name__} with result: {result}"
        )
        exception_formatter = ifnone(
            exception_formatter,
            default=lambda function,
            e,
            stack_trace: f"{function.__name__} failed to complete with the following error: {e}\n{stack_trace}",
        )

        def decorator(function):
            is_async = inspect.iscoroutinefunction(function)

            if self is None:
                if is_async:

                    @wraps(function)
                    async def wrapper(self, *args, **kwargs):
                        self.logger.log(log_level, prefix_formatter(function, args, kwargs))
                        try:
                            result = await function(self, *args, **kwargs)
                        except Exception as e:
                            self.logger.error(exception_formatter(function, e, traceback.format_exc()))
                            raise
                        else:
                            self.logger.log(log_level, suffix_formatter(function, result))
                            return result
                else:

                    @wraps(function)
                    def wrapper(self, *args, **kwargs):
                        self.logger.log(log_level, prefix_formatter(function, args, kwargs))
                        try:
                            result = function(self, *args, **kwargs)
                        except Exception as e:
                            self.logger.error(exception_formatter(function, e, traceback.format_exc()))
                            raise
                        else:
                            self.logger.log(log_level, suffix_formatter(function, result))
                            return result

            else:
                if is_async:

                    @wraps(function)
                    async def wrapper(*args, **kwargs):
                        self.logger.log(log_level, prefix_formatter(function, args, kwargs))
                        try:
                            result = await function(*args, **kwargs)
                        except Exception as e:
                            self.logger.error(exception_formatter(function, e, traceback.format_exc()))
                            raise
                        else:
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
                        else:
                            self.logger.log(log_level, suffix_formatter(function, result))
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

    Note:
        Without this class, attempting to create a class that inherits from both Mindtrace class and ABC
        would fail due to metaclass conflicts. MindtraceABC resolves this by using the CombinedABCMeta.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
