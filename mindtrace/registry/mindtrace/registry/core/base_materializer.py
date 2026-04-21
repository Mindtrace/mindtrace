from typing import Any, Type


class BaseMaterializer:
    """Base class for materializers.

    Provides the minimal interface for serializing/deserializing objects:
    - ``save(data)`` to persist an object to ``self.uri``
    - ``load(data_type)`` to restore an object from ``self.uri``
    """

    def __init__(self, uri: str, **kwargs):
        self.uri = uri

    def save(self, data: Any) -> None:
        raise NotImplementedError

    def load(self, data_type: Type[Any]) -> Any:
        raise NotImplementedError
