"""Datalake object-store write-ceiling stress suite."""

from __future__ import annotations

import time
from tempfile import TemporaryDirectory
from uuid import uuid4

from mindtrace.datalake import Datalake
from mindtrace.registry import LocalMountConfig, Mount, MountBackendKind

from tests.stress.lib.benchmark import StressReporter, StressResult, StressSuiteConfig, utc_now_iso
from tests.stress.lib.workloads import deterministic_payload, parse_size_bytes, run_threaded_until_deadline


def run(config: StressSuiteConfig, reporter: StressReporter) -> StressResult:
    """Measure Datalake payload writes without metadata insertion."""

    started = utc_now_iso()
    monotonic_start = time.perf_counter()
    payload_size = parse_size_bytes(config.parameters.get("payload_size"), default=64 * 1024)
    concurrency = int(config.parameters.get("concurrency", 1))
    payload = deterministic_payload(payload_size)
    mongo_uri = config.resources.get("mongo_uri", "mongodb://localhost:27017")
    mongo_db_name = config.resources.get("mongo_db_name", f"mindtrace_stress_{config.run_id.replace('-', '_')}")
    prefix = f"stress/{config.run_id}/{config.suite_id}/{uuid4().hex}"

    temp_context = TemporaryDirectory(prefix="mindtrace-datalake-registry-stress-")
    lake: Datalake | None = None
    try:
        mounts = [
            Mount(
                name="stress",
                backend=MountBackendKind.LOCAL,
                config=LocalMountConfig(uri=temp_context.name),
                is_default=True,
            )
        ]
        lake = Datalake(mongo_db_uri=mongo_uri, mongo_db_name=mongo_db_name, mounts=mounts, default_mount="stress")
        deadline = reporter.deadline(config.duration_seconds)

        def operation() -> None:
            name = f"{prefix}/{uuid4().hex}"
            op_start = time.perf_counter()
            try:
                lake.put_object(name=name, obj=payload, mount="stress", metadata={"run_id": config.run_id})
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
        if lake is not None:
            lake.close()
        if config.keep_resources:
            reporter.set_metric("preserved_store_path", temp_context.name)
        else:
            temp_context.cleanup()

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
            "payload_size_bytes": payload_size,
            "concurrency": concurrency,
            "mount": "stress",
        },
    )
