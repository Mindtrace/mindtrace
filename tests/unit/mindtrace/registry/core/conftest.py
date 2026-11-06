"""Registry and Store fixtures shared by core unit suites."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from mindtrace.core import Config
from mindtrace.registry import GCPRegistryBackend, LocalRegistryBackend, Registry, S3RegistryBackend, Store
from mindtrace.registry.core.mount import LocalMountConfig, Mount
from tests.utils.registry_storage import MockGCSHandler, MockS3Handler


@pytest.fixture
def temp_registry_dir():
    """Create a temporary directory for registry storage."""
    with TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def test_bytes():
    """Create test bytes."""
    return b"test bytes"


@pytest.fixture
def test_config():
    """Create a test configuration."""
    return Config()


@pytest.fixture
def test_basic_types():
    """Create test basic types."""
    return {"str": "test", "int": 42, "float": 3.14, "bool": True}


@pytest.fixture
def test_container_types():
    """Create test container types."""
    return {"list": [1, 2, 3], "dict": {"a": 1, "b": 2}, "tuple": (1, 2, 3), "set": {1, 2, 3}}


@pytest.fixture
def test_path():
    """Create a test path."""
    with TemporaryDirectory() as temp_dir:
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("test content")
        yield test_file


@pytest.fixture
def concrete_backend():
    """Create a concrete backend instance."""
    with TemporaryDirectory() as temp_dir:
        yield LocalRegistryBackend(uri=Path(temp_dir))


@pytest.fixture
def mutable_registry():
    """Create a versioned mutable registry (auto-increments on save, allows overwrites with explicit version)."""
    with TemporaryDirectory() as temp_dir:
        yield Registry(backend=temp_dir, version_objects=True, mutable=True)


@pytest.fixture
def non_versioned_immutable_registry():
    """Create a non-versioned immutable registry (write-once, raises on conflict)."""
    with TemporaryDirectory() as temp_dir:
        yield Registry(backend=temp_dir, version_objects=False, mutable=False)


@pytest.fixture
def non_versioned_registry():
    """Create a registry with versioning disabled and mutable=True for overwrites."""
    with TemporaryDirectory() as temp_dir:
        yield Registry(backend=temp_dir, version_objects=False, mutable=True)


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


@pytest.fixture
def registry(temp_registry_dir):
    """Create a Registry instance with a temporary directory."""
    return Registry(backend=temp_registry_dir, version_objects=True)


@pytest.fixture(params=["local", "cached", "store"])
def save_target(request, tmp_path):
    """Exercise local, cache-aware remote, and Store save entry points."""
    if request.param == "cached":
        registry = request.getfixturevalue("cached_mock_registry")
    else:
        registry = Registry(tmp_path / "registry", version_objects=True)
    target = Store(mounts={"local": registry}, default_mount="local") if request.param == "store" else registry
    return target, registry


@pytest.fixture(params=["core", "registry", "cached"])
def reader(request, tmp_path):
    if request.param == "cached":
        registry = request.getfixturevalue("cached_mock_registry")
    else:
        registry = Registry(backend=tmp_path / "registry", version_objects=True, mutable=True)
    return registry, registry._core if request.param == "core" else registry


@pytest.fixture(params=["core", "registry", "cached", "store"])
def batch_target(request, tmp_path):
    if request.param == "cached":
        registry = request.getfixturevalue("cached_mock_registry")
    else:
        registry = Registry(backend=tmp_path / "registry", version_objects=True, mutable=True)
    target = registry
    if request.param == "core":
        target = registry._core
    elif request.param == "store":
        target = Store({"archive": registry}, default_mount="archive")
    return target, registry


@pytest.fixture(params=["registry", "store"])
def public_registry(request, tmp_path):
    registry = Registry(backend=tmp_path / "registry", version_objects=True)
    if request.param == "store":
        return Store(mounts={"local": registry}, default_mount="local")
    return registry


@pytest.fixture(params=["local", "cached"])
def move_store(request, tmp_path):
    source = (
        request.getfixturevalue("cached_mock_registry")
        if request.param == "cached"
        else Registry(backend=tmp_path / "source", version_objects=True, mutable=True)
    )
    destination = Registry(backend=tmp_path / "destination", version_objects=True, mutable=True)
    return Store(mounts={"src": source, "dst": destination}, default_mount="dst")


@pytest.fixture
def store(tmp_path):
    return Store(
        mounts={
            "a": Registry(backend=tmp_path / "a", version_objects=True, mutable=True),
            "b": Registry(backend=tmp_path / "b", version_objects=True, mutable=True),
        },
        default_mount="a",
    )


@pytest.fixture
def basic_store():
    with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
        store = Store.from_mounts(
            [
                Mount(name="a", backend="local", config=LocalMountConfig(uri=d1), is_default=True),
                Mount(name="b", backend="local", config=LocalMountConfig(uri=d2)),
            ]
        )
        yield store


@pytest.fixture
def versioned_store():
    with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
        store = Store(
            mounts={
                "a": Registry(backend=Path(d1), version_objects=True, mutable=True),
                "b": Registry(backend=Path(d2), version_objects=True, mutable=True),
            },
            default_mount="a",
        )
        yield store


@pytest.fixture
def download_store(tmp_path, cached_mock_registry):
    local = Registry(backend=tmp_path / "local", version_objects=True)
    store = Store(mounts={"local": local}, default_mount="local")
    store.add_mount(cached_mock_registry, name="remote", read_only=True)
    return store
