"""Class/string materializer inputs and persistent registrations, without remote services."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from mindtrace.registry import BuiltInMaterializer, Registry, Store
from mindtrace.registry.core._registry_core import _RegistryCore
from tests.registry_test_helpers import RevisionedIntMaterializer, materializer_path


class _SerializerMeta(type):
    """Distinguish a materializer's class from its metaclass."""


class ForeignIntMaterializer(metaclass=_SerializerMeta):
    """An importable materializer that does not inherit any Mindtrace base."""

    def __init__(self, uri: str):
        self.uri = uri

    def save(self, data: int) -> None:
        Path(self.uri, "number.txt").write_text(str(data))

    def load(self, data_type: type) -> int:
        return int(Path(self.uri, "number.txt").read_text())


@pytest.fixture(params=["local", "cached", "store"])
def save_target(request, tmp_path):
    """Exercise local, cache-aware remote, and Store save entry points."""
    if request.param == "cached":
        registry = request.getfixturevalue("cached_mock_registry")
    else:
        registry = Registry(tmp_path / "registry", version_objects=True)
    target = Store(mounts={"local": registry}, default_mount="local") if request.param == "store" else registry
    return target, registry


@pytest.mark.parametrize("batch", [False, True], ids=["single", "batch"])
@pytest.mark.parametrize("reference", ["class", "path", "legacy", "automatic"])
def test_save_materializer_references_round_trip(save_target, batch, reference):
    target, registry = save_target
    materializer = {
        "class": BuiltInMaterializer,
        "path": materializer_path(BuiltInMaterializer),
        "legacy": "zenml.materializers.BuiltInMaterializer",
        "automatic": None,
    }[reference]
    names, values = (["first", "second"], [7, 8]) if batch else (["first"], [7])
    result = target.save(
        names if batch else names[0],
        values if batch else values[0],
        version="1.0.0",
        materializer=materializer,
    )
    if batch:
        assert result.success_count == len(names), result.errors
        assert result.failure_count == 0
        assert result.results == ["1.0.0"] * len(names)
    else:
        assert result == "1.0.0"
    for name, value in zip(names, values):
        assert target.load(name, version="1.0.0") == value
        # Inspect authoritative metadata, independently of cache-artifact fidelity.
        assert registry._core.info(name, "1.0.0")["materializer"] == materializer_path(BuiltInMaterializer)


@pytest.mark.parametrize("batch", [False, True], ids=["single", "batch"])
def test_save_rejects_materializer_instance_before_materialization(save_target, tmp_path, monkeypatch, batch):
    target, registry = save_target
    instance = BuiltInMaterializer(uri=str(tmp_path / "unused-instance"))
    instance.save = Mock(side_effect=AssertionError("must not use the supplied instance"))
    instantiate = Mock(side_effect=AssertionError("must not construct a replacement instance"))
    push = Mock(side_effect=AssertionError("must not commit an artifact"))
    monkeypatch.setattr("mindtrace.registry.core._registry_core.instantiate_target", instantiate)
    monkeypatch.setattr(registry.backend, "push", push)
    if batch:
        result = target.save(["first", "second"], [7, 8], version="1.0.0", materializer=instance)
        assert result.success_count == 0
        assert result.failure_count == 2
        assert result.results == [None, None]
        for error in result.errors.values():
            assert error["error"] == "TypeError"
            assert "class or fully qualified class-name string" in error["message"]
    else:
        with pytest.raises(TypeError, match="class or fully qualified class-name string"):
            target.save("first", 7, version="1.0.0", materializer=instance)
    instance.save.assert_not_called()
    instantiate.assert_not_called()
    push.assert_not_called()
    assert not Path(instance.uri).exists()
    assert not registry.has_object("first", "1.0.0")
    assert not registry.has_object("second", "1.0.0")


@pytest.mark.parametrize("reference", ["class", "path"])
def test_explicit_foreign_materializer_overrides_registration(tmp_path, reference):
    registry = Registry(tmp_path / "registry", version_objects=True)
    registry.register_materializer(int, RevisionedIntMaterializer)
    materializer = ForeignIntMaterializer if reference == "class" else materializer_path(ForeignIntMaterializer)
    hints = registry.serialization_hints_for_object(7, materializer=materializer)
    assert hints == {"class": "builtins.int", "materializer": materializer_path(ForeignIntMaterializer)}
    registry.save("number", 7, version="1.0.0", materializer=materializer)
    assert registry.load("number", "1.0.0") == 7
    assert registry.info("number", "1.0.0")["materializer"] == materializer_path(ForeignIntMaterializer)
    assert registry.registered_materializer("builtins.int") == materializer_path(RevisionedIntMaterializer)


def test_serialization_hints_reject_materializer_instance(tmp_path):
    registry = Registry(tmp_path / "registry")
    with pytest.raises(TypeError, match="class or fully qualified class-name string"):
        registry.serialization_hints_for_object(7, materializer=BuiltInMaterializer(uri=str(tmp_path)))


@pytest.mark.parametrize("default", [False, True], ids=["registry", "default"])
def test_registration_rejects_materializer_instance_without_mutation(tmp_path, monkeypatch, default):
    registry = Registry(tmp_path / "registry")
    defaults = Registry.get_default_materializers()
    monkeypatch.setattr(_RegistryCore, "_default_materializers", defaults.copy())
    original_bytes = registry.backend.metadata_path.read_bytes()
    original_mapping = registry.registered_materializers()
    instance = BuiltInMaterializer(uri=str(tmp_path))
    register = registry.register_default_materializer if default else registry.register_materializer
    with pytest.raises(TypeError, match="class or fully qualified class-name string"):
        register(int, instance)
    assert registry.backend.metadata_path.read_bytes() == original_bytes
    assert registry.registered_materializers() == original_mapping
    assert Registry.get_default_materializers() == defaults


@pytest.mark.parametrize("reference", ["class", "path"])
def test_default_registration_accepts_class_and_string(tmp_path, monkeypatch, reference):
    monkeypatch.setattr(_RegistryCore, "_default_materializers", Registry.get_default_materializers())
    materializer = ForeignIntMaterializer if reference == "class" else materializer_path(ForeignIntMaterializer)
    Registry.register_default_materializer(int, materializer)
    registry = Registry(tmp_path / "registry")
    registry.save("number", 7)
    assert registry.load("number") == 7
    assert registry.info("number", "1.0.0")["materializer"] == materializer_path(ForeignIntMaterializer)


@pytest.mark.parametrize("remote", [False, True], ids=["local", "remote"])
def test_reopen_preserves_custom_and_legacy_mappings_and_fills_missing_defaults(tmp_path, request, monkeypatch, remote):
    backend = request.getfixturevalue("cached_mock_registry").backend if remote else tmp_path / "registry"
    registry = Registry(backend, version_objects=True, use_cache=False)
    registry.register_materializer(int, RevisionedIntMaterializer)
    registry.save("before", 7, version="1.0.0")
    metadata = registry.backend.fetch_registry_metadata()
    metadata["materializers"].pop("builtins.str")
    legacy = "zenml.materializers.BuiltInMaterializer"
    metadata["materializers"]["builtins.float"] = legacy
    registry.backend.save_registry_metadata(metadata)
    register = Mock(wraps=registry.backend.register_materializer)
    monkeypatch.setattr(registry.backend, "register_materializer", register)

    reopened = Registry(registry.backend, use_cache=False)

    register.assert_called_once_with(["builtins.str"], [materializer_path(BuiltInMaterializer)])
    assert reopened.registered_materializer("builtins.int") == materializer_path(RevisionedIntMaterializer)
    assert reopened.backend.registered_materializers()["builtins.float"] == legacy
    assert reopened.registered_materializer("builtins.float") == materializer_path(BuiltInMaterializer)
    assert reopened.load("before", "1.0.0") == 7
    reopened.save("after", 8, version="1.0.0")
    assert reopened.info("after", "1.0.0")["materializer"] == materializer_path(RevisionedIntMaterializer)
    assert reopened.load("after", "1.0.0") == 8
    reopened.save("float", 1.5)
    reopened.save("text", "hello")
    assert reopened.load("float") == 1.5
    assert reopened.load("text") == "hello"


def test_explicit_default_override_still_replaces_custom_registration(tmp_path):
    registry = Registry(tmp_path / "registry")
    registry.register_materializer(int, RevisionedIntMaterializer)
    registry._register_default_materializers(override_preexisting_materializers=True)
    assert registry.registered_materializer("builtins.int") == materializer_path(BuiltInMaterializer)
    registry.save("number", 7)
    assert registry.load("number") == 7
