"""Preserve reported errors without adding read/existence work."""

from unittest.mock import Mock

import pytest
import yaml

from mindtrace.registry import Registry
from mindtrace.registry.core.exceptions import RegistryObjectNotFound
from mindtrace.registry.core.types import OpResult, OpResults
from tests.unit.mindtrace.registry.core.test_registry_delete_versions import _stored_files


@pytest.fixture(params=["core", "registry", "cached"])
def reader(request, tmp_path):
    if request.param == "cached":
        registry = request.getfixturevalue("cached_mock_registry")
    else:
        registry = Registry(backend=tmp_path / "registry", version_objects=True, mutable=True)
    return registry, registry._core if request.param == "core" else registry


def _read(target, operation, key="item@1.0.0"):
    if operation == "load":
        return target.load("item", "1.0.0")
    if operation == "getitem":
        return target[key]
    return getattr(target, operation)(key, "fallback")


@pytest.mark.parametrize("operation", ["load", "getitem", "get", "setdefault"])
@pytest.mark.parametrize("error_type", [PermissionError, ValueError, KeyError])
def test_reported_metadata_error_preserves_exception_without_preflight(reader, monkeypatch, operation, error_type):
    registry, target = reader
    registry._core.save("item", 7, version="1.0.0")
    before = _stored_files(registry.backend)
    error = error_type("metadata access failed")
    results = OpResults()
    results.add(OpResult.failed("item", "1.0.0", error))
    fetch = Mock(return_value=results)
    monkeypatch.setattr(registry.backend, "fetch_metadata", fetch)
    for method in ("has_object", "list_versions", "pull", "push", "delete"):
        monkeypatch.setattr(registry.backend, method, Mock(side_effect=AssertionError(f"Unexpected {method}")))

    with pytest.raises(error_type) as caught:
        _read(target, operation)
    assert caught.value is error
    fetch.assert_called_once_with(["item"], ["1.0.0"])
    assert _stored_files(registry.backend) == before


@pytest.mark.parametrize("facade", [False, True], ids=["core", "registry"])
@pytest.mark.parametrize("operation", ["getitem", "get", "setdefault", "pop"])
def test_malformed_class_metadata_keyerror_is_not_absence(tmp_path, facade, operation):
    registry = Registry(backend=tmp_path / "registry", version_objects=True, mutable=True)
    registry.save("item", 7, version="1.0.0")
    path = registry.backend._object_metadata_path("item", "1.0.0")
    metadata = yaml.safe_load(path.read_text())
    del metadata["class"]
    path.write_text(yaml.safe_dump(metadata))
    before = _stored_files(registry.backend)
    with pytest.raises(KeyError, match="class"):
        _read(registry if facade else registry._core, operation)
    assert _stored_files(registry.backend) == before


@pytest.mark.parametrize("operation", ["load", "get"])
@pytest.mark.parametrize("missing", [False, True], ids=["operational", "missing"])
def test_serialized_metadata_errors_keep_their_classification(reader, monkeypatch, operation, missing):
    registry, target = reader
    results = OpResults()
    results.add(
        OpResult.failed(
            "item", "1.0.0", error_type="RegistryObjectNotFound" if missing else "PermissionError", message="details"
        )
    )
    fetch = Mock(return_value=results)
    monkeypatch.setattr(registry.backend, "fetch_metadata", fetch)
    if missing and operation == "get":
        assert _read(target, operation) == "fallback"
    else:
        with pytest.raises(RegistryObjectNotFound if missing else RuntimeError, match="details"):
            _read(target, operation)
    fetch.assert_called_once_with(["item"], ["1.0.0"])


def test_batch_metadata_errors_preserve_independent_results(reader, monkeypatch):
    registry, target = reader
    for name in ("blocked", "good"):
        registry._core.save(name, 7, version="1.0.0")
    before = _stored_files(registry.backend)
    original = registry.backend.fetch_metadata

    def fetch(names, versions):
        results = original(names, versions)
        if "blocked" in names:
            results.add(OpResult.failed("blocked", "1.0.0", PermissionError("access denied")))
        return results

    monkeypatch.setattr(registry.backend, "fetch_metadata", fetch)
    result = target[["blocked@1.0.0", "good@1.0.0"]]
    assert result.results == [None, 7]
    assert result.failed == [("blocked", "1.0.0")]
    assert result.succeeded == [("good", "1.0.0")]
    assert result.errors[("blocked", "1.0.0")]["error"] == "PermissionError"
    assert _stored_files(registry.backend) == before


@pytest.mark.parametrize("operation", ["getitem", "get", "setdefault"])
def test_batch_missing_items_remain_results_without_default_writes(reader, operation):
    registry, target = reader
    registry.save("item", 7, version="1")
    result = _read(target, operation, key=["item@1", "missing@1"])
    assert result.results == [7, None]
    assert result.failed == [("missing", "1.0.0")]
    assert result.errors[("missing", "1.0.0")]["error"] == "RegistryObjectNotFound"
    assert registry.list_objects() == ["item"]


@pytest.mark.parametrize("stage", ["load", "delete"])
@pytest.mark.parametrize("default", [None, "fallback"])
def test_pop_operational_keyerror_propagates_without_more_existence_checks(reader, monkeypatch, stage, default):
    registry, target = reader
    registry._core.save("item", 7, version="1.0.0")
    before = _stored_files(registry.backend)
    error = KeyError(f"{stage} failed")
    operation = Mock(side_effect=error)
    monkeypatch.setattr(target, stage, operation)
    exists = Mock(wraps=registry.backend.has_object)
    monkeypatch.setattr(registry.backend, "has_object", exists)
    if stage == "load":
        deletion = Mock(side_effect=AssertionError("Delete after failed load"))
        monkeypatch.setattr(target, "delete", deletion)
    with pytest.raises(KeyError) as caught:
        target.pop("item@1.0.0", default)
    assert caught.value is error
    operation.assert_called_once()
    exists.assert_called_once_with("item", "1.0.0")
    assert _stored_files(registry.backend) == before


@pytest.mark.parametrize("operation", ["getitem", "get", "setdefault"])
def test_mapping_reads_have_same_io_and_integrity_budget_as_load(reader, monkeypatch, operation):
    registry, target = reader
    registry._core.save("item", 7, version="1.0.0")
    backends = [registry.backend]
    if registry._cached:
        backends.append(registry._cache.backend)
    calls = []
    for backend in backends:
        for method in ("fetch_metadata", "pull", "list_versions", "has_object"):
            spy = Mock(wraps=getattr(backend, method))
            monkeypatch.setattr(backend, method, spy)
            calls.append(spy)
    from mindtrace.registry.core import _registry_core

    integrity = Mock(wraps=_registry_core.compute_dir_hash)
    monkeypatch.setattr(_registry_core, "compute_dir_hash", integrity)
    calls.append(integrity)

    # Compare cold and warm cache reads; local/core readers have no cache state.
    for warm in [False, True] if registry._cached else [False]:
        for direct in [True, False]:
            if registry._cached and not warm:
                registry.clear_cache()
            for spy in calls:
                spy.reset_mock()
            value = target.load("item", "1.0.0") if direct else _read(target, operation)
            assert value == 7
            counts = [spy.call_count for spy in calls]
            if direct:
                expected = counts
            else:
                assert counts == expected


def test_missing_defaults_and_selected_version_pop_are_unchanged(reader):
    registry, target = reader
    assert target.get("missing") is None
    assert target.get("missing", "fallback") == "fallback"
    assert target.setdefault("missing") is None
    with pytest.raises(KeyError):
        _ = target["missing"]
    assert target.pop("missing", "fallback") == "fallback"
    with pytest.raises(KeyError):
        target.pop("missing")
    assert target.setdefault("item@1", 7) == 7
    registry._core.save("item", 8, version="2")
    assert target.pop("item@1") == 7
    assert registry._core.load("item", "2") == 8


@pytest.mark.parametrize("operation", ["getitem", "get", "setdefault"])
def test_invalid_read_version_is_valueerror_without_backend_io(reader, monkeypatch, operation):
    registry, target = reader
    for method in ("fetch_metadata", "pull", "list_versions", "push"):
        monkeypatch.setattr(registry.backend, method, Mock(side_effect=AssertionError(f"Unexpected {method}")))
    with pytest.raises(ValueError):
        _read(target, operation, key="item@invalid")


@pytest.mark.parametrize("operation", ["load", "delete", "getitem", "delitem"])
def test_missing_object_is_also_a_key_error(reader, operation):
    _, target = reader
    with pytest.raises(KeyError) as caught:
        if operation == "load":
            target.load("missing", "1")
        elif operation == "delete":
            target.delete("missing", "1")
        elif operation == "getitem":
            target["missing@1"]
        else:
            del target["missing@1"]
    assert isinstance(caught.value, RegistryObjectNotFound)
