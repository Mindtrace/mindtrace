from __future__ import annotations

from abc import abstractmethod

from mindtrace.core import MindtraceABC


class BrokerConnectionBase(MindtraceABC):
    """Abstract base class for broker connections."""

    def __init__(self, *args, **kwargs):
        super().__init__()

    @abstractmethod
    def connect(self):
        raise NotImplementedError

    @abstractmethod
    def is_connected(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def close(self):
        raise NotImplementedError

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
