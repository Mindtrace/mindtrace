"""Registry mixed read/write throughput benchmark."""

from __future__ import annotations

import random
import time
from types import MappingProxyType
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from mindtrace.core import (
    BenchReporter,
    BenchResult,
    BenchResultSchema,
    BenchSuiteConfig,
    BenchTestSuite,
    TaskSchema,
    utc_now_iso,
)
from mindtrace.core.testing.workloads import deterministic_payload, parse_size_bytes, run_threaded_until_deadline
from mindtrace.registry.testing.suites._backends import RegistryBackendResources, build_registry


class RegistryMixedRwInput(BaseModel):
    backend: Literal["local", "minio", "gcs"] = Field("local", description="Registry backend to benchmark.")
    payload_size: str = Field("64KiB", description="Generated payload size, e.g. '64KiB' or '1MiB'.")
    concurrency: int = Field(1, ge=1, description="Number of concurrent worker threads.")
    object_count: int = Field(100, ge=1, description="Objects pre-seeded before timed mixed operations.")
    read_ratio: float = Field(0.8, ge=0.0, le=1.0, description="Fraction of operations that should be reads.")


class RegistryMixedRwResources(RegistryBackendResources):
    """Resources for local, minio, and gcs registry backends."""


class RegistryMixedRwSuite(BenchTestSuite):
    suite_id = "registry.stress.mixed_rw"
    title = "Registry stress — mixed read/write throughput"
    description = "Runs configurable mixed ``Registry.load`` and ``Registry.save`` operations."
    tags = frozenset({"stress", "registry"})
    requires = ("local_disk",)
    safety = "Uses generated object prefixes; remote backends require configured resources."
    task_schema = TaskSchema(name=suite_id, input_schema=RegistryMixedRwInput, output_schema=BenchResultSchema)
    resource_schema = RegistryMixedRwResources
    profiles = MappingProxyType(
        {
            "stress": {
                "duration_seconds": 10.0,
                "backend": "local",
                "payload_size": "64KiB",
                "concurrency": 1,
                "object_count": 100,
                "read_ratio": 0.8,
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
        prefix = f"bench:{config.run_id}:{config.suite_id}:{uuid4().hex}"

        registry, cleanup, backend_metrics = build_registry(config, backend, prefix)
        try:
            names = [f"{prefix}:seed:{index:08d}" for index in range(object_count)]
            for name in names:
                registry.save(name, payload)
            deadline = reporter.deadline(config.duration_seconds)
            rng = random.Random(0)
            write_index = 0
            read_ops = 0
            write_ops = 0

            def operation() -> None:
                nonlocal read_ops, write_index, write_ops
                is_read = rng.random() < read_ratio
                name = rng.choice(names) if is_read else f"{prefix}:write:{write_index:08d}-{uuid4().hex}"
                if not is_read:
                    write_index += 1
                op_start = time.perf_counter()
                try:
                    if is_read:
                        loaded = registry.load(name)
                        if loaded != payload:
                            raise ValueError("payload mismatch")
                        read_ops += 1
                    else:
                        registry.save(name, payload)
                        write_ops += 1
                except Exception as exc:  # noqa: BLE001
                    reporter.record_operation(success=False, latency_seconds=time.perf_counter() - op_start, error=exc)
                    return
                reporter.record_operation(
                    success=True,
                    latency_seconds=time.perf_counter() - op_start,
                    bytes_processed=payload_size,
                    operation_type="read" if is_read else "write",
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
                "object_count": object_count,
                "read_ratio": read_ratio,
                "read_ops": read_ops,
                "write_ops": write_ops,
                "object_prefix": prefix,
            },
        )
