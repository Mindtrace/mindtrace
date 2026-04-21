from abc import abstractmethod
from typing import Any, Type

from mindtrace.core import Mindtrace
from mindtrace.registry.core.base_materializer import BaseMaterializer


class Archiver(Mindtrace, BaseMaterializer):
    """Base Archiver class for handling data persistence."""

    def __init__(self, uri: str, *args, **kwargs):
        super().__init__(uri=uri, *args, **kwargs)
        self.logger.debug(f"Archiver initialized at: {uri}")

    @abstractmethod
    def save(self, data: Any):
        raise NotImplementedError("Subclasses must implement save().")

    @abstractmethod
    def load(self, data_type: Type[Any]) -> Any:
        raise NotImplementedError("Subclasses must implement load().")
