"""Shared registry backend helpers for benchmark suites."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from pydantic import BaseModel, Field

from mindtrace.core import BenchSuiteConfig
from mindtrace.registry import GCPRegistryBackend, MinioRegistryBackend, Registry


class RegistryBackendResources(BaseModel):
    minio_endpoint: str = Field("localhost:9100", description="S3-compatible endpoint for minio backend.")
    minio_access_key: str = Field(
        "minioadmin",
        description="Access key for minio backend.",
        json_schema_extra={"secret": True},
    )
    minio_secret_key: str = Field(
        "minioadmin",
        description="Secret key for minio backend.",
        json_schema_extra={"secret": True},
    )
    minio_bucket: str = Field("stress-registry", description="Bucket for minio backend writes.")
    minio_prefix: str | None = Field(None, description="Optional object prefix for minio backend writes.")
    minio_secure: bool = Field(False, description="Whether the minio endpoint uses TLS.")
    gcs_project_id: str | None = Field(None, description="GCP project ID for gcs backend.")
    gcs_bucket_name: str | None = Field(None, description="GCS bucket name for gcs backend.")
    gcs_prefix: str | None = Field(None, description="Optional object prefix for gcs backend writes.")
    gcs_credentials_path: str | None = Field(
        None,
        description="Optional service account credentials path for gcs backend.",
        json_schema_extra={"secret": True},
    )


def build_registry(
    config: BenchSuiteConfig,
    backend: str,
    prefix: str,
) -> tuple[Registry, Callable[[], None], dict[str, object]]:
    if backend == "local":
        registry_path = Path(mkdtemp(prefix="mindtrace-registry-bench-"))
        registry = Registry(backend=registry_path, version_objects=True, mutable=True)

        def cleanup() -> None:
            if config.keep_resources:
                return
            rmtree(registry_path, ignore_errors=True)

        return registry, cleanup, {"backend": "local", "local_path": str(registry_path)}

    if backend == "minio":
        bucket = str(config.resources.get("minio_bucket", "stress-registry"))
        backend_prefix = str(config.resources.get("minio_prefix") or prefix)
        backend_obj = MinioRegistryBackend(
            endpoint=str(config.resources.get("minio_endpoint", "localhost:9100")),
            access_key=str(config.resources.get("minio_access_key", "minioadmin")),
            secret_key=str(config.resources.get("minio_secret_key", "minioadmin")),
            bucket=bucket,
            secure=as_bool(config.resources.get("minio_secure", False)),
            prefix=backend_prefix,
        )
        return (
            Registry(backend=backend_obj, version_objects=True, mutable=True, use_cache=False),
            lambda: None,
            {"backend": "minio", "bucket": bucket, "prefix": backend_prefix},
        )

    if backend in {"gcs", "gcp"}:
        bucket_name = required_resource(config, "gcs_bucket_name")
        project_id = required_resource(config, "gcs_project_id")
        backend_prefix = str(config.resources.get("gcs_prefix") or prefix)
        backend_obj = GCPRegistryBackend(
            project_id=project_id,
            bucket_name=bucket_name,
            credentials_path=config.resources.get("gcs_credentials_path"),
            prefix=backend_prefix,
        )
        return (
            Registry(backend=backend_obj, version_objects=True, mutable=True, use_cache=False),
            lambda: None,
            {"backend": "gcs", "bucket": bucket_name, "project_id": project_id, "prefix": backend_prefix},
        )

    raise ValueError(f"Unsupported registry bench backend {backend!r}; expected local, minio, or gcs")


def required_resource(config: BenchSuiteConfig, key: str) -> str:
    value = config.resources.get(key)
    if value is None or value == "":
        raise ValueError(f"Suite {config.suite_id} requires resource config key {key!r}")
    return str(value)


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
