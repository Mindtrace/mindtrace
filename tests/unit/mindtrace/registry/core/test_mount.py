from tempfile import TemporaryDirectory

import pytest

from mindtrace.registry import (
    GCPMountConfig,
    GCPServiceAccountFileAuth,
    LocalMountConfig,
    Mount,
    NoAuth,
    Registry,
    S3AccessKeyAuth,
    S3MountConfig,
    Store,
)
from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend
from mindtrace.registry.backends.registry_backend import RegistryBackend


class DummyRemoteBackend(RegistryBackend):
    def __init__(self, uri="dummy://backend", **kwargs):
        super().__init__(uri=uri, **kwargs)

    def push(self, *args, **kwargs):  # pragma: no cover - not used in these tests
        raise NotImplementedError

    def pull(self, *args, **kwargs):  # pragma: no cover - not used in these tests
        raise NotImplementedError

    def delete(self, *args, **kwargs):  # pragma: no cover - not used in these tests
        raise NotImplementedError

    def save_metadata(self, *args, **kwargs):  # pragma: no cover - not used in these tests
        raise NotImplementedError

    def fetch_metadata(self, *args, **kwargs):  # pragma: no cover - not used in these tests
        raise NotImplementedError

    def delete_metadata(self, *args, **kwargs):  # pragma: no cover - not used in these tests
        raise NotImplementedError

    def save_registry_metadata(self, metadata: dict) -> None:  # pragma: no cover - not used in these tests
        return None

    def fetch_registry_metadata(self) -> dict:  # pragma: no cover - not used in these tests
        return {}

    def list_objects(self):  # pragma: no cover - not used in these tests
        return []

    def list_versions(self, name):  # pragma: no cover - not used in these tests
        return {}

    def has_object(self, name, version):  # pragma: no cover - not used in these tests
        return {}

    def register_materializer(self, object_class, materializer_class):  # pragma: no cover - not used in these tests
        return None

    def registered_materializers(self, object_class=None):  # pragma: no cover - not used in these tests
        return {}


class DummyS3Backend(DummyRemoteBackend):
    pass


class DummyGCPBackend(DummyRemoteBackend):
    pass


def test_mount_rejects_invalid_local_auth():
    with pytest.raises(TypeError):
        Mount(
            name="local",
            backend="local",
            config=LocalMountConfig(uri="/tmp/test"),
            auth=S3AccessKeyAuth(access_key="a", secret_key="b"),
        )


def test_registry_from_local_mount_builds_local_backend():
    with TemporaryDirectory() as d:
        mount = Mount(
            name="local",
            backend="local",
            config=LocalMountConfig(uri=d),
            registry_options={"version_objects": True, "mutable": True},
        )

        registry = Registry.from_mount(mount)

        assert isinstance(registry.backend, LocalRegistryBackend)
        assert registry.backend.uri.exists()
        assert registry.version_objects is True
        assert registry.mutable is True


def test_registry_from_s3_mount_builds_s3_backend(monkeypatch):
    captured = {}

    def fake_s3_backend(**kwargs):
        captured.update(kwargs)
        return DummyS3Backend(uri=f"s3://{kwargs['bucket']}/{kwargs.get('prefix', '').strip('/')}")

    monkeypatch.setattr("mindtrace.registry.backends.s3_registry_backend.S3RegistryBackend", fake_s3_backend)

    mount = Mount(
        name="nas",
        backend="s3",
        config=S3MountConfig(
            bucket="datasets",
            prefix="mindtrace/",
            endpoint="minio.local:9000",
            secure=False,
        ),
        auth=S3AccessKeyAuth(access_key="abc", secret_key="xyz"),
        registry_options={"version_objects": True},
    )

    registry = Registry.from_mount(mount)

    assert isinstance(registry.backend, DummyS3Backend)
    assert captured["bucket"] == "datasets"
    assert captured["prefix"] == "mindtrace/"
    assert captured["endpoint"] == "minio.local:9000"
    assert captured["secure"] is False
    assert captured["access_key"] == "abc"
    assert captured["secret_key"] == "xyz"
    assert registry.version_objects is True


def test_registry_from_gcp_mount_builds_gcp_backend(monkeypatch):
    captured = {}

    def fake_gcp_backend(**kwargs):
        captured.update(kwargs)
        return DummyGCPBackend(uri=f"gs://{kwargs['bucket_name']}/{kwargs.get('prefix', '').strip('/')}")

    monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.GCPRegistryBackend", fake_gcp_backend)

    mount = Mount(
        name="gcp",
        backend="gcp",
        config=GCPMountConfig(
            bucket_name="bucket-a",
            project_id="proj-1",
            prefix="datasets",
        ),
        auth=GCPServiceAccountFileAuth(path="/tmp/service-account.json"),
        registry_options={"mutable": True},
    )

    registry = Registry.from_mount(mount)

    assert isinstance(registry.backend, DummyGCPBackend)
    assert captured["bucket_name"] == "bucket-a"
    assert captured["project_id"] == "proj-1"
    assert captured["prefix"] == "datasets"
    assert captured["credentials_path"] == "/tmp/service-account.json"
    assert registry.mutable is True


def test_store_add_mount_accepts_mount_instance():
    with TemporaryDirectory() as d:
        store = Store()
        mount = Mount(
            name="local2",
            backend="local",
            config=LocalMountConfig(uri=d),
            read_only=True,
            registry_options={"version_objects": True, "mutable": True},
        )

        store.add_mount(mount)

        added = store.get_mount("local2")
        assert added.read_only is True
        assert isinstance(added.registry.backend, LocalRegistryBackend)


def test_store_from_mounts_uses_is_default_flag():
    with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
        mounts = [
            Mount(name="a", backend="local", config=LocalMountConfig(uri=d1)),
            Mount(name="b", backend="local", config=LocalMountConfig(uri=d2), is_default=True),
        ]

        store = Store.from_mounts(mounts)

        assert store.default_mount == "b"
        assert store.has_mount("a")
        assert store.has_mount("b")
        assert store.has_mount("temp")


def test_store_from_mounts_explicit_default_overrides_flag():
    with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
        mounts = [
            Mount(name="a", backend="local", config=LocalMountConfig(uri=d1), is_default=True),
            Mount(name="b", backend="local", config=LocalMountConfig(uri=d2)),
        ]

        store = Store.from_mounts(mounts, default_mount="b")

        assert store.default_mount == "b"


def test_mount_display_uri_for_remote_mounts():
    s3_mount = Mount(
        name="nas",
        backend="s3",
        config=S3MountConfig(bucket="datasets", prefix="mindtrace"),
        auth=NoAuth(),
    )
    gcp_mount = Mount(
        name="gcp",
        backend="gcp",
        config=GCPMountConfig(bucket_name="bucket-a", project_id="proj-1", prefix="exports"),
        auth=NoAuth(),
    )

    assert s3_mount.display_uri() == "s3://datasets/mindtrace"
    assert gcp_mount.display_uri() == "gs://bucket-a/exports"
