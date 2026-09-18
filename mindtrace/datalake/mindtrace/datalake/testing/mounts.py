"""Shared mount builders for datalake benchmark workloads."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from mindtrace.core import BenchSuiteConfig
from mindtrace.core.testing.minio import resolve_minio_bench_connection
from mindtrace.registry import (
    AmbientAuth,
    GCSMountConfig,
    GCSServiceAccountFileAuth,
    LocalMountConfig,
    Mount,
    MountBackendKind,
    S3AccessKeyAuth,
    S3MountConfig,
)


def build_payload_mount(
    config: BenchSuiteConfig,
    backend: str,
    prefix: str,
) -> tuple[Mount, Callable[[], None], dict[str, object]]:
    registry_options = {"mutable": True, "version_objects": True, "use_cache": False}

    if backend == "local":
        registry_path = Path(mkdtemp(prefix="mindtrace-datalake-bench-"))

        def cleanup() -> None:
            if config.keep_resources:
                return
            rmtree(registry_path, ignore_errors=True)

        return (
            Mount(
                name="stress",
                backend=MountBackendKind.LOCAL,
                config=LocalMountConfig(uri=registry_path),
                is_default=True,
                registry_options=registry_options,
            ),
            cleanup,
            {"backend": "local", "local_path": str(registry_path)},
        )

    if backend == "minio":
        minio = resolve_minio_bench_connection(config.resources)
        backend_prefix = str(config.resources.get("minio_prefix") or prefix)
        return (
            Mount(
                name="stress",
                backend=MountBackendKind.S3,
                config=S3MountConfig(
                    bucket=minio.bucket,
                    prefix=backend_prefix,
                    endpoint=minio.endpoint,
                    secure=minio.secure,
                ),
                auth=S3AccessKeyAuth(
                    access_key=minio.access_key,
                    secret_key=minio.secret_key,
                ),
                is_default=True,
                registry_options=registry_options,
            ),
            lambda: None,
            {"backend": "minio", "bucket": minio.bucket, "prefix": backend_prefix},
        )

    if backend in {"gcs", "gcp"}:
        bucket_name = _required_resource(config, "gcs_bucket_name")
        project_id = _required_resource(config, "gcs_project_id")
        credentials_path = config.resources.get("gcs_credentials_path")
        backend_prefix = str(config.resources.get("gcs_prefix") or prefix)
        return (
            Mount(
                name="stress",
                backend=MountBackendKind.GCS,
                config=GCSMountConfig(
                    bucket_name=bucket_name,
                    project_id=project_id,
                    prefix=backend_prefix,
                    credentials_path=credentials_path,
                ),
                auth=GCSServiceAccountFileAuth(path=credentials_path) if credentials_path else AmbientAuth(),
                is_default=True,
                registry_options=registry_options,
            ),
            lambda: None,
            {"backend": "gcs", "bucket": bucket_name, "project_id": project_id, "prefix": backend_prefix},
        )

    raise ValueError(f"Unsupported datalake bench backend {backend!r}; expected local, minio, or gcs")


def _required_resource(config: BenchSuiteConfig, key: str) -> str:
    value = config.resources.get(key)
    if value is None or value == "":
        raise ValueError(f"Suite {config.suite_id} requires resource config key {key!r}")
    return str(value)
