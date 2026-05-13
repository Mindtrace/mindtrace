"""Datalake payload write throughput without asset metadata insertion."""

from __future__ import annotations

import time
from types import MappingProxyType
from uuid import uuid4

from mindtrace.core.testing.bench_framework import BenchReporter, BenchResult, BenchSuiteConfig, utc_now_iso
from mindtrace.core.testing.bench_suite import BenchTestSuite
from mindtrace.core.testing.workloads import deterministic_payload, parse_size_bytes, run_threaded_until_deadline
from mindtrace.datalake import Datalake
from mindtrace.datalake.testing.mounts import build_payload_mount


class DatalakePayloadWriteCeilingSuite(BenchTestSuite):
    suite_id = "datalake.stress.payload_write_ceiling"
    title = "Datalake stress — payload write ceiling"
    description = "Measures ``put_object`` throughput using configured mount backends."
    tags = frozenset({"stress", "datalake"})
    requires = ("local_disk",)
    safety = "Uses generated prefixes; remote backends require configured resources."
    profiles = MappingProxyType(
        {
            "stress": {
                "duration_seconds": 10.0,
                "backend": "local",
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
        payload_size = parse_size_bytes(
            config.parameters.get("payload_size", config.parameters.get("object_size")),
            default=64 * 1024,
        )
        concurrency = int(config.parameters.get("concurrency", 1))
        payload = deterministic_payload(payload_size)
        mongo_uri = str(config.resources.get("mongo_uri", "mongodb://127.0.0.1:27017"))
        mongo_db_name = str(
            config.resources.get("mongo_db_name") or f"mindtrace_bench_{config.run_id.replace('-', '_')}"
        )
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
                    lake.put_object(name=name, obj=payload, mount="stress", metadata={"run_id": config.run_id})
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
                "mount": "stress",
                "object_prefix": prefix,
            },
        )
