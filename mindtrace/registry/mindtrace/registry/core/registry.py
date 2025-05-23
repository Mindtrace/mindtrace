from typing import Type, TypeVar

from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import Mindtrace, ifnone
from mindtrace.registry import LocalRegistryBackend, RegistryBackend

T = TypeVar("T")


class Registry(Mindtrace):
    def __init__(self, backend: RegistryBackend = None, **kwargs):
        super().__init__(**kwargs)

        self.materializers: dict[Type[T], BaseMaterializer] = {}
        self.backend = ifnone(backend, default=LocalRegistryBackend())

    def save(self, name: str, object: T, materializer: BaseMaterializer = None, version: str = None):
        raise NotImplementedError("Registry save method not implemented")

    def load(self, name: str, version: str = None) -> T:
        raise NotImplementedError("Registry load method not implemented")
    
    
