from tempfile import TemporaryDirectory

import pytest

from mindtrace.registry import (
    AmbientAuth,
    GCSMountConfig,
    GCSServiceAccountFileAuth,
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
        self._uri = uri
        super().__init__(uri=uri, **kwargs)

    @property
    def uri(self):
        return self._uri

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


class DummyGCSBackend(DummyRemoteBackend):
    pass


def test_mount_requires_backend():
    with pytest.raises(TypeError):
        Mount(name="local", config=LocalMountConfig(uri="/tmp/test"))


def test_mount_requires_config():
    with pytest.raises(TypeError):
        Mount(name="local", backend="local")


def test_mount_rejects_invalid_name():
    with pytest.raises(ValueError):
        Mount(name="bad/name", backend="local", config=LocalMountConfig(uri="/tmp/test"))


def test_mount_rejects_invalid_local_auth():
    with pytest.raises(TypeError):
        Mount(
            name="local",
            backend="local",
            config=LocalMountConfig(uri="/tmp/test"),
            auth=S3AccessKeyAuth(access_key="a", secret_key="b"),
        )


def test_mount_rejects_invalid_s3_config_type():
    with pytest.raises(TypeError):
        Mount(name="nas", backend="s3", config=LocalMountConfig(uri="/tmp/test"), auth=AmbientAuth())


def test_mount_rejects_invalid_s3_auth_type():
    with pytest.raises(TypeError):
        Mount(
            name="nas",
            backend="s3",
            config=S3MountConfig(bucket="datasets"),
            auth=NoAuth(),
        )


def test_mount_rejects_invalid_gcs_config_type():
    with pytest.raises(TypeError):
        Mount(name="gcs", backend="gcs", config=LocalMountConfig(uri="/tmp/test"), auth=AmbientAuth())


def test_mount_rejects_invalid_gcs_auth_type():
    with pytest.raises(TypeError):
        Mount(
            name="gcs",
            backend="gcs",
            config=GCSMountConfig(bucket_name="bucket-a", project_id="proj-1"),
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


def test_registry_from_gcs_mount_builds_gcs_backend(monkeypatch):
    captured = {}

    def fake_gcs_backend(**kwargs):
        captured.update(kwargs)
        return DummyGCSBackend(uri=f"gs://{kwargs['bucket_name']}/{kwargs.get('prefix', '').strip('/')}")

    monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.GCPRegistryBackend", fake_gcs_backend)

    mount = Mount(
        name="gcs",
        backend="gcs",
        config=GCSMountConfig(
            bucket_name="bucket-a",
            project_id="proj-1",
            prefix="datasets",
        ),
        auth=GCSServiceAccountFileAuth(path="/tmp/service-account.json"),
        registry_options={"mutable": True},
    )

    registry = Registry.from_mount(mount)

    assert isinstance(registry.backend, DummyGCSBackend)
    assert captured["bucket_name"] == "bucket-a"
    assert captured["project_id"] == "proj-1"
    assert captured["prefix"] == "datasets"
    assert captured["credentials_path"] == "/tmp/service-account.json"
    assert registry.mutable is True


def test_registry_mount_property_round_trips_local_registry():
    with TemporaryDirectory() as d:
        registry = Registry(backend=d, version_objects=True, mutable=True)
        mount = registry.mount
        assert mount.backend == "local"
        assert isinstance(mount.config, LocalMountConfig)
        assert mount.registry_options["version_objects"] is True
        assert mount.registry_options["mutable"] is True
        assert mount.auth.mode == "none"


def test_mount_from_registry_classmethod():
    with TemporaryDirectory() as d:
        registry = Registry(backend=d, version_objects=True, mutable=False)
        mount = Mount.from_registry(registry)
        assert mount.backend == "local"
        assert mount.registry_options["mutable"] is False


def test_mount_from_registry_s3_best_effort(monkeypatch):
    registry = Registry.__new__(Registry)
    backend = DummyS3Backend(uri="s3://datasets/mindtrace")
    backend.storage = type(
        "S3StorageStub",
        (),
        {"bucket_name": "datasets", "endpoint": "minio.local:9000", "secure": False},
    )()
    backend._prefix = "mindtrace"
    registry.backend = backend
    registry.version_objects = True
    registry.mutable = True
    registry.version_digits = 8

    monkeypatch.setattr("mindtrace.registry.backends.s3_registry_backend.S3RegistryBackend", DummyS3Backend)
    mount = Mount.from_registry(registry, name="s3mount")
    assert mount.name == "s3mount"
    assert mount.backend == "s3"
    assert isinstance(mount.config, S3MountConfig)
    assert mount.auth.mode == "ambient"


def test_mount_from_registry_gcs_best_effort(monkeypatch):
    registry = Registry.__new__(Registry)
    backend = DummyGCSBackend(uri="gs://bucket-a/datasets")
    backend.gcs = type("GCSStorageStub", (), {"bucket_name": "bucket-a"})()
    backend._prefix = "datasets"
    backend.config = {"MINDTRACE_GCP": {"GCP_PROJECT_ID": "proj-1"}}
    registry.backend = backend
    registry.version_objects = True
    registry.mutable = True
    registry.version_digits = 8

    monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.GCPRegistryBackend", DummyGCSBackend)
    mount = Mount.from_registry(registry, name="gcsmount")
    assert mount.name == "gcsmount"
    assert mount.backend == "gcs"
    assert isinstance(mount.config, GCSMountConfig)
    assert mount.auth.mode == "ambient"


def test_mount_from_registry_rejects_unsupported_backend():
    registry = Registry.__new__(Registry)
    registry.backend = DummyRemoteBackend(uri="dummy://backend")
    registry.version_objects = True
    registry.mutable = True
    registry.version_digits = 8
    with pytest.raises(TypeError):
        Mount.from_registry(registry)


def test_mount_name_can_be_omitted():
    mount = Mount(name=None, backend="local", config=LocalMountConfig(uri="/tmp/test"))
    assert mount.name is None


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


def test_store_add_mount_accepts_name_override_for_mount():
    with TemporaryDirectory() as d:
        store = Store()
        mount = Mount(name="local2", backend="local", config=LocalMountConfig(uri=d))
        store.add_mount(mount, name="override")
        assert store.has_mount("override")


def test_store_add_mount_accepts_registry_instance_with_name():
    with TemporaryDirectory() as d:
        store = Store()
        registry = Registry(backend=d)
        store.add_mount(registry, name="named-registry")
        assert store.has_mount("named-registry")


def test_store_add_mount_derives_name_for_nameless_mount():
    with TemporaryDirectory() as d:
        store = Store()
        mount = Mount(name=None, backend="local", config=LocalMountConfig(uri=d))
        store.add_mount(mount)
        derived = [m for m in store.list_mounts() if m != "temp"]
        assert len(derived) == 1
        assert derived[0] != "mount"


def test_store_add_mount_derives_distinct_names_for_multiple_registries():
    with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
        store = Store()
        store.add_mount(Registry(backend=d1))
        store.add_mount(Registry(backend=d2))
        derived = [m for m in store.list_mounts() if m != "temp"]
        assert len(derived) == 2
        assert derived[0] != derived[1]


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
        auth=AmbientAuth(),
    )
    gcs_mount = Mount(
        name="gcs",
        backend="gcs",
        config=GCSMountConfig(bucket_name="bucket-a", project_id="proj-1", prefix="exports"),
        auth=AmbientAuth(),
    )

    assert s3_mount.display_uri() == "s3://datasets/mindtrace"
    assert gcs_mount.display_uri() == "gs://bucket-a/exports"


def test_noauth_still_supported_for_local_mounts():
    mount = Mount(name="local", backend="local", config=LocalMountConfig(uri="/tmp/test"), auth=NoAuth())
    assert mount.auth.mode == "none"
