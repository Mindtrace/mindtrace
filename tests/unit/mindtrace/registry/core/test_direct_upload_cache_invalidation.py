"""Direct uploads invalidate only the destination object's local cache."""

import json
from unittest.mock import Mock

import pytest

from mindtrace.registry import Registry, S3RegistryBackend
from mindtrace.registry.core.types import OpResult


@pytest.mark.parametrize(
    "name,version,expected_version",
    [
        pytest.param("item", "1", "1.0.0", id="overwrite"),
        pytest.param("item", "3", "3.0.0", id="new-version"),
        pytest.param("item", None, "2.0.1", id="automatic"),
        pytest.param("new", None, "1.0.0", id="new-object"),
    ],
)
def test_direct_upload_invalidates_only_destination_without_warming(
    cached_mock_registry, monkeypatch, record_property, name, version, expected_version
):
    registry = cached_mock_registry
    for object_name, object_version in (
        ("keep", "1.0.0"),
        ("item/child", "1.0.0"),
        ("item", "1.0.0"),
        ("item", "2.0.0"),
    ):
        registry.save(object_name, b"old", version=object_version)
    assert registry._cache_lru_estimated_entries == 4
    registry._cache.list_versions(name)  # Prime version-list memoization.
    staged = registry.create_direct_upload_target("replacement")["staged_target"]
    assert registry.backend.storage.upload_string(b"new", staged["path"]).ok
    cache_push = Mock(wraps=registry._cache.backend.push)
    monkeypatch.setattr(registry._cache.backend, "push", cache_push)
    calls = {}
    for method in ("list_objects", "list_versions", "fetch_metadata", "push", "pull", "delete", "commit_direct_upload"):
        calls[method] = Mock(wraps=getattr(registry.backend, method))
        monkeypatch.setattr(registry.backend, method, calls[method])

    committed = registry.commit_direct_upload(name, staged_target=staged, version=version)

    record_property("remote_calls", json.dumps({key: call.call_count for key, call in calls.items()}, sort_keys=True))
    assert committed == expected_version
    cache_push.assert_not_called()
    calls["pull"].assert_not_called()
    assert registry._cache.list_versions(name) == []
    remaining = 2 if name == "item" else 4
    assert registry._cache_lru_estimated_entries == remaining
    for unchanged in ("keep", "item/child"):
        assert registry.load(unchanged, "1.0.0", verify="none") == b"old"
    if name == "new":
        assert registry._cache.list_versions("item") == ["1.0.0", "2.0.0"]
    calls["pull"].assert_not_called()  # Retained objects are still cache hits.
    assert registry.load(name, committed, verify="none") == b"new"
    calls["pull"].assert_called_once()
    assert registry._cache.load(name, committed) == b"new"
    assert registry._cache_lru_estimated_entries == remaining + 1


@pytest.mark.parametrize("outcome", ["failed", "skipped"])
def test_unsuccessful_direct_upload_preserves_cache(cached_mock_registry, monkeypatch, outcome):
    registry = cached_mock_registry
    registry.save("item", b"old", version="1.0.0")
    registry.save("keep", b"keep", version="1.0.0")
    staged = registry.create_direct_upload_target("attempt")["staged_target"]
    assert registry.backend.storage.upload_string(b"new", staged["path"]).ok
    before = registry._cache_lru_estimated_entries
    failure = PermissionError("remote denied")
    if outcome == "failed":
        monkeypatch.setattr(
            registry.backend,
            "commit_direct_upload",
            Mock(return_value=OpResult.failed("item", "1.0.0", failure)),
        )
    with pytest.raises(PermissionError if outcome == "failed" else RuntimeError) as error:
        registry.commit_direct_upload("item", staged_target=staged, version="1.0.0", on_conflict="skip")
    if outcome == "failed":
        assert error.value is failure
    else:
        assert "already exists" in str(error.value)
    assert registry._cache.load("item", "1.0.0") == b"old"
    assert registry._cache.load("keep", "1.0.0") == b"keep"
    assert registry._remote.load("item", "1.0.0") == b"old"
    assert registry._cache_lru_estimated_entries == before


@pytest.mark.parametrize("cached", [False, True])
def test_unversioned_direct_upload_and_uncached_control(cached_mock_registry, tmp_path, monkeypatch, cached):
    # A separate backend is necessary: versioning is persisted in registry metadata.
    backend = S3RegistryBackend(
        uri=tmp_path / "unversioned",
        endpoint="example.invalid",
        access_key="test",
        secret_key="test",
        bucket="unversioned-direct-upload",
        secure=False,
    )
    registry = Registry(backend=backend, use_cache=cached, version_objects=False, mutable=True)
    registry.save("item", b"old")
    registry.save("keep", b"keep")
    staged = registry.create_direct_upload_target("replacement")["staged_target"]
    assert backend.storage.upload_string(b"new", staged["path"]).ok

    assert registry.commit_direct_upload("item", staged_target=staged) == "1.0.0"

    pull = Mock(wraps=backend.pull)
    monkeypatch.setattr(backend, "pull", pull)
    assert registry.load("keep", verify="none") == b"keep"
    assert pull.call_count == (0 if cached else 1)
    assert registry.load("item", verify="none") == b"new"


def test_cache_invalidation_failure_preserves_successful_commit(cached_mock_registry, monkeypatch):
    registry = cached_mock_registry
    registry.save("item", b"old", version="1.0.0")
    registry.save("keep", b"keep", version="1.0.0")
    staged = registry.create_direct_upload_target("replacement")["staged_target"]
    assert registry.backend.storage.upload_string(b"new", staged["path"]).ok
    before = registry._cache_lru_estimated_entries
    monkeypatch.setattr(registry._cache.backend, "list_versions", Mock(side_effect=PermissionError("cache denied")))
    warning = Mock()
    monkeypatch.setattr(registry.logger, "warning", warning)

    assert registry.commit_direct_upload("item", staged_target=staged, version="1.0.0") == "1.0.0"
    warning.assert_called_once()
    assert "cache denied" in str(warning.call_args)

    assert registry._remote.load("item", "1.0.0") == b"new"
    assert registry._cache.load("keep", "1.0.0") == b"keep"
    # Best effort cannot promise freshness when local invalidation itself fails.
    assert registry._cache.load("item", "1.0.0") == b"old"
    assert registry._cache_lru_estimated_entries == before
