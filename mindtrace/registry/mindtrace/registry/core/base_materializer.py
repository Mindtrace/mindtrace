"""Materializer contract for the Registry.

The public contract is a :class:`Materializer` Protocol. Any class exposing
``uri``, ``save(data)``, and ``load(data_type)`` satisfies it without needing
to inherit from anything in mindtrace. The concrete :class:`BaseMaterializer`
is provided as a convenience starting point for in-tree implementations.
"""

from typing import Any, Protocol, Type, runtime_checkable


@runtime_checkable
class Materializer(Protocol):
    """Structural contract for objects that serialize to / deserialize from ``uri``."""

    uri: str

    def save(self, data: Any) -> None: ...

    def load(self, data_type: Type[Any]) -> Any: ...


class BaseMaterializer:
    """Minimal concrete base. Subclasses override :meth:`save` and :meth:`load`."""

    def __init__(self, uri: str, **_: Any):
        self.uri = uri

    def save(self, data: Any) -> None:
        raise NotImplementedError

    def load(self, data_type: Type[Any]) -> Any:
        raise NotImplementedError
