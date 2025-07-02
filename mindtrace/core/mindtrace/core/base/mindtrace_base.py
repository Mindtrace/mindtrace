from abc import ABC, ABCMeta

from mindtrace.core.config import Config
from mindtrace.core.logging import Logger


class MindtraceMeta(type):
    pass


class Mindtrace(metaclass=MindtraceMeta):
    """Base class for Mindtrace components."""

    def __init__(self):
        self.config = Config()
        self.logger = Logger()


class MindtraceABCMeta(MindtraceMeta, ABCMeta):
    pass


class MindtraceABC(ABC, metaclass=MindtraceABCMeta):
    """Base class for Mindtrace-derived abstract classes."""
    
    def __init__(self):
        self.config = Config()
        self.logger = Logger()
