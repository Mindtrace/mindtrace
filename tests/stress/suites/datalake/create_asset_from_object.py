"""Composed Datalake create_asset_from_object stress suite."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from uuid import uuid4

from mindtrace.datalake import Datalake
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
from tests.stress.lib.benchmark import StressReporter, StressResult, StressSuiteConfig, utc_now_iso
from tests.stress.lib.remote_mongo import resolve_stress_atlas_mongo
from tests.stress.lib.workloads import deterministic_payload, parse_size_bytes, run_threaded_until_deadline


def run(config: StressSuiteConfig, reporter: StressReporter) -> StressResult:
    """Measure the composed payload + metadata Datalake write path."""

    started = utc_now_iso()
    monotonic_start = time.perf_counter()
    backend = str(config.parameters.get("backend", "local")).lower()
    mongo_backend, mongo_uri, mongo_db_name = resolve_mongo(config)
    payload_size = parse_size_bytes(
        config.parameters.get("payload_size", config.parameters.get("object_size")),
        default=64 * 1024,
    )
    concurrency = int(config.parameters.get("concurrency", 1))
    payload = deterministic_payload(payload_size)
    prefix = f"stress/{config.run_id}/{config.suite_id}/{uuid4().hex}"

    mount, cleanup, backend_metrics = build_mount(config, backend, prefix)
    lake: Datalake | None = None
    try:
        lake = Datalake(mongo_db_uri=mongo_uri, mongo_db_name=mongo_db_name, mounts=[mount], default_mount="stress")
        lake.initialize()
        deadline = reporter.deadline(config.duration_seconds)

        def operation() -> None:
            name = f"{prefix}/{uuid4().hex}"
            op_start = time.perf_counter()
            try:
                lake.create_asset_from_object(
                    name=name,
                    obj=payload,
                    mount="stress",
                    kind="artifact",
                    media_type="application/octet-stream",
                    size_bytes=payload_size,
                    object_metadata={"run_id": config.run_id},
                    asset_metadata={"stress_run_id": config.run_id},
                )
            except Exception as exc:  # noqa: BLE001 - benchmark records backend failures
                reporter.record_operation(success=False, latency_seconds=time.perf_counter() - op_start, error=exc)
                return
            reporter.record_operation(
                success=True,
                latency_seconds=time.perf_counter() - op_start,
                bytes_processed=payload_size,
            )

        run_threaded_until_deadline(
            concurrency, deadline, operation, should_continue=lambda: not reporter.is_cancelled()
        )
    finally:
        if lake is not None:
            lake.close()
        cleanup()

    elapsed = time.perf_counter() - monotonic_start
    return StressResult(
        suite_id=config.suite_id,
        status="passed" if reporter.failures == 0 else "failed",
        started_at=started,
        ended_at=utc_now_iso(),
        duration_seconds=elapsed,
        operations=reporter.operations,
        successes=reporter.successes,
        failures=reporter.failures,
        bytes_processed=reporter.bytes_processed,
        latency_seconds=reporter.latency_seconds,
        error_counts=reporter.error_counts,
        metrics={
            **reporter.metrics,
            **backend_metrics,
            "payload_size_bytes": payload_size,
            "concurrency": concurrency,
            "mongo_backend": mongo_backend,
            "mongo_db_name": mongo_db_name,
            "mount": "stress",
            "object_prefix": prefix,
        },
    )


def build_mount(
    config: StressSuiteConfig, backend: str, prefix: str
) -> tuple[Mount, Callable[[], None], dict[str, object]]:
    """Create a Datalake mount for the requested backend."""

    registry_options = {"mutable": True, "version_objects": True, "use_cache": False}

    if backend == "local":
        registry_path = Path(mkdtemp(prefix="mindtrace-datalake-e2e-stress-"))

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
        bucket = str(config.resources.get("minio_bucket", "stress-registry"))
        backend_prefix = str(config.resources.get("minio_prefix") or prefix)
        return (
            Mount(
                name="stress",
                backend=MountBackendKind.S3,
                config=S3MountConfig(
                    bucket=bucket,
                    prefix=backend_prefix,
                    endpoint=str(config.resources.get("minio_endpoint", "localhost:9100")),
                    secure=as_bool(config.resources.get("minio_secure", False)),
                ),
                auth=S3AccessKeyAuth(
                    access_key=str(config.resources.get("minio_access_key", "minioadmin")),
                    secret_key=str(config.resources.get("minio_secret_key", "minioadmin")),
                ),
                is_default=True,
                registry_options=registry_options,
            ),
            lambda: None,
            {"backend": "minio", "bucket": bucket, "prefix": backend_prefix},
        )

    if backend in {"gcs", "gcp"}:
        bucket_name = require_resource(config, "gcs_bucket_name")
        project_id = require_resource(config, "gcs_project_id")
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

    raise ValueError(f"Unsupported create_asset_from_object stress backend {backend!r}; expected local, minio, or gcs")


def require_resource(config: StressSuiteConfig, key: str) -> str:
    value = config.resources.get(key)
    if not value:
        raise ValueError(f"Suite {config.suite_id} requires resource config key {key!r}")
    return str(value)


def resolve_mongo(config: StressSuiteConfig) -> tuple[str, str, str]:
    backend = str(config.parameters.get("mongo_backend", "local")).lower()
    default_db_name = f"mindtrace_stress_{config.run_id.replace('-', '_')}"

    if backend == "local":
        return (
            "local",
            require_resource(config, "mongo_uri"),
            str(config.resources.get("mongo_db_name", default_db_name)),
        )

    if backend == "atlas":
        atlas_uri, atlas_db_name = resolve_stress_atlas_mongo(config.resources, default_db_name)
        return ("atlas", atlas_uri, atlas_db_name)

    raise ValueError(f"Unsupported Mongo stress backend {backend!r}; expected local or atlas")


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
