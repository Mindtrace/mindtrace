"""Explicit dictionary deletion uses the same version identity as save and load."""

import pytest

from mindtrace.registry import GCPRegistryBackend, LocalRegistryBackend, Registry, S3RegistryBackend
from mindtrace.registry.core.exceptions import RegistryObjectNotFound
from tests.unit.mindtrace.registry.backends.test_gcp_registry_backend import MockGCSHandler
from tests.unit.mindtrace.registry.backends.test_s3_registry_backend import MockS3Handler


@pytest.fixture(params=["local", "cached-s3", "cached-gcp"])
def deletion_backend(request, monkeypatch, tmp_path):
    """Use real backends and cache code, with remote transport mocked in memory."""
    if request.param == "local":
        return LocalRegistryBackend(uri=tmp_path / "registry")
    if request.param == "cached-s3":
        monkeypatch.setattr("mindtrace.registry.backends.s3_registry_backend.S3StorageHandler", MockS3Handler)
        return S3RegistryBackend(
            uri=tmp_path / "remote",
            endpoint="example.invalid",
            access_key="test",
            secret_key="test",
            bucket="delete-version-tests",
            prefix="tenant/registry",
        )
    monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.GCSStorageHandler", MockGCSHandler)
    return GCPRegistryBackend(
        uri=tmp_path / "remote",
        project_id="test-project",
        bucket_name="delete-version-tests",
        credentials_path=str(tmp_path / "unused-credentials.json"),
        prefix="tenant/registry",
    )


def _stored_files(backend):
    """Read actual payload/metadata bytes without using discovery or has_object."""
    if isinstance(backend, LocalRegistryBackend):
        return {
            path.relative_to(backend.uri).as_posix(): path.read_bytes()
            for path in backend.uri.rglob("*")
            if path.is_file()
        }
    handler = backend.storage if isinstance(backend, S3RegistryBackend) else backend.gcs
    return dict(handler._objects)


def _replicas(registry):
    return [registry.backend, registry._cache.backend] if registry._cached else [registry.backend]


def _assert_exact_version_removed(backend, before, name, version):
    if isinstance(backend, LocalRegistryBackend):
        metadata = f"_meta_{name}@{version}.yaml"
        payload_prefix = f"{name}/{version}/"
    else:
        root = f"{backend._prefix}/" if backend._prefix else ""
        metadata = f"{root}_meta_{name}@{version}.json"
        payload_prefix = f"{root}objects/{name}/{version}/"
    assert metadata in before
    assert any(key.startswith(payload_prefix) for key in before)
    expected = {key: value for key, value in before.items() if key != metadata and not key.startswith(payload_prefix)}
    assert _stored_files(backend) == expected


@pytest.mark.parametrize("versioned", [False, True])
@pytest.mark.parametrize("save_version", ["1", "1.0.0"])
@pytest.mark.parametrize("delete_version", ["1", "1.0.0"])
def test_delitem_equivalent_versions_remove_only_selected_artifacts(
    deletion_backend, versioned, save_version, delete_version
):
    registry = Registry(backend=deletion_backend, version_objects=versioned)
    assert registry.save("item", 42, version=save_version) == "1.0.0"
    registry.save("keep", 99, version="1.0.0")
    if versioned:
        registry.save("item", 43, version="2.0.0")
    assert registry["item@1"] == registry["item@1.0.0"] == 42
    assert "item@1" in registry
    assert "item@1.0.0" in registry
    replicas = _replicas(registry)
    before = [_stored_files(backend) for backend in replicas]
    cache_count = registry._cache_lru_estimated_entries

    del registry[f"item@{delete_version}"]

    for backend, files in zip(replicas, before):
        _assert_exact_version_removed(backend, files, "item", "1.0.0")
    assert registry.has_object("item", "1.0.0") is False
    assert registry.load("keep", "1.0.0") == 99
    if versioned:
        assert registry.list_versions("item") == ["2.0.0"]
        assert registry.load("item", "2.0.0") == 43
    if registry._cached:
        assert registry._cache.has_object("item", "1.0.0") is False
        assert registry._cache.load("keep", "1.0.0") == 99
        assert registry._cache_lru_estimated_entries == cache_count - 1


@pytest.mark.parametrize(
    "digits, short_version, full_version",
    [(1, "1", "1"), (2, "1", "1.0"), (4, "1.2", "1.2.0.0")],
)
def test_delitem_respects_configured_version_digits(deletion_backend, digits, short_version, full_version):
    registry = Registry(backend=deletion_backend, version_objects=True, version_digits=digits)
    registry.save("item", 42, version=full_version)
    registry.save("keep", 99, version=full_version)
    assert registry.load("item", short_version) == 42
    replicas = _replicas(registry)
    before = [_stored_files(backend) for backend in replicas]

    del registry[f"item@{short_version}"]

    for backend, files in zip(replicas, before):
        _assert_exact_version_removed(backend, files, "item", full_version)
    assert registry.load("keep", full_version) == 99


@pytest.mark.parametrize("versioned", [False, True])
@pytest.mark.parametrize("key", ["absent@1", "item@2"])
def test_delitem_missing_explicit_identity_raises_registry_error(deletion_backend, versioned, key):
    registry = Registry(backend=deletion_backend, version_objects=versioned)
    registry.save("item", 42, version="1")
    replicas = _replicas(registry)
    before = [_stored_files(backend) for backend in replicas]

    with pytest.raises(RegistryObjectNotFound):
        del registry[key]

    assert [_stored_files(backend) for backend in replicas] == before


def test_delitem_does_not_introduce_latest_deletion(deletion_backend):
    registry = Registry(backend=deletion_backend, version_objects=True)
    registry.save("item", 42, version="1")
    replicas = _replicas(registry)
    before = [_stored_files(backend) for backend in replicas]

    with pytest.raises(ValueError):
        del registry["item@latest"]

    assert _stored_files(registry.backend) == before[0]
    assert registry.load("item", "1.0.0") == 42


@pytest.mark.parametrize("version", ["1", "1.0.0"])
@pytest.mark.parametrize("operation", ["delete", "batch_delete", "batch_delitem", "pop"])
def test_other_delete_entry_points_keep_normalizing_versions(tmp_path, operation, version):
    registry = Registry(backend=tmp_path / "registry", version_objects=True)
    registry.save("item", 42, version="1.0.0")
    registry.save("item", 43, version="2.0.0")
    before = _stored_files(registry.backend)

    if operation == "delete":
        registry.delete("item", version)
    elif operation == "batch_delete":
        result = registry.delete(["item"], [version])
        assert result.success_count == 1
        assert result.failure_count == 0
    elif operation == "batch_delitem":
        del registry[[f"item@{version}"]]
    else:
        assert registry.pop(f"item@{version}") == 42

    _assert_exact_version_removed(registry.backend, before, "item", "1.0.0")
    assert registry.load("item", "2.0.0") == 43
