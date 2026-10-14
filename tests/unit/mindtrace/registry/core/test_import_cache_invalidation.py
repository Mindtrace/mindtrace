"""Imports invalidate destination-object caches without warming or remote preflights."""

import json
from unittest.mock import Mock

import pytest

from mindtrace.registry import Registry, S3RegistryBackend
from mindtrace.registry.core.exceptions import RegistryCleanupRequired
from mindtrace.registry.core.types import CleanupState


@pytest.mark.parametrize("operation", ["explicit", "automatic", "renamed", "update"])
@pytest.mark.parametrize("warm", [False, True])
def test_import_invalidates_destination_only_without_warming(
    cached_mock_registry, tmp_path, monkeypatch, record_property, operation, warm
):
    registry = cached_mock_registry
    source = Registry(backend=tmp_path / "source", version_objects=True)
    source_name = "source" if operation == "renamed" else "item"
    source.save(source_name, 2, version="1.0.0")
    registry.save("unrelated", 99, version="1.0.0")
    if warm:
        registry.save("item", 1, version="1.0.0")
        registry._remote.delete("item", "1.0.0")
        # Object-level invalidation deliberately removes other cached versions
        # of this object, but never other objects.
        registry._cache.save("item", 9, version="9.0.0")
    registry._cache_lru_estimated_entries = 3 if warm else 1
    # Prime discovery; invalidation must not leave stale version-list entries.
    registry._cache.list_versions("item")
    cache_push = Mock(wraps=registry._cache.backend.push)
    monkeypatch.setattr(registry._cache.backend, "push", cache_push)
    calls = {}
    for method in ("list_objects", "list_versions", "fetch_metadata", "push", "pull", "delete"):
        calls[method] = Mock(wraps=getattr(registry.backend, method))
        monkeypatch.setattr(registry.backend, method, calls[method])

    if operation == "update":
        result = registry.update(source)
    elif operation == "automatic":
        result = registry.download(source, source_name)
    else:
        result = registry.download(source, source_name, target_name="item", target_version="1")

    record_property("remote_calls", json.dumps({name: call.call_count for name, call in calls.items()}, sort_keys=True))
    assert result is None  # Preserve the existing public return value.
    cache_push.assert_not_called()
    assert registry._cache.list_versions("item") == []
    assert registry._cache.load("unrelated", "1.0.0") == 99
    assert registry._cache_lru_estimated_entries == 1
    calls["pull"].assert_not_called()  # No destination download during invalidation.
    assert registry.load("item", "1.0.0", verify="none") == 2
    calls["pull"].assert_called_once()
    assert registry._cache.load("item", "1.0.0") == 2
    assert registry._cache_lru_estimated_entries == 2


@pytest.mark.parametrize("failure", ["conflict", "missing", "load", "push"])
def test_uncommitted_download_does_not_invalidate_cache(cached_mock_registry, tmp_path, monkeypatch, failure):
    registry = cached_mock_registry
    registry.save("item", 1, version="1.0.0")
    source = Registry(backend=tmp_path / "source", version_objects=True)
    if failure != "missing":
        source.save("item", 2, version="1.0.0")
    if failure != "conflict":
        registry._remote.delete("item", "1.0.0")
    if failure == "load":
        monkeypatch.setattr(source._core, "load", Mock(side_effect=OSError("source unavailable")))
    elif failure == "push":
        monkeypatch.setattr(registry.backend, "push", Mock(side_effect=PermissionError("destination denied")))
    delete = Mock(wraps=registry._cache.delete)
    monkeypatch.setattr(registry._cache, "delete", delete)
    before = registry._cache_lru_estimated_entries
    expected = PermissionError if failure == "push" else OSError if failure == "load" else ValueError

    with pytest.raises(expected):
        registry.download(source, "item", version="1.0.0", target_version="1.0.0")

    delete.assert_not_called()
    assert registry._cache.load("item", "1.0.0") == 1
    assert registry._cache_lru_estimated_entries == before


def test_update_invalidates_each_success_before_a_later_failure(cached_mock_registry, tmp_path, monkeypatch):
    registry = cached_mock_registry
    source = Registry(backend=tmp_path / "source", version_objects=True)
    for name in ("a", "b"):
        source.save(name, 2, version="1.0.0")
        registry.save(name, 1, version="1.0.0")
        registry._remote.delete(name, "1.0.0")
    monkeypatch.setattr(source._core, "list_objects", lambda: ["a", "b"])
    push = registry.backend.push

    def fail_second(names, *args, **kwargs):
        if names == ["b"]:
            raise OSError("second import failed")
        return push(names, *args, **kwargs)

    monkeypatch.setattr(registry.backend, "push", fail_second)
    with pytest.raises(OSError, match="second import failed"):
        registry.update(source)

    assert registry._cache.list_versions("a") == []
    assert registry.load("a", "1.0.0", verify="none") == 2
    assert registry._cache.load("b", "1.0.0") == 1


def test_update_conflict_preserves_cache(cached_mock_registry, tmp_path):
    registry = cached_mock_registry
    registry.save("item", 1, version="1.0.0")
    source = Registry(backend=tmp_path / "source", version_objects=True)
    source.save("item", 2, version="1.0.0")

    with pytest.raises(ValueError, match="already exists"):
        registry.update(source)
    assert registry._cache.load("item", "1.0.0") == 1


def test_cache_cleanup_failure_does_not_mask_import_or_prevent_other_evictions(
    cached_mock_registry, tmp_path, monkeypatch
):
    registry = cached_mock_registry
    registry.save("item", 1, version="1.0.0")
    registry._remote.delete("item", "1.0.0")
    registry._cache.save("item", 9, version="9.0.0")
    registry._cache_lru_estimated_entries = 2
    source = Registry(backend=tmp_path / "source", version_objects=True)
    source.save("item", 2, version="1.0.0")
    delete = registry._cache.backend.delete

    def fail_one(names, versions, **kwargs):
        from mindtrace.registry.core.types import OpResult

        result = delete(names, versions, **kwargs)
        # Inject a failed local deletion for one version; others still succeed.
        if "1.0.0" in versions:
            registry._cache.save("item", 1, version="1.0.0")
            result.add(OpResult.failed("item", "1.0.0", PermissionError("cache denied")))
        return result

    monkeypatch.setattr(registry._cache.backend, "delete", fail_one)
    warning = Mock()
    monkeypatch.setattr(registry.logger, "warning", warning)

    assert registry.download(source, "item", target_version="1.0.0") is None
    assert registry._remote.load("item", "1.0.0") == 2
    assert registry._cache.list_versions("item") == ["1.0.0"]
    assert registry._cache_lru_estimated_entries == 1
    warning.assert_called()


def test_committed_cleanup_warning_invalidates_and_still_propagates(cached_mock_registry, tmp_path, monkeypatch):
    registry = cached_mock_registry
    registry.save("item", 1, version="1.0.0")
    registry._remote.delete("item", "1.0.0")
    source = Registry(backend=tmp_path / "source", version_objects=True)
    source.save("item", 2, version="1.0.0")
    push = registry.backend.push

    def commit_with_cleanup_warning(*args, **kwargs):
        result = push(*args, **kwargs)
        result.first().cleanup = CleanupState.ORPHANED
        return result

    monkeypatch.setattr(registry.backend, "push", commit_with_cleanup_warning)
    with pytest.raises(RegistryCleanupRequired):
        registry.download(source, "item", target_version="1.0.0")

    assert registry._cache.list_versions("item") == []
    assert registry._remote.load("item", "1.0.0") == 2


@pytest.mark.parametrize("cached", [False, True])
def test_nonversioned_import_and_uncached_control(cached_mock_registry, tmp_path, cached):
    backend = S3RegistryBackend(
        uri=tmp_path / "nonversioned",
        endpoint="example.invalid",
        access_key="test",
        secret_key="test",
        bucket="nonversioned-import",
        secure=False,
    )
    registry = Registry(backend=backend, use_cache=cached, version_objects=False, mutable=True)
    registry.save("item", 1)
    registry._core.delete("item")
    source = Registry(backend=tmp_path / "source", version_objects=True)
    source.save("item", 2, version="7.0.0")

    assert registry.download(source, "item") is None
    assert registry.load("item", verify="none") == 2
