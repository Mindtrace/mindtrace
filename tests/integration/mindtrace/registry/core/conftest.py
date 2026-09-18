"""Shared fixtures for registry core integration tests against remote backends.

MinIO (S3-compatible, local Docker) is the default remote. GCP runs as a second
parametrized backend when credentials and a test bucket are configured — the
same skip pattern as ``tests/integration/conftest.py``.
"""

from __future__ import annotations

import pytest

from mindtrace.registry import (
    AmbientAuth,
    GCSMountConfig,
    GCSServiceAccountFileAuth,
    LocalMountConfig,
    Mount,
    S3AccessKeyAuth,
    S3MountConfig,
    Store,
)


@pytest.fixture(params=[pytest.param("minio", id="minio"), pytest.param("gcp", marks=pytest.mark.gcp, id="gcp")])
def remote_kind(request):
    """Which remote object store this test should exercise."""
    return request.param


@pytest.fixture
def gcp_object_backend(gcp_test_bucket, gcp_test_prefix, gcp_project_id, gcp_credentials_path, gcs_client):
    """Function-scoped GCP backend isolated by prefix."""
    try:
        from mindtrace.registry.backends.gcp_registry_backend import GCPRegistryBackend

        backend = GCPRegistryBackend(
            uri=f"gs://{gcp_test_bucket}/{gcp_test_prefix}",
            project_id=gcp_project_id,
            bucket_name=gcp_test_bucket,
            credentials_path=gcp_credentials_path,
            prefix=gcp_test_prefix,
        )
    except Exception as exc:
        pytest.skip(f"GCP backend creation failed: {exc}")
    yield backend
    try:
        bucket = gcs_client.bucket(gcp_test_bucket)
        for blob in bucket.list_blobs(prefix=gcp_test_prefix):
            blob.delete()
    except Exception:
        pass


@pytest.fixture
def remote_object_backend(remote_kind, request):
    """Live S3/MinIO or GCS backend. Unused backends are not constructed."""
    if remote_kind == "minio":
        return request.getfixturevalue("s3_backend")
    return request.getfixturevalue("gcp_object_backend")


@pytest.fixture
def remote_and_local_store(remote_kind, temp_dir, request):
    """Store with a local default mount and a remote non-default mount.

    Unqualified keys that exist only on the remote mount are how S2 presign
    routing is observed (local backends cannot mint URLs).
    """
    local_mount = Mount(
        name="local",
        backend="local",
        config=LocalMountConfig(uri=temp_dir / "local-default"),
        is_default=True,
        registry_options={"version_objects": True, "mutable": True},
    )
    if remote_kind == "minio":
        s3_config = request.getfixturevalue("s3_config")
        remote_mount = Mount(
            name="remote",
            backend="s3",
            config=S3MountConfig(
                bucket=request.getfixturevalue("s3_test_bucket"),
                prefix=request.getfixturevalue("s3_test_prefix"),
                endpoint=s3_config["endpoint"],
                secure=s3_config["secure"],
            ),
            auth=S3AccessKeyAuth(access_key=s3_config["access_key"], secret_key=s3_config["secret_key"]),
            registry_options={"version_objects": True, "mutable": True},
        )
        yield Store.from_mounts([local_mount, remote_mount])
        return

    gcp_test_bucket = request.getfixturevalue("gcp_test_bucket")
    gcp_test_prefix = request.getfixturevalue("gcp_test_prefix")
    gcp_project_id = request.getfixturevalue("gcp_project_id")
    gcp_credentials_path = request.getfixturevalue("gcp_credentials_path")
    gcs_client = request.getfixturevalue("gcs_client")
    auth = GCSServiceAccountFileAuth(path=gcp_credentials_path) if gcp_credentials_path else AmbientAuth()
    remote_mount = Mount(
        name="remote",
        backend="gcs",
        config=GCSMountConfig(
            bucket_name=gcp_test_bucket,
            project_id=gcp_project_id,
            prefix=gcp_test_prefix,
            credentials_path=gcp_credentials_path,
        ),
        auth=auth,
        registry_options={"version_objects": True, "mutable": True},
    )
    store = Store.from_mounts([local_mount, remote_mount])
    try:
        yield store
    finally:
        try:
            bucket = gcs_client.bucket(gcp_test_bucket)
            for blob in bucket.list_blobs(prefix=gcp_test_prefix):
                blob.delete()
        except Exception:
            pass
