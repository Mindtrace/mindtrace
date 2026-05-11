"""Registry write-ceiling stress suite for local, MinIO/S3, and GCS backends."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from uuid import uuid4

from mindtrace.registry import GCPRegistryBackend, MinioRegistryBackend, Registry

from tests.stress.lib.benchmark import StressReporter, StressResult, StressSuiteConfig, utc_now_iso
from tests.stress.lib.workloads import deterministic_payload, parse_size_bytes, run_threaded_until_deadline


def run(config: StressSuiteConfig, reporter: StressReporter) -> StressResult:
    """Measure sustained ``Registry.save`` payload throughput for a selected backend."""

    started = utc_now_iso()
    monotonic_start = time.perf_counter()
    backend = str(config.parameters.get("backend", "local")).lower()
    payload_size = parse_size_bytes(
        config.parameters.get("payload_size", config.parameters.get("object_size")),
        default=64 * 1024,
    )
    concurrency = int(config.parameters.get("concurrency", 1))
    payload = deterministic_payload(payload_size)
    prefix = f"stress/{config.run_id}/{config.suite_id}/{uuid4().hex}"

    registry, cleanup, backend_metrics = build_registry(config, backend, prefix)
    try:
        deadline = reporter.deadline(config.duration_seconds)

        def operation() -> None:
            name = f"{prefix}/{uuid4().hex}"
            op_start = time.perf_counter()
            try:
                registry.save(name, payload)
            except Exception as exc:  # noqa: BLE001 - benchmark records backend failures
                reporter.record_operation(success=False, latency_seconds=time.perf_counter() - op_start, error=exc)
                return
            reporter.record_operation(
                success=True,
                latency_seconds=time.perf_counter() - op_start,
                bytes_processed=payload_size,
            )

        run_threaded_until_deadline(concurrency, deadline, operation)
    finally:
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
            "object_prefix": prefix,
        },
    )


def build_registry(
    config: StressSuiteConfig,
    backend: str,
    prefix: str,
) -> tuple[Registry, Callable[[], None], dict[str, object]]:
    """Create the requested Registry backend for the suite run."""

    if backend == "local":
        registry_path = Path(mkdtemp(prefix="mindtrace-registry-stress-"))
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
            Registry(backend=backend_obj, version_objects=True, mutable=True),
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
            Registry(backend=backend_obj, version_objects=True, mutable=True),
            lambda: None,
            {"backend": "gcs", "bucket": bucket_name, "project_id": project_id, "prefix": backend_prefix},
        )

    raise ValueError(f"Unsupported registry stress backend {backend!r}; expected local, minio, or gcs")


def required_resource(config: StressSuiteConfig, key: str) -> str:
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
