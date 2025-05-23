from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from mindtrace.core import MindtraceABC

T = TypeVar("T")


class RegistryBackend(MindtraceABC):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @abstractmethod
    def push(self, name: str, object: T, version: str | None = None):
        raise NotImplementedError("Registry push method not implemented")

    @abstractmethod
    def pull(self, name: str, version: str | None = None) -> T:
        raise NotImplementedError("Registry pull method not implemented")

    @abstractmethod
    def delete(self, name: str, version: str | None = None):
        raise NotImplementedError("Registry delete method not implemented")

    @abstractmethod
    def info(self, name: str = None, version: str = "latest") -> BaseModel:
        raise NotImplementedError("Registry info method not implemented")
        