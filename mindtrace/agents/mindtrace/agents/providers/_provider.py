from __future__ import annotations

from abc import abstractmethod
from typing import Generic, TypeVar

from mindtrace.core import MindtraceABC

from ..profiles import ModelProfile

InterfaceClient = TypeVar("InterfaceClient")


class Provider(MindtraceABC, Generic[InterfaceClient]):
    _client: InterfaceClient

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError()

    @property
    @abstractmethod
    def base_url(self) -> str:
        raise NotImplementedError()

    @property
    @abstractmethod
    def client(self) -> InterfaceClient:
        raise NotImplementedError()

    def model_profile(self, model_name: str) -> ModelProfile | None:
        return None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, base_url={self.base_url!r})"


__all__ = [
    "InterfaceClient",
    "Provider",
]
