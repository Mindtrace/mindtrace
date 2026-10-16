"""Missing public deletion targets are errors, not idempotent cleanup successes."""

from unittest.mock import Mock

import pytest

from mindtrace.registry import GCPRegistryBackend, Registry, S3RegistryBackend, Store
from mindtrace.registry.core.exceptions import RegistryObjectNotFound
from mindtrace.registry.core.types import BatchResult, OpResult, OpResults
from tests.unit.mindtrace.registry.backends.test_gcp_registry_backend import MockGCSHandler
from tests.unit.mindtrace.registry.backends.test_s3_registry_backend import MockS3Handler
from tests.unit.mindtrace.registry.core.test_registry_delete_versions import _stored_files


@pytest.fixture(params=["local", "s3", "cached-s3", "gcp", "cached-gcp"])
def make_registry(request, monkeypatch, tmp_path):
    """Construct real Registry/backends, mocking only remote storage transport."""
    kind = request.param

    def make(versioned=True):
        backend = tmp_path / "registry"
        if kind.endswith("s3"):
            monkeypatch.setattr("mindtrace.registry.backends.s3_registry_backend.S3StorageHandler", MockS3Handler)
            backend = S3RegistryBackend(
                uri=tmp_path / "remote",
                endpoint="example.invalid",
                access_key="test",
                secret_key="test",
                bucket="missing-delete",
                prefix="tenant/registry",
            )
        elif kind.endswith("gcp"):
            monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.GCSStorageHandler", MockGCSHandler)
            backend = GCPRegistryBackend(
                uri=tmp_path / "remote",
                project_id="test",
                bucket_name="missing-delete",
                credentials_path=str(tmp_path / "unused.json"),
                prefix="tenant/registry",
            )
        return Registry(backend=backend, version_objects=versioned, use_cache=kind.startswith("cached"))

    return make


def _snapshot(registry):
    backends = [registry.backend]
    if registry._cached:
        backends.append(registry._cache.backend)
    return [_stored_files(backend) for backend in backends]


@pytest.mark.parametrize("versioned", [False, True])
@pytest.mark.parametrize("operation", ["delete", "delitem"])
@pytest.mark.parametrize("name, version", [("missing", None), ("missing", "1"), ("keep", "2")])
def test_missing_single_targets_raise_without_modifying_storage(make_registry, versioned, operation, name, version):
    registry = make_registry(versioned)
    registry.save("keep", 7, version="1")
    before = _snapshot(registry)
    with pytest.raises(RegistryObjectNotFound):
        if operation == "delete":
            registry.delete(name, version)
        else:
            del registry[name if version is None else f"{name}@{version}"]
    assert _snapshot(registry) == before


@pytest.mark.parametrize("versioned", [False, True])
@pytest.mark.parametrize("version", [None, "1"])
def test_mixed_batch_reports_missing_and_keeps_independent_success(make_registry, versioned, version):
    registry = make_registry(versioned)
    registry.save("present", 7, version="1")
    registry.save("keep", 8, version="1")
    if versioned:
        registry.save("keep", 9, version="2")
    result = registry.delete(["missing", "present"], version)
    expected = version or "all"
    assert result.results == [None, True]
    assert result.failed == [("missing", expected)]
    assert result.succeeded == [("present", expected)]
    assert result.errors[("missing", expected)]["error"] == "RegistryObjectNotFound"
    assert registry.load("keep", "1") == 8
    assert not registry.has_object("present", "1")
    if registry._cached:
        assert not registry._cache.has_object("present", "1")
        assert registry._cache.load("keep", "1") == 8
    with pytest.raises(RegistryObjectNotFound):
        registry.delete("present", version)


def test_batch_aliases_of_missing_version_are_all_failures(make_registry):
    registry = make_registry()
    result = registry.delete(["missing", "missing"], ["1", "1.0.0"])
    assert result.results == [None, None]
    assert result.succeeded == []
    assert result.failed == [("missing", "1"), ("missing", "1.0.0")]
    assert all(error["error"] == "RegistryObjectNotFound" for error in result.errors.values())


@pytest.mark.parametrize("operation", ["delete", "delitem"])
def test_invalid_version_errors_are_not_relabelled_missing(make_registry, operation):
    registry = make_registry()
    registry.save("keep", 7)
    before = _snapshot(registry)
    with pytest.raises(ValueError):
        if operation == "delete":
            registry.delete("keep", "latest")
        else:
            del registry["keep@latest"]
    assert _snapshot(registry)[0] == before[0]


def test_delete_uses_authoritative_state_not_stale_version_listing(make_registry):
    registry = make_registry()
    registry.save("item", 7, version="1")
    assert registry.list_versions("item") == ["1.0.0"]
    registry.backend.delete(["item"], ["1.0.0"])
    before = _snapshot(registry)
    with pytest.raises(RegistryObjectNotFound):
        registry.delete("item")
    assert _snapshot(registry)[0] == before[0]


def test_all_version_delete_refreshes_cached_empty_listing(make_registry):
    registry = make_registry()
    assert registry.list_versions("item") == []
    registry.save("item", 7, version="1")
    # Emulate an existing reader whose cached negative list predates the save.
    registry._core._versions_cache["item"] = ([], float("inf"))
    registry.delete("item")
    assert not registry.has_object("item", "1")


def test_backend_cleanup_remains_idempotent(make_registry):
    registry = make_registry()
    before = _snapshot(registry)
    for _ in range(2):
        result = registry.backend.delete(["missing"], ["1.0.0"])
        assert result[("missing", "1.0.0")].ok
    assert _snapshot(registry) == before


@pytest.mark.parametrize("facade", [False, True])
def test_core_and_facade_delitem_return_batch_result(tmp_path, facade):
    registry = Registry(backend=tmp_path / "registry", version_objects=False)
    registry.save("present", 7)
    target = registry if facade else registry._core
    result = target.__delitem__(["present", "missing"])
    assert isinstance(result, BatchResult)
    assert result.results == [True, None]
    assert result.errors[("missing", "all")]["error"] == "RegistryObjectNotFound"
    with pytest.raises(RegistryObjectNotFound):
        del target["present"]
    empty = target.delete([])
    assert empty.results == empty.succeeded == empty.failed == []
    assert empty.errors == {}


@pytest.mark.parametrize("stage", ["fetch_metadata", "delete"])
@pytest.mark.parametrize("operation", ["delete", "delitem", "batch"])
@pytest.mark.parametrize("raised", [False, True], ids=["per-item-result", "raised-by-backend"])
def test_operational_failures_are_preserved(tmp_path, monkeypatch, stage, operation, raised):
    registry = Registry(backend=tmp_path / "registry", version_objects=True)
    registry.save("item", 7, version="1")
    error = PermissionError("storage access denied")
    failure = OpResults()
    failure.add(OpResult.failed("item", "1.0.0", error))
    failing_operation = Mock(side_effect=error) if raised else Mock(return_value=failure)
    monkeypatch.setattr(registry.backend, stage, failing_operation)
    before = _snapshot(registry)
    if operation == "batch":
        result = registry.delete(["item"], ["1"])
        assert result.results == [None]
        assert result.errors[("item", "1")]["error"] == "PermissionError"
    else:
        with pytest.raises(PermissionError) as caught:
            if operation == "delete":
                registry.delete("item", "1")
            else:
                del registry["item@1"]
        assert caught.value is error
    assert _snapshot(registry) == before


def test_failed_batch_remote_items_evict_only_targeted_cache(cached_mock_registry, monkeypatch):
    registry = cached_mock_registry
    for name in ("stale", "failed", "good", "keep"):
        registry.save(name, name, version="1")
    registry.backend.delete(["stale"], ["1.0.0"])
    original = registry.backend.delete

    def delete(names, versions, **kwargs):
        result = OpResults()
        for name, version in zip(names, versions):
            if name == "failed":
                result.add(OpResult.failed(name, version, PermissionError("blocked")))
            else:
                result.add(original([name], [version], **kwargs).first())
        return result

    monkeypatch.setattr(registry.backend, "delete", delete)
    result = registry.delete(["stale", "failed", "good"], "1")
    assert result.succeeded == [("good", "1")]
    assert result.errors[("stale", "1")]["error"] == "RegistryObjectNotFound"
    assert result.errors[("failed", "1")]["error"] == "PermissionError"
    assert registry._cache.load("keep", "1") == "keep"
    for name in ("stale", "failed", "good"):
        assert not registry._cache.has_object(name, "1")


def test_store_delegates_missing_delete_policy(tmp_path):
    registry = Registry(backend=tmp_path / "registry", version_objects=False)
    store = Store(mounts={"main": registry}, default_mount="main")
    with pytest.raises(RegistryObjectNotFound):
        store.delete("main/missing")
    with pytest.raises(RegistryObjectNotFound):
        del store["main/missing"]
    registry.save("present", 7)
    result = store.delete(["main/present", "main/missing"])
    assert result.success_count == result.failure_count == 1
    assert result.errors[("main/missing", "latest")]["error"] == "RegistryObjectNotFound"


@pytest.mark.parametrize("stage", ["list_versions", "fetch_metadata"])
def test_batch_lookup_error_does_not_block_independent_deletion(tmp_path, monkeypatch, stage):
    registry = Registry(backend=tmp_path / "registry", version_objects=True)
    for name in ("blocked", "good"):
        registry.save(name, name, version="1")
    original = getattr(registry.backend, stage)

    def lookup(names, *args):
        if stage == "list_versions":
            if names == "blocked":
                raise PermissionError("denied")
            return original(names, *args)
        result = original(names, *args)
        result.add(OpResult.failed("blocked", "1.0.0", PermissionError("denied")))
        return result

    monkeypatch.setattr(registry.backend, stage, lookup)
    result = registry.delete(["blocked", "good"])
    assert result.results == [None, True]
    assert result.errors[("blocked", "all")]["error"] == "PermissionError"
    monkeypatch.setattr(registry.backend, stage, original)
    assert registry.load("blocked", "1") == "blocked"
    assert (registry.backend.uri / "blocked" / "1.0.0" / "data.json").is_file()
    assert not (registry.backend.uri / "good" / "1.0.0").exists()


def test_serialized_missing_metadata_error_uses_registry_exception(tmp_path, monkeypatch):
    registry = Registry(backend=tmp_path / "registry")
    result = OpResults()
    result.add(OpResult.failed("missing", "1.0.0", error_type="RegistryObjectNotFound", message="absent"))
    monkeypatch.setattr(registry.backend, "fetch_metadata", Mock(return_value=result))
    with pytest.raises(RegistryObjectNotFound, match="absent"):
        registry.delete("missing")


@pytest.mark.parametrize("stage", ["fetch_metadata", "delete"])
def test_missing_backend_response_is_not_success_or_absence(tmp_path, monkeypatch, stage):
    registry = Registry(backend=tmp_path / "registry")
    registry.save("item", 7)
    before = _snapshot(registry)
    monkeypatch.setattr(registry.backend, stage, Mock(return_value=OpResults()))
    with pytest.raises(RuntimeError, match="Backend returned no"):
        registry.delete("item")
    assert _snapshot(registry) == before


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("version", [None, "1"])
def test_missing_remote_delete_evicts_stale_cache(cached_mock_registry, batch, version):
    registry = cached_mock_registry
    registry.save("item", 1, version="1")
    registry.save("keep", 2, version="1")
    registry._remote.delete("item", "1")
    # All-version invalidation must ignore a memoized negative version listing.
    registry._cache._versions_cache["item"] = ([], float("inf"))
    if batch:
        result = registry.delete(["item"], version)
        assert result.failure_count == 1
    else:
        with pytest.raises(RegistryObjectNotFound):
            registry.delete("item", version)
    assert not registry._cache.has_object("item", "1")
    with pytest.raises(RegistryObjectNotFound):
        registry.load("item", "1")
    assert registry._cache.load("keep", "1") == 2


def test_cache_cleanup_failure_preserves_remote_delete_error(cached_mock_registry, monkeypatch):
    registry = cached_mock_registry
    registry.save("item", 1, version="1")
    error = PermissionError("remote delete denied")
    monkeypatch.setattr(registry._remote, "delete", Mock(side_effect=error))
    cleanup = Mock(side_effect=RuntimeError("cache unavailable"))
    monkeypatch.setattr(registry._cache, "delete", cleanup)
    with pytest.raises(PermissionError) as caught:
        registry.delete("item", "1")
    assert caught.value is error
    cleanup.assert_called_once()
