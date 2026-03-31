from enum import Enum
from typing import Any, ClassVar, Tuple, Type


class ArtifactType(str, Enum):
    """Artifact type classification."""

    DATA = "data"
    MODEL = "model"


class BaseMaterializer:
    """Base class for materializers.

    Provides the minimal interface for serializing/deserializing objects:
    - ``save(data)`` to persist an object to ``self.uri``
    - ``load(data_type)`` to restore an object from ``self.uri``

    Subclasses must declare ``ASSOCIATED_TYPES`` and implement both methods.
    """

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = ()
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def __init__(self, uri: str, **kwargs):
        self.uri = uri

    def save(self, data: Any) -> None:
        raise NotImplementedError

    def load(self, data_type: Type[Any]) -> Any:
        raise NotImplementedError
