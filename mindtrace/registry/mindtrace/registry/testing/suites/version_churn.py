"""Registry version creation and latest-load benchmark."""

from __future__ import annotations

import time
from types import MappingProxyType
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema, utc_now_iso
from mindtrace.core.testing.workloads import deterministic_payload, parse_size_bytes, run_threaded_until_deadline
from mindtrace.registry.testing.suites._backends import RegistryBackendResources, build_registry


class RegistryVersionChurnInput(BaseModel):
    backend: Literal["local", "minio", "gcs"] = Field("local", description="Registry backend to benchmark.")
    payload_size: str = Field("16KiB", description="Generated payload size per version.")
    concurrency: int = Field(1, ge=1, description="Number of concurrent worker threads.")
    names: int = Field(10, ge=1, description="Number of logical object names to churn versions for.")
    load_latest: bool = Field(True, description="Also load latest after each save.")


class RegistryVersionChurnResources(RegistryBackendResources):
    """Resources for local, minio, and gcs registry backends."""


class RegistryVersionChurnSuite(BenchTestSuite):
    suite_id = "registry.stress.version_churn"
    title = "Registry stress — version churn"
    description = "Repeatedly saves new versions across a configurable object-name set."
    tags = frozenset({"stress", "registry"})
    requires = ("local_disk",)
    safety = "Uses generated object prefixes; remote backends require configured resources."
    task_schema = TaskSchema(name=suite_id, input_schema=RegistryVersionChurnInput, output_schema=BenchResultSchema)
    resource_schema = RegistryVersionChurnResources
    profiles = MappingProxyType(
        {
            "stress": {
                "duration_seconds": 10.0,
                "backend": "local",
                "payload_size": "16KiB",
                "concurrency": 1,
                "names": 10,
                "load_latest": True,
            },
        },
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        started = utc_now_iso()
        monotonic_start = time.perf_counter()
        backend = str(config.parameters.get("backend", "local")).lower()
        payload_size = parse_size_bytes(config.parameters.get("payload_size"), default=16 * 1024)
        concurrency = int(config.parameters.get("concurrency", 1))
        names_count = int(config.parameters.get("names", 10))
        load_latest = bool(config.parameters.get("load_latest", True))
        payload = deterministic_payload(payload_size)
        prefix = f"bench:{config.run_id}:{config.suite_id}:{uuid4().hex}"

        registry, cleanup, backend_metrics = build_registry(config, backend, prefix)
        try:
            names = [f"{prefix}:object-{index:04d}" for index in range(names_count)]
            deadline = reporter.deadline(config.duration_seconds)
            version_index = 0
            loads = 0

            def operation() -> None:
                nonlocal loads, version_index
                object_index = version_index % len(names)
                version = str((version_index // len(names)) + 1)
                version_index += 1
                name = names[object_index]
                op_start = time.perf_counter()
                try:
                    registry.save(name, payload, version=version)
                    if load_latest:
                        loaded = registry.load(name, version="latest")
                        if loaded != payload:
                            raise ValueError("latest payload mismatch")
                        loads += 1
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
                "names": names_count,
                "load_latest": load_latest,
                "latest_loads": loads,
                "object_prefix": prefix,
            },
        )
