"""Registry local backend write-ceiling stress suite."""

from __future__ import annotations

import time
from tempfile import TemporaryDirectory
from uuid import uuid4

from mindtrace.registry import Registry

from tests.stress.lib.benchmark import StressReporter, StressResult, StressSuiteConfig, utc_now_iso
from tests.stress.lib.workloads import deterministic_payload, parse_size_bytes, run_threaded_until_deadline


def run(config: StressSuiteConfig, reporter: StressReporter) -> StressResult:
    """Measure sustained local ``Registry.save`` payload throughput."""

    started = utc_now_iso()
    monotonic_start = time.perf_counter()
    payload_size = parse_size_bytes(config.parameters.get("payload_size"), default=64 * 1024)
    concurrency = int(config.parameters.get("concurrency", 1))
    payload = deterministic_payload(payload_size)
    prefix = f"stress/{config.run_id}/{config.suite_id}/{uuid4().hex}"

    temp_context = TemporaryDirectory(prefix="mindtrace-registry-stress-")
    try:
        registry = Registry(backend=temp_context.name, version_objects=True, mutable=True)
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
        if config.keep_resources:
            reporter.set_metric("preserved_registry_path", temp_context.name)
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
            "backend": "local",
        },
    )
