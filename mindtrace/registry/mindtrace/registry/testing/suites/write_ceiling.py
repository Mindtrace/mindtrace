"""Registry sustained write throughput (``Registry.save``), ported from legacy stress suites."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from types import MappingProxyType
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from mindtrace.core.types.task_schema import TaskSchema
from mindtrace.core.testing.bench_framework import (
    BenchReporter,
    BenchResult,
    BenchResultSchema,
    BenchSuiteConfig,
    utc_now_iso,
)
from mindtrace.core.testing.bench_suite import BenchTestSuite
from mindtrace.core.testing.workloads import deterministic_payload, parse_size_bytes, run_threaded_until_deadline
from mindtrace.registry import GCPRegistryBackend, MinioRegistryBackend, Registry


class RegistryWriteCeilingInput(BaseModel):
    backend: Literal["local", "minio", "gcs"] = Field("local", description="Registry backend to benchmark.")
    payload_size: str = Field("64KiB", description="Generated payload size, e.g. '64KiB' or '1MiB'.")
    concurrency: int = Field(1, ge=1, description="Number of concurrent writer threads.")


class RegistryWriteCeilingResources(BaseModel):
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


class RegistryWriteCeilingSuite(BenchTestSuite):
    suite_id = "registry.stress.write_ceiling"
    title = "Registry stress — sustained save throughput"
    description = (
        "Measures ``Registry.save`` throughput for ``local``, ``minio``, or ``gcs`` backends "
        "(credentials / endpoints supplied via bench ``resources``)."
    )
    tags = frozenset({"stress", "registry"})
    requires = ("local_disk",)
    safety = "Uses generated object prefixes; remote backends require configured resources."
    task_schema = TaskSchema(
        name=suite_id,
        input_schema=RegistryWriteCeilingInput,
        output_schema=BenchResultSchema,
    )
    resource_schema = RegistryWriteCeilingResources
    profiles = MappingProxyType(
        {
            "stress": {
                "duration_seconds": 10.0,
                "backend": "local",
                "payload_size": "64KiB",
                "concurrency": 1,
            },
        },
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        started = utc_now_iso()
        monotonic_start = time.perf_counter()
        backend = str(config.parameters.get("backend", "local")).lower()
        payload_size = parse_size_bytes(
            config.parameters.get("payload_size", config.parameters.get("object_size")),
            default=64 * 1024,
        )
        concurrency = int(config.parameters.get("concurrency", 1))
        payload = deterministic_payload(payload_size)
        prefix = f"bench/{config.run_id}/{config.suite_id}/{uuid4().hex}"

        registry, cleanup, backend_metrics = _build_registry(config, backend, prefix)
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

            run_threaded_until_deadline(
                concurrency,
                deadline,
                operation,
                should_continue=lambda: not reporter.is_cancelled(),
            )
        finally:
            cleanup()

        elapsed = time.perf_counter() - monotonic_start
        return BenchResult(
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


def _build_registry(
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
            secure=_as_bool(config.resources.get("minio_secure", False)),
            prefix=backend_prefix,
        )
        return (
            Registry(backend=backend_obj, version_objects=True, mutable=True, use_cache=False),
            lambda: None,
            {"backend": "minio", "bucket": bucket, "prefix": backend_prefix},
        )

    if backend in {"gcs", "gcp"}:
        bucket_name = _required_resource(config, "gcs_bucket_name")
        project_id = _required_resource(config, "gcs_project_id")
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


def _required_resource(config: BenchSuiteConfig, key: str) -> str:
    value = config.resources.get(key)
    if value is None or value == "":
        raise ValueError(f"Suite {config.suite_id} requires resource config key {key!r}")
    return str(value)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
