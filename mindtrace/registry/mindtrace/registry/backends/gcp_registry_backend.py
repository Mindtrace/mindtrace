from typing import TypeVar

from pydantic import BaseModel

from mindtrace.registry.backends.registry_backend import RegistryBackend

T = TypeVar("T")


class GCPRegistryBackend(RegistryBackend):  # pragma: no cover
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def push(self, name: str, object: T, version: str | None = None):
        raise NotImplementedError("Registry push method not implemented")

    def pull(self, name: str, version: str | None = None) -> T:
        raise NotImplementedError("Registry pull method not implemented")

    def delete(self, name: str, version: str | None = None):
        raise NotImplementedError("Registry delete method not implemented")

    def info(self, name: str = None, version: str = "latest") -> BaseModel:
        raise NotImplementedError("Registry info method not implemented")
