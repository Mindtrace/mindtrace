from abc import abstractmethod
from typing import Any, Set, Type

from zenml.enums import ArtifactType
from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import Mindtrace, MindtraceMeta


class ArchiverMeta(MindtraceMeta, type(BaseMaterializer)):
    """Meta class for Archiver."""

    pass


class Archiver(Mindtrace, BaseMaterializer, metaclass=ArchiverMeta):
    """Base Archiver class for handling data persistence."""

    # Required by BaseMaterializer
    ASSOCIATED_TYPES: Set[Type] = {Any}
    ASSOCIATED_ARTIFACT_TYPE: ArtifactType = ArtifactType.DATA

    def __init__(self, uri: str, *args, **kwargs):
        super().__init__(uri=uri, *args, **kwargs)
        self.logger.debug(f"Archiver initialized at: {uri}")

    @abstractmethod
    def save(self, data: Any):
        raise NotImplementedError("Subclasses must implement save().")

    @abstractmethod
    def load(self, data_type: Type[Any]) -> Any:
        raise NotImplementedError("Subclasses must implement load().")
