"""Mindtrace base classes. Provides unified configuration, logging and context management."""

from abc import ABC

from mindtrace.core.config import Config
from mindtrace.core.logging.logger import get_logger


class _ClassOrInstanceAttr:
    """Descriptor providing a lazy class-level default with per-instance override.

    When accessed on a class (``cls.logger``), returns a lazily created
    value cached on the class.  When accessed on an instance
    (``self.logger``), returns the instance-level value if one has been
    set, otherwise falls through to the class-level default.
    """

    def __init__(self, factory):
        self._factory = factory

    def __set_name__(self, owner, name):
        self._name = name
        self._cls_attr = f"_cls_{name}"

    def __get__(self, obj, cls):
        if obj is not None:
            val = obj.__dict__.get(self._name)
            if val is not None:
                return val
        cached = cls.__dict__.get(self._cls_attr)
        if cached is not None:
            return cached
        val = self._factory(cls)
        setattr(cls, self._cls_attr, val)
        return val

    def __set__(self, obj, value):
        obj.__dict__[self._name] = value

    def __delete__(self, obj):
        obj.__dict__.pop(self._name, None)


class _ClassOrInstanceProperty:
    """Descriptor that works as a property on both classes and instances.

    On a class: computes from ``cls``.
    On an instance: computes from ``type(obj)``.
    """

    def __init__(self, func):
        self._func = func

    def __get__(self, obj, cls):
        return self._func(cls if obj is None else type(obj))


class Mindtrace:
    """Base class for all Mindtrace components.

    Provides:
    - ``self.logger`` / ``cls.logger`` — automatic per-class logging
    - ``self.config`` / ``cls.config`` — centralised configuration via :class:`CoreConfig`
    - Context manager support (``with`` statement)
    - ``self.name`` / ``cls.name`` — identity helpers
    - ``self.unique_name`` / ``cls.unique_name`` — fully qualified identity

    Usage::

        class MyComponent(Mindtrace):
            def run(self):
                self.logger.info("running")
                temp = self.config.MINDTRACE_DIR_PATHS.TEMP_DIR
    """

    logger = _ClassOrInstanceAttr(lambda cls: get_logger(f"{cls.__module__}.{cls.__name__}"))
    config = _ClassOrInstanceAttr(lambda cls: Config())
    unique_name = _ClassOrInstanceProperty(lambda cls: f"{cls.__module__}.{cls.__name__}")
    name = _ClassOrInstanceProperty(lambda cls: cls.__name__)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = get_logger(self.unique_name)
        self.config = Config()

    def __enter__(self):
        self.logger.debug(f"Initializing {self.name} as a context manager.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.debug(f"Exiting context manager for {self.name}.")
        if exc_type is not None:
            self.logger.exception("Exception occurred", exc_info=(exc_type, exc_val, exc_tb))
        return False


class MindtraceABC(Mindtrace, ABC):
    """Abstract base class combining :class:`Mindtrace` with :class:`ABC`.

    Use instead of ``Mindtrace`` when you need abstract methods::

        from abc import abstractmethod

        class Backend(MindtraceABC):
            @abstractmethod
            def connect(self): ...
    """

    pass
