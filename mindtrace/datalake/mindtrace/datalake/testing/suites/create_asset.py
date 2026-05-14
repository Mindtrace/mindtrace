"""Composed ``create_asset_from_object`` throughput."""

from __future__ import annotations

import time
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
from mindtrace.datalake import Datalake
from mindtrace.datalake.testing.mongo_resolve import resolve_mongo_triple
from mindtrace.datalake.testing.mounts import build_payload_mount


class DatalakeCreateAssetFromObjectInput(BaseModel):
    backend: Literal["local", "minio", "gcs"] = Field("local", description="Object storage backend to benchmark.")
    mongo_backend: Literal["local", "atlas"] = Field("local", description="Mongo backend label to resolve.")
    payload_size: str = Field("64KiB", description="Generated payload size, e.g. '64KiB' or '1MiB'.")
    concurrency: int = Field(1, ge=1, description="Number of concurrent writer threads.")


class DatalakeCreateAssetFromObjectResources(BaseModel):
    mongo_uri: str = Field("mongodb://127.0.0.1:27017", description="MongoDB URI for local backend.")
    mongo_db_name: str | None = Field(None, description="Optional Mongo database name for this run.")
    REMOTE_MONGO_DB_URI: str | None = Field(
        None,
        description="Atlas Mongo URI for atlas backend.",
        json_schema_extra={"secret": True},
    )
    REMOTE_MONGO_DB_NAME: str | None = Field(None, description="Atlas Mongo database name for atlas backend.")
    mongo_atlas_uri: str | None = Field(
        None,
        description="Alias for REMOTE_MONGO_DB_URI.",
        json_schema_extra={"secret": True},
    )
    mongo_atlas_db_name: str | None = Field(None, description="Alias for REMOTE_MONGO_DB_NAME.")
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


class DatalakeCreateAssetFromObjectSuite(BenchTestSuite):
    suite_id = "datalake.stress.create_asset_from_object"
    title = "Datalake stress — create_asset_from_object ceiling"
    description = "Measures the composed payload + metadata write path."
    tags = frozenset({"stress", "datalake"})
    requires = ("local_disk", "mongo")
    safety = "Uses generated prefixes; remote backends require configured resources."
    task_schema = TaskSchema(
        name=suite_id,
        input_schema=DatalakeCreateAssetFromObjectInput,
        output_schema=BenchResultSchema,
    )
    resource_schema = DatalakeCreateAssetFromObjectResources
    profiles = MappingProxyType(
        {
            "stress": {
                "duration_seconds": 10.0,
                "backend": "local",
                "mongo_backend": "local",
                "payload_size": "64KiB",
                "concurrency": 1,
                "resources": {"mongo_uri": "mongodb://127.0.0.1:27017"},
            },
        },
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        started = utc_now_iso()
        monotonic_start = time.perf_counter()
        backend = str(config.parameters.get("backend", "local")).lower()
        mongo_backend, mongo_uri, mongo_db_name = resolve_mongo_triple(config)
        payload_size = parse_size_bytes(
            config.parameters.get("payload_size", config.parameters.get("object_size")),
            default=64 * 1024,
        )
        concurrency = int(config.parameters.get("concurrency", 1))
        payload = deterministic_payload(payload_size)
        prefix = f"bench/{config.run_id}/{config.suite_id}/{uuid4().hex}"

        mount, cleanup, backend_metrics = build_payload_mount(config, backend, prefix)
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
                        asset_metadata={"bench_run_id": config.run_id},
                    )
                except Exception as exc:  # noqa: BLE001
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
            if lake is not None:
                lake.close()
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
                "mongo_backend": mongo_backend,
                "mongo_db_name": mongo_db_name,
                "mount": "stress",
                "object_prefix": prefix,
            },
        )
