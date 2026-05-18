"""Tests for the Materializer Protocol and legacy zenml materializer-string aliasing."""

import json
import os
from pathlib import Path
from typing import Any, Type

import pytest
from pydantic import BaseModel

from mindtrace.registry import BaseMaterializer, Materializer, Registry
from mindtrace.registry.core._registry_core import _LEGACY_MATERIALIZER_ALIASES, _resolve_materializer_string


class _PydanticSample(BaseModel):
    """Module-scope pydantic subclass so ``Registry.load`` can re-import its class."""

    x: int
    y: str


# ────────────────────────────────────────────────────────────────────────────────
# Protocol structural checks
# ────────────────────────────────────────────────────────────────────────────────


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


def test_protocol_accepts_foreign_classes_without_inheritance():
    """A class with the right shape satisfies Materializer even without inheriting BaseMaterializer."""
    instance = _ForeignMaterializer("/tmp/x")
    assert isinstance(instance, Materializer)
    assert not isinstance(instance, BaseMaterializer)


def test_protocol_rejects_classes_missing_methods():
    class Incomplete:
        def __init__(self, uri: str, **_: Any):
            self.uri = uri

        def save(self, data: Any) -> None: ...

        # `load` deliberately missing

    assert not isinstance(Incomplete("/tmp/x"), Materializer)


def test_base_materializer_satisfies_protocol():
    class Concrete(BaseMaterializer):
        def save(self, data: Any) -> None: ...

        def load(self, data_type: Type[Any]) -> Any:
            return None

    assert isinstance(Concrete("/tmp/x"), Materializer)


# ────────────────────────────────────────────────────────────────────────────────
# Foreign materializers integrate with the Registry via registration + dispatch
# ────────────────────────────────────────────────────────────────────────────────


class StringHolder:
    """Plain class round-tripped through the registry by a foreign materializer."""

    def __init__(self, value: str):
        self.value = value


def test_registry_dispatches_to_foreign_materializer(tmp_path: Path):
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    reg.register_materializer(
        StringHolder,
        f"{__name__}.StringHolderMaterializer",
    )
    obj = StringHolder("hello")
    reg.save("holder", obj)
    loaded = reg.load("holder")
    assert isinstance(loaded, StringHolder)
    assert loaded.value == "hello"


class StringHolderMaterializer:
    """A materializer for StringHolder that does NOT inherit BaseMaterializer."""

    def __init__(self, uri: str, **_: Any):
        self.uri = uri

    def save(self, data: StringHolder) -> None:
        Path(self.uri).mkdir(parents=True, exist_ok=True)
        with open(os.path.join(self.uri, "data.json"), "w") as f:
            json.dump({"value": data.value}, f)

    def load(self, data_type: Type[Any]) -> StringHolder:
        with open(os.path.join(self.uri, "data.json")) as f:
            payload = json.load(f)
        return StringHolder(value=payload["value"])


# ────────────────────────────────────────────────────────────────────────────────
# Legacy zenml materializer-string alias map
# ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "legacy, expected",
    list(_LEGACY_MATERIALIZER_ALIASES.items()),
)
def test_resolve_materializer_string_handles_all_documented_aliases(legacy: str, expected: str):
    assert _resolve_materializer_string(legacy) == expected


def test_resolve_materializer_string_is_idempotent_for_unknown_strings():
    s = "some.unknown.path.Materializer"
    assert _resolve_materializer_string(s) == s


def test_resolve_materializer_string_none_passes_through():
    assert _resolve_materializer_string(None) is None


def test_legacy_zenml_materializer_string_resolves_in_materialize_from_bytes(tmp_path: Path):
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    out = reg.materialize_from_bytes(
        b"abc",
        object_class="builtins.bytes",
        materializer="zenml.materializers.BytesMaterializer",
    )
    assert out == b"abc"


def test_pydantic_subclass_dispatches_via_basemodel_mro(tmp_path: Path):
    """``pydantic.main.BaseModel`` must be registered so MRO-based dispatch hits user subclasses."""
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    reg.save("m", _PydanticSample(x=7, y="hi"))
    loaded = reg.load("m")
    assert isinstance(loaded, _PydanticSample)
    assert loaded.x == 7
    assert loaded.y == "hi"


def test_legacy_zenml_metadata_loads_via_alias_map(tmp_path: Path):
    """Simulate a registry whose stored metadata still references zenml.* materializers."""
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    version = reg.save("greeting", "hello")

    # Rewrite the stored metadata to use a legacy zenml materializer string.
    meta_path = reg.backend._object_metadata_path("greeting", version)
    import yaml

    with open(meta_path) as f:
        meta = yaml.safe_load(f)
    meta["materializer"] = "zenml.materializers.built_in_materializer.BuiltInMaterializer"
    with open(meta_path, "w") as f:
        yaml.safe_dump(meta, f)

    # Drop the in-memory cache so the next load goes through the alias path.
    reg._core._materializer_cache.clear()

    assert reg.load("greeting") == "hello"
