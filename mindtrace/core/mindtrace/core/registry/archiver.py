from abc import abstractmethod
from typing import Type, Any, Set

from zenml.enums import ArtifactType
from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import Mindtrace, MindtraceMeta


class ArchiverMeta(MindtraceMeta, type(BaseMaterializer)):
    """Meta class for Archiver."""

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        return cls


class Archiver(Mindtrace, BaseMaterializer, metaclass=ArchiverMeta):
    """Base Archiver class for handling data persistence."""

    # Required by BaseMaterializer
    ASSOCIATED_TYPES: Set[Type] = {Any}
    ARTIFACT_TYPE: ArtifactType = ArtifactType.DATA

    def __init__(self, uri: str, *args, **kwargs):
        Mindtrace.__init__(self)
        BaseMaterializer.__init__(self, uri=uri, *args, **kwargs)
        self.logger.info(f"Archiver initialized at: {self.uri}")

    @abstractmethod
    def load(self, data_type: Type[Any]) -> Any:
        raise NotImplementedError("Subclasses must implement load().")

    @abstractmethod
    def save(self, obj: Any) -> None:
        raise NotImplementedError("Subclasses must implement save().")
