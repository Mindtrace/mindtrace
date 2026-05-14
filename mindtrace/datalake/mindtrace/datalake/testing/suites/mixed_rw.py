"""Datalake mixed payload read/write benchmark."""

from __future__ import annotations

import random
import time
from types import MappingProxyType
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema, utc_now_iso
from mindtrace.core.testing.workloads import deterministic_payload, parse_size_bytes, run_threaded_until_deadline
from mindtrace.datalake import Datalake
from mindtrace.datalake.testing.mounts import build_payload_mount


class DatalakeMixedRwInput(BaseModel):
    backend: Literal["local", "minio", "gcs"] = Field("local", description="Object storage backend to benchmark.")
    payload_size: str = Field("64KiB", description="Generated payload size, e.g. '64KiB' or '1MiB'.")
    concurrency: int = Field(1, ge=1, description="Number of concurrent worker threads.")
    object_count: int = Field(100, ge=1, description="Objects pre-seeded before timed mixed operations.")
    read_ratio: float = Field(0.8, ge=0.0, le=1.0, description="Fraction of operations that should be reads.")


class DatalakeMixedRwResources(BaseModel):
    mongo_uri: str = Field("mongodb://127.0.0.1:27017", description="MongoDB URI used by the datalake ODM.")
    mongo_db_name: str | None = Field(None, description="Optional Mongo database name for this run.")
    minio_endpoint: str = Field("localhost:9100", description="S3-compatible endpoint for minio backend.")
    minio_access_key: str = Field("minioadmin", description="Access key for minio backend.", json_schema_extra={"secret": True})
    minio_secret_key: str = Field("minioadmin", description="Secret key for minio backend.", json_schema_extra={"secret": True})
    minio_bucket: str = Field("stress-registry", description="Bucket for minio backend writes.")
    minio_prefix: str | None = Field(None, description="Optional object prefix for minio backend writes.")
    minio_secure: bool = Field(False, description="Whether the minio endpoint uses TLS.")
    gcs_project_id: str | None = Field(None, description="GCP project ID for gcs backend.")
    gcs_bucket_name: str | None = Field(None, description="GCS bucket name for gcs backend.")
    gcs_prefix: str | None = Field(None, description="Optional object prefix for gcs backend writes.")
    gcs_credentials_path: str | None = Field(None, description="Optional service account credentials path for gcs backend.", json_schema_extra={"secret": True})


class DatalakeMixedRwSuite(BenchTestSuite):
    suite_id = "datalake.stress.payload_mixed_rw"
    title = "Datalake stress — mixed payload read/write"
    description = "Runs configurable mixed ``get_object`` and ``put_object`` operations."
    tags = frozenset({"stress", "datalake"})
    requires = ("local_disk",)
    safety = "Uses generated prefixes; remote backends require configured resources."
    task_schema = TaskSchema(name=suite_id, input_schema=DatalakeMixedRwInput, output_schema=BenchResultSchema)
    resource_schema = DatalakeMixedRwResources
    profiles = MappingProxyType(
        {
            "stress": {
                "duration_seconds": 10.0,
                "backend": "local",
                "payload_size": "64KiB",
                "concurrency": 1,
                "object_count": 100,
                "read_ratio": 0.8,
                "resources": {"mongo_uri": "mongodb://127.0.0.1:27017"},
            },
        },
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        started = utc_now_iso()
        monotonic_start = time.perf_counter()
        backend = str(config.parameters.get("backend", "local")).lower()
        payload_size = parse_size_bytes(config.parameters.get("payload_size"), default=64 * 1024)
        concurrency = int(config.parameters.get("concurrency", 1))
        object_count = int(config.parameters.get("object_count", 100))
        read_ratio = float(config.parameters.get("read_ratio", 0.8))
        payload = deterministic_payload(payload_size)
        mongo_uri = str(config.resources.get("mongo_uri", "mongodb://127.0.0.1:27017"))
        mongo_db_name = str(config.resources.get("mongo_db_name") or f"mindtrace_bench_{config.run_id.replace('-', '_')}")
        prefix = f"bench/{config.run_id}/{config.suite_id}/{uuid4().hex}"

        mount, cleanup, backend_metrics = build_payload_mount(config, backend, prefix)
        lake: Datalake | None = None
        read_ops = 0
        write_ops = 0
        try:
            lake = Datalake(mongo_db_uri=mongo_uri, mongo_db_name=mongo_db_name, mounts=[mount], default_mount="stress")
            lake.initialize()
            refs = [lake.put_object(name=f"{prefix}/seed/{index:08d}", obj=payload, mount="stress") for index in range(object_count)]
            deadline = reporter.deadline(config.duration_seconds)
            rng = random.Random(0)
            write_index = 0

            def operation() -> None:
                nonlocal read_ops, refs, write_index, write_ops
                is_read = rng.random() < read_ratio
                op_start = time.perf_counter()
                try:
                    if is_read:
                        loaded = lake.get_object(rng.choice(refs))
                        if loaded != payload:
                            raise ValueError("payload mismatch")
                        read_ops += 1
                    else:
                        ref = lake.put_object(name=f"{prefix}/write/{write_index:08d}-{uuid4().hex}", obj=payload, mount="stress")
                        refs.append(ref)
                        write_index += 1
                        write_ops += 1
                except Exception as exc:  # noqa: BLE001
                    reporter.record_operation(success=False, latency_seconds=time.perf_counter() - op_start, error=exc)
                    return
                reporter.record_operation(success=True, latency_seconds=time.perf_counter() - op_start, bytes_processed=payload_size, operation_type="read" if is_read else "write")

            run_threaded_until_deadline(concurrency, deadline, operation, should_continue=lambda: not reporter.is_cancelled())
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
            metrics={**reporter.metrics, **backend_metrics, "payload_size_bytes": payload_size, "concurrency": concurrency, "object_count": object_count, "read_ratio": read_ratio, "read_ops": read_ops, "write_ops": write_ops, "mount": "stress", "object_prefix": prefix},
        )
