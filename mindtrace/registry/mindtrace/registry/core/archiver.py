from abc import abstractmethod
from typing import Any

from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import Mindtrace, MindtraceABC


class ArchiverMeta(type(Mindtrace), type(BaseMaterializer)):
    pass


class Archiver(Mindtrace, BaseMaterializer, metaclass=ArchiverMeta):
    ASSOCIATED_TYPES = (Any, )  # List of types that can be archived
    ASSOCIATED_ARTIFACT_TYPES = (Any, )  # List of artifact types that can be archived

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @abstractmethod
    def save(self, data: Any):
        raise NotImplementedError("Archiver save method not implemented")

    @classmethod
    @abstractmethod
    def load(cls, data: Any):
        raise NotImplementedError("Archiver load method not implemented")
