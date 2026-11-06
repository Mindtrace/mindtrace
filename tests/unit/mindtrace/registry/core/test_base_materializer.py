"""Behavioral unit tests for core.base_materializer."""

import os
from typing import Any, Type

from mindtrace.registry import BaseMaterializer, Materializer


class _ForeignMaterializer:
    """A materializer-shaped class that does NOT inherit from BaseMaterializer."""

    def __init__(self, uri: str, **_: Any):
        self.uri = uri

    def save(self, data: Any) -> None:
        with open(os.path.join(self.uri, "payload.txt"), "w") as f:
            f.write(str(data))

    def load(self, data_type: Type[Any]) -> Any:
        with open(os.path.join(self.uri, "payload.txt")) as f:
            return data_type(f.read())


class TestMaterializerProtocol:
    def test_protocol_accepts_foreign_classes_without_inheritance(self):
        """A class with the right shape satisfies Materializer even without inheriting BaseMaterializer."""
        instance = _ForeignMaterializer("/tmp/x")
        assert isinstance(instance, Materializer)
        assert not isinstance(instance, BaseMaterializer)

    def test_protocol_rejects_classes_missing_methods(self):
        class Incomplete:
            def __init__(self, uri: str, **_: Any):
                self.uri = uri

            def save(self, data: Any) -> None: ...

            # `load` deliberately missing

        assert not isinstance(Incomplete("/tmp/x"), Materializer)

    def test_base_materializer_satisfies_protocol(self):
        class Concrete(BaseMaterializer):
            def save(self, data: Any) -> None: ...

            def load(self, data_type: Type[Any]) -> Any:
                return None

        assert isinstance(Concrete("/tmp/x"), Materializer)
