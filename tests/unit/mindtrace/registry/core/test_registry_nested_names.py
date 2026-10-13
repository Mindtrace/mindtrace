"""Nested names retain their full identity through discovery and lifecycle operations."""

import pytest

from mindtrace.registry import GCPRegistryBackend, LocalRegistryBackend, Registry, S3RegistryBackend
from tests.unit.mindtrace.registry.backends.test_gcp_registry_backend import MockGCSHandler
from tests.unit.mindtrace.registry.backends.test_s3_registry_backend import MockS3Handler


@pytest.fixture(params=["local", "s3", "s3-prefixed", "gcp", "gcp-prefixed"])
def nested_backend(request, monkeypatch, tmp_path):
    """Exercise real backend code with in-memory remote storage adapters."""
    kind = request.param
    prefix = "tenant/registry" if kind.endswith("-prefixed") else ""
    if kind == "local":
        return LocalRegistryBackend(uri=tmp_path / "registry")
    if kind.startswith("s3"):
        monkeypatch.setattr("mindtrace.registry.backends.s3_registry_backend.S3StorageHandler", MockS3Handler)
        return S3RegistryBackend(
            uri=tmp_path / "remote",
            endpoint="example.invalid",
            access_key="test",
            secret_key="test",
            bucket="nested-name-tests",
            prefix=prefix,
        )
    monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.GCSStorageHandler", MockGCSHandler)
    return GCPRegistryBackend(
        uri=tmp_path / "remote",
        project_id="test-project",
        bucket_name="nested-name-tests",
        credentials_path=str(tmp_path / "unused-credentials.json"),
        prefix=prefix,
    )


def _stored_files(backend):
    """Inspect physical storage without relying on the discovery methods under test."""
    if isinstance(backend, LocalRegistryBackend):
        return {p.relative_to(backend.uri).as_posix(): p.read_bytes() for p in backend.uri.rglob("*") if p.is_file()}
    handler = backend.storage if isinstance(backend, S3RegistryBackend) else backend.gcs
    return dict(handler._objects)


def _version_files(backend, files, name, version):
    if isinstance(backend, LocalRegistryBackend):
        metadata_key = f"_meta_{name}@{version}.yaml"
        payload_prefix = f"{name}/{version}/"
    else:
        root = f"{backend._prefix}/" if backend._prefix else ""
        metadata_key = f"{root}_meta_{name}@{version}.json"
        payload_prefix = f"{root}objects/{name}/{version}/"
    return {key for key in files if key == metadata_key or key.startswith(payload_prefix)}


@pytest.mark.parametrize("versioned", [False, True])
@pytest.mark.parametrize("operation", ["load", "has_object"])
def test_nested_default_save_and_read(nested_backend, versioned, operation):
    """The user's two-line example works with default settings and with versioning."""
    options = {"version_objects": True} if versioned else {}
    registry = Registry(backend=nested_backend, use_cache=False, **options)
    assert registry.version_objects is versioned
    assert registry.save("models/resnet", 1) == "1.0.0"
    assert registry.load("models/resnet", "1.0.0") == 1
    if operation == "load":
        assert registry.load("models/resnet") == 1
    else:
        assert registry.has_object("models/resnet") is True


@pytest.mark.parametrize("versioned", [False, True])
def test_nested_names_keep_parents_and_identical_leaf_names(nested_backend, versioned):
    registry = Registry(backend=nested_backend, version_objects=versioned, use_cache=False)
    names = ["flat", "models/resnet", "archive/resnet", "models/vision/resnet", "models.v2/resnet.50"]
    for value, name in enumerate(names):
        registry.save(name, value, version="1.0.0")
    assert registry.list_objects() == sorted(names)
    for value, name in enumerate(names):
        assert registry.load(name, "1.0.0") == value
        assert registry.list_versions(name) == ["1.0.0"]


@pytest.mark.parametrize("operation", ["list_versions", "latest", "next_version"])
def test_nested_versions_are_exact_and_numerically_ordered(nested_backend, operation):
    registry = Registry(backend=nested_backend, version_objects=True, use_cache=False)
    name = "models/resnet"
    for value, version in enumerate(["1.0.10", "1.0.2", "2.0.0"]):
        registry.save(name, value, version=version)
    registry.save("models/resnet2", 99, version="9.0.0")
    registry.save("models/resnet/child", 88, version="8.0.0")
    if operation == "list_versions":
        assert registry.list_versions(name) == ["1.0.2", "1.0.10", "2.0.0"]
        assert registry.list_versions("models/absent") == []
    elif operation == "latest":
        assert registry.load(name) == 2
    else:
        assert registry.save(name, 3) == "2.0.1"
        assert registry.load(name) == 3
        assert registry.load(name, "2.0.0") == 2
    assert registry.load("models/resnet2", "9.0.0") == 99
    assert registry.load("models/resnet/child", "8.0.0") == 88


@pytest.mark.parametrize("versioned", [False, True])
@pytest.mark.parametrize("delete_all", [False, True], ids=["one-version", "all-versions"])
def test_nested_delete_preserves_siblings_descendants_and_other_versions(nested_backend, versioned, delete_all):
    registry = Registry(backend=nested_backend, version_objects=versioned, use_cache=False)
    name = "models/resnet"
    registry.save(name, 1, version="1.0.0")
    if versioned:
        registry.save(name, 2, version="1.0.1")
    survivors = ["models/resnet/child", "models/resnet2", "archive/resnet"]
    for value, other in enumerate(survivors, start=10):
        registry.save(other, value, version="1.0.0")
    before = _stored_files(nested_backend)
    removed = _version_files(nested_backend, before, name, "1.0.0")
    if versioned and delete_all:
        removed |= _version_files(nested_backend, before, name, "1.0.1")

    registry.delete(name, None if delete_all else "1.0.0")

    assert _stored_files(nested_backend) == {key: value for key, value in before.items() if key not in removed}
    for value, other in enumerate(survivors, start=10):
        assert registry.load(other, "1.0.0") == value
    expected_versions = ["1.0.1"] if versioned and not delete_all else []
    assert registry.list_versions(name) == expected_versions
    if expected_versions:
        assert registry.load(name) == 2
    assert registry.list_objects() == sorted(survivors + ([name] if expected_versions else []))


@pytest.mark.parametrize("versioned", [False, True])
def test_clear_includes_nested_names_and_removes_metadata(nested_backend, versioned):
    registry = Registry(backend=nested_backend, version_objects=versioned, use_cache=False)
    empty_registry_files = _stored_files(nested_backend)
    for name in ["models/resnet", "models/resnet/child", "archive/resnet", "flat"]:
        registry.save(name, 1, version="1.0.0")
        if versioned:
            registry.save(name, 2, version="2.0.0")
    registry.clear()
    assert _stored_files(nested_backend) == empty_registry_files
    assert registry.list_objects() == []


@pytest.mark.parametrize("versioned", [False, True])
def test_reopen_preserves_existing_nested_storage_layout(nested_backend, versioned):
    registry = Registry(backend=nested_backend, version_objects=versioned, use_cache=False)
    registry.save("models/resnet", 1, version="1.0.0")
    before = _stored_files(nested_backend)
    metadata_key = "_meta_models/resnet@1.0.0.yaml"
    if not isinstance(nested_backend, LocalRegistryBackend):
        root = f"{nested_backend._prefix}/" if nested_backend._prefix else ""
        metadata_key = f"{root}_meta_models/resnet@1.0.0.json"
    assert metadata_key in before

    reopened = Registry(backend=nested_backend, use_cache=False)
    assert reopened.version_objects is versioned
    assert reopened.load("models/resnet", "1.0.0") == 1
    assert reopened.list_objects() == ["models/resnet"]
    assert reopened.list_versions("models/resnet") == ["1.0.0"]
    assert reopened.load("models/resnet") == 1
    assert _stored_files(nested_backend) == before


def test_local_discovery_ignores_payload_files_and_non_metadata_entries(tmp_path):
    registry = Registry(backend=tmp_path / "registry", version_objects=True)
    registry.save("models/resnet", 1, version="1.0.0")
    root = registry.backend.uri
    decoys = [
        "models/resnet/1.0.0/_meta_fake@9.0.0.yaml",
        "_staging/_meta_fake@9.0.0.yaml",
        "_meta_models/notes.yaml",
        "_meta_models/resnet@1.0.0.yaml.backup",
        "_meta_models/resnet@.yaml",
    ]
    for relative in decoys:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not object metadata")
    (root / "_meta_models/resnet@3.0.0.yaml").mkdir()
    assert registry.list_objects() == ["models/resnet"]
    assert registry.list_versions("models/resnet") == ["1.0.0"]
    assert registry.list_versions("models/absent") == []


@pytest.mark.parametrize("kind", ["s3", "gcp"])
def test_cached_remote_nested_name_round_trip(kind, monkeypatch, tmp_path):
    """Keep cache-enabled public entry points working without changing cache policy."""
    if kind == "s3":
        monkeypatch.setattr("mindtrace.registry.backends.s3_registry_backend.S3StorageHandler", MockS3Handler)
        backend = S3RegistryBackend(
            uri=tmp_path / "remote", endpoint="example.invalid", access_key="test", secret_key="test", bucket="nested"
        )
    else:
        monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.GCSStorageHandler", MockGCSHandler)
        backend = GCPRegistryBackend(
            uri=tmp_path / "remote",
            project_id="test",
            bucket_name="nested",
            credentials_path=str(tmp_path / "unused-credentials.json"),
        )
    registry = Registry(backend=backend, version_objects=True, use_cache=True)
    registry.save("models/resnet", 1)
    registry.save("models/resnet", 2)
    assert registry.list_objects() == ["models/resnet"]
    assert registry.list_versions("models/resnet") == ["1.0.0", "1.0.1"]
    assert registry.load("models/resnet") == 2
    assert registry.load("models/resnet", "1.0.0") == 1
