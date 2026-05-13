"""Datalake smoke wiring — local object store + Mongo reachable."""

from __future__ import annotations

import time
from types import MappingProxyType
from uuid import uuid4

from mindtrace.core.testing.bench_framework import BenchReporter, BenchResult, BenchSuiteConfig, utc_now_iso
from mindtrace.core.testing.bench_suite import BenchTestSuite
from mindtrace.core.testing.workloads import deterministic_payload
from mindtrace.datalake import Datalake
from mindtrace.datalake.testing.mongo_resolve import require_resource
from mindtrace.datalake.testing.mounts import build_payload_mount


class DatalakeSmokeSuite(BenchTestSuite):
    suite_id = "datalake.smoke.package_install"
    title = "Datalake smoke — local mount + Mongo + put_object"
    description = (
        "Creates a temporary local mount, connects to MongoDB from ``resources.mongo_uri``, "
        "and performs one ``put_object`` call."
    )
    tags = frozenset({"smoke", "datalake"})
    requires = ("local_disk", "mongo")
    profiles = MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 2.0,
                "backend": "local",
                "resources": {"mongo_uri": "mongodb://127.0.0.1:27017"},
            },
        },
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        started = utc_now_iso()
        mono = time.perf_counter()
        backend = str(config.parameters.get("backend", "local")).lower()
        mongo_uri = require_resource(config, "mongo_uri")
        mongo_db_name = str(
            config.resources.get("mongo_db_name") or f"mindtrace_bench_{config.run_id.replace('-', '_')}"
        )
        prefix = f"bench/{config.run_id}/{config.suite_id}/{uuid4().hex}"
        payload = deterministic_payload(512)

        mount, cleanup, backend_metrics = build_payload_mount(config, backend, prefix)
        lake: Datalake | None = None
        try:
            lake = Datalake(mongo_db_uri=mongo_uri, mongo_db_name=mongo_db_name, mounts=[mount], default_mount="stress")
            lake.initialize()
            op_start = time.perf_counter()
            try:
                lake.put_object(name=f"{prefix}/smoke", obj=payload, mount="stress", metadata={"run_id": config.run_id})
            except Exception as exc:  # noqa: BLE001
                reporter.record_operation(success=False, latency_seconds=time.perf_counter() - op_start, error=exc)
            else:
                reporter.record_operation(
                    success=True,
                    latency_seconds=time.perf_counter() - op_start,
                    bytes_processed=len(payload),
                )
        finally:
            if lake is not None:
                lake.close()
            cleanup()

        elapsed = time.perf_counter() - mono
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
            metrics={**reporter.metrics, **backend_metrics},
        )
