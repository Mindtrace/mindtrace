"""Store moves retain source identity and reject permissions before writing."""

from unittest.mock import Mock

import pytest

from mindtrace.registry import LocalRegistryBackend, Registry, Store
from mindtrace.registry.core.exceptions import RegistryObjectNotFound, StoreAmbiguousObjectError
from tests.unit.mindtrace.registry.core.test_registry_delete_versions import (
    _replicas,
    _stored_files,
)


def _assert_exact_version_removed(backend, before, name, version):
    """Compare committed artifacts; deletion may also clean staging for its target."""
    if isinstance(backend, LocalRegistryBackend):
        metadata = f"_meta_{name}@{version}.yaml"
        payload = f"{name}/{version}/"
        staging = "_staging/"
    else:
        root = f"{backend._prefix}/" if backend._prefix else ""
        metadata = f"{root}_meta_{name}@{version}.json"
        payload = f"{root}objects/{name}/{version}/"
        staging = f"{root}_staging/"
    assert metadata in before
    assert any(key.startswith(payload) for key in before)
    expected = {
        key: value for key, value in before.items() if key != metadata and not key.startswith((payload, staging))
    }
    actual = {key: value for key, value in _stored_files(backend).items() if not key.startswith(staging)}
    assert actual == expected


@pytest.fixture(params=["local", "cached"])
def move_store(request, tmp_path):
    source = (
        request.getfixturevalue("cached_mock_registry")
        if request.param == "cached"
        else Registry(backend=tmp_path / "source", version_objects=True, mutable=True)
    )
    destination = Registry(backend=tmp_path / "destination", version_objects=True, mutable=True)
    return Store(mounts={"src": source, "dst": destination}, default_mount="dst")


@pytest.mark.parametrize(
    ("key", "kwargs"),
    [
        ("src/item", {}),
        ("item", {}),
        ("src/item@1", {}),
        ("item@1", {}),
        ("src/item", {"source_version": "1"}),
        ("item@2", {"source_version": "1"}),
    ],
)
def test_move_retains_source_identity_when_new_version_is_published(move_store, monkeypatch, key, kwargs):
    source = move_store.get_registry("src")
    destination = move_store.get_registry("dst")
    source.save("item", "copied", version="1")
    source.save("keep", "untouched", version="1")
    source.load("item", "1")  # Exercise eviction of an existing cached source replica.
    original_save = destination.save
    published = []
    snapshots = []

    def save_then_publish(*args, **save_kwargs):
        saved = original_save(*args, **save_kwargs)
        source.save("item", "newer", version="2")
        snapshots.extend((backend, _stored_files(backend)) for backend in _replicas(source))
        published.append("2.0.0")
        return saved

    monkeypatch.setattr(destination, "save", save_then_publish)
    assert move_store.move(key, target="dst/item", target_version="7", **kwargs) == "7.0.0"
    assert published == ["2.0.0"]
    assert destination.load("item", "7") == "copied"
    for backend, before in snapshots:
        _assert_exact_version_removed(backend, before, "item", "1.0.0")
    assert source.load("item", "2") == "newer"
    assert source.load("keep", "1") == "untouched"


@pytest.mark.parametrize("qualified", [False, True])
def test_move_read_only_source_rejects_before_load_or_write(move_store, monkeypatch, qualified):
    source = move_store.get_registry("src")
    source.save("item", "original", version="1")
    move_store.remove_mount("src")
    move_store.add_mount(source, name="src", read_only=True)
    source_files = _stored_files(source.backend)
    destination = move_store.get_registry("dst")
    destination_files = _stored_files(destination.backend)
    load = Mock(wraps=source.load)
    save = Mock(wraps=destination.save)
    monkeypatch.setattr(source, "load", load)
    monkeypatch.setattr(destination, "save", save)

    with pytest.raises(PermissionError, match="Mount 'src' is read-only"):
        move_store.move("src/item" if qualified else "item", target="dst/item")

    load.assert_not_called()
    save.assert_not_called()
    assert _stored_files(source.backend) == source_files
    assert _stored_files(destination.backend) == destination_files


@pytest.mark.parametrize("versioned", [False, True])
@pytest.mark.parametrize("digits", [2, 4])
def test_move_unqualified_nested_source_to_same_default_name(tmp_path, monkeypatch, versioned, digits):
    source = Registry(backend=tmp_path / "src", version_objects=versioned, version_digits=digits)
    destination = Registry(backend=tmp_path / "dst", version_objects=versioned, version_digits=digits)
    store = Store(mounts={"src": source, "dst": destination}, default_mount="dst")
    version = source.save("nested/item", "original")
    source.save("nested/sibling", "keep")
    before = _stored_files(source.backend)
    resolve = Mock(wraps=store._resolve_load_location)
    monkeypatch.setattr(store, "_resolve_load_location", resolve)

    assert store.move("nested/item", target="nested/item") == version

    resolve.assert_called_once_with("nested/item", "latest")
    assert destination.load("nested/item") == "original"
    _assert_exact_version_removed(source.backend, before, "nested/item", version)
    assert source.load("nested/sibling") == "keep"


@pytest.mark.parametrize(
    ("key", "kwargs", "expected"),
    [
        ("src/item", {}, "ten"),
        ("src/item", {"source_version": None}, "ten"),
        ("item@2", {}, "two"),
        ("src/item@2", {"source_version": "10"}, "ten"),
    ],
)
def test_move_preserves_version_selection_and_remaining_history(move_store, key, kwargs, expected):
    source = move_store.get_registry("src")
    source.save("item", "two", version="2")
    source.save("item", "ten", version="10")
    before = _stored_files(source.backend)
    version = "10.0.0" if expected == "ten" else "2.0.0"
    remaining = "2" if expected == "ten" else "10"

    assert move_store.move(key, target="dst/renamed@5", **kwargs) == "5.0.0"

    assert move_store.load("dst/renamed@5") == expected
    _assert_exact_version_removed(source.backend, before, "item", version)
    assert source.load("item", remaining) == ("two" if expected == "ten" else "ten")


@pytest.mark.parametrize("stage", ["load", "save", "delete"])
def test_move_propagates_errors_without_unintended_source_deletion(move_store, monkeypatch, stage):
    source = move_store.get_registry("src")
    destination = move_store.get_registry("dst")
    source.save("item", "original", version="1")
    before = _stored_files(source.backend)
    error = OSError(f"{stage} unavailable")
    operation = Mock(side_effect=error)
    monkeypatch.setattr(destination if stage == "save" else source, stage, operation)

    with pytest.raises(OSError) as caught:
        move_store.move("src/item", target="dst/item")

    assert caught.value is error
    operation.assert_called_once()
    assert _stored_files(source.backend) == before
    if stage == "delete":
        # No rollback guarantee: successful destination copy remains.
        assert destination.load("item") == "original"
    else:
        assert destination.list_versions("item") == []


@pytest.mark.parametrize("key", ["src/missing", "missing", "src/item@99", "src/item@invalid"])
def test_move_bad_source_never_writes_destination(move_store, monkeypatch, key):
    move_store.save("src/item", "keep", version="1")
    source_files = _stored_files(move_store.get_registry("src").backend)
    destination = move_store.get_registry("dst")
    save = Mock(wraps=destination.save)
    monkeypatch.setattr(destination, "save", save)
    error_type = ValueError if key.endswith("invalid") else RegistryObjectNotFound

    with pytest.raises(error_type):
        move_store.move(key, target="dst/item")

    save.assert_not_called()
    assert _stored_files(move_store.get_registry("src").backend) == source_files


def test_move_ambiguous_source_never_writes(move_store, monkeypatch):
    move_store.save("src/item", "source", version="1")
    move_store.save("dst/item", "destination", version="1")
    destination = move_store.get_registry("dst")
    before = _stored_files(destination.backend)
    save = Mock(wraps=destination.save)
    monkeypatch.setattr(destination, "save", save)
    with pytest.raises(StoreAmbiguousObjectError):
        move_store.move("item", target="dst/other")
    save.assert_not_called()
    assert _stored_files(destination.backend) == before


def test_move_read_only_destination_preserves_source(move_store):
    source = move_store.get_registry("src")
    source.save("item", "original", version="1")
    before = _stored_files(source.backend)
    destination = move_store.get_registry("dst")
    move_store.remove_mount("dst")
    move_store.add_mount(destination, name="dst", read_only=True)
    with pytest.raises(PermissionError, match="Mount 'dst' is read-only"):
        move_store.move("src/item", target="dst/item")
    assert _stored_files(source.backend) == before
    assert destination.list_versions("item") == []


@pytest.mark.parametrize("qualified", [False, True])
@pytest.mark.parametrize("version", ["latest", "1"])
def test_move_backend_call_budget(move_store, monkeypatch, record_property, qualified, version):
    """Do not exceed the pre-fix I/O budget on the same cold initial state."""
    source = move_store.get_registry("src")
    source.save("item", "original", version="1")
    if source._cached:
        source.clear_cache()
    source._core._invalidate_versions_cache("item")
    calls = {}
    for mount_name in move_store.list_mounts():
        registry = move_store.get_registry(mount_name)
        for replica, backend in enumerate(_replicas(registry)):
            for method in ("list_versions", "has_object", "fetch_metadata", "pull", "push", "delete"):
                spy = Mock(wraps=getattr(backend, method))
                monkeypatch.setattr(backend, method, spy)
                calls[f"{mount_name}/{replica}/{method}"] = spy
    assert (
        move_store.move(
            "src/item" if qualified else "item", target="dst/renamed", source_version=version, target_version="1"
        )
        == "1.0.0"
    )
    record_property("backend_calls", {key: spy.call_count for key, spy in calls.items()})
    # Baseline budgets: list_versions, has_object, fetch_metadata, pull, push, delete.
    budgets = {
        (False, False, "latest"): (2, 4, 2, 1, 1, 1),
        (False, True, "latest"): (1, 0, 2, 1, 1, 1),
        (False, False, "1"): (0, 6, 2, 1, 1, 1),
        (False, True, "1"): (0, 0, 2, 1, 1, 1),
        (True, False, "latest"): (2, 7, 6, 1, 2, 2),
        (True, True, "latest"): (1, 3, 4, 1, 2, 2),
        (True, False, "1"): (0, 9, 6, 1, 2, 2),
        (True, True, "1"): (0, 3, 4, 1, 2, 2),
    }
    methods = ("list_versions", "has_object", "fetch_metadata", "pull", "push", "delete")
    for method, limit in zip(methods, budgets[source._cached, qualified, version]):
        count = sum(spy.call_count for key, spy in calls.items() if key.endswith(f"/{method}"))
        assert count <= limit, f"Extra {method} calls: {count} > {limit}"
    # Qualified moves do not discover other mounts or preflight existence.
    if qualified:
        assert calls["temp/0/has_object"].call_count == 0
        assert calls["temp/0/list_versions"].call_count == 0
    assert move_store.load("dst/renamed", "1") == "original"
