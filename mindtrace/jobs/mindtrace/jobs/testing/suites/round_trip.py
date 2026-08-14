"""Local Jobs round-trip smoke benchmark."""

from __future__ import annotations

import time
from types import MappingProxyType

from pydantic import BaseModel, Field

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema
from mindtrace.jobs import Consumer
from mindtrace.jobs.testing.suites._common import (
    WorkerStats,
    bench_result,
    cleanup_local_runtime,
    create_local_runtime,
    make_job,
    payload_text,
)


class JobsRoundTripSmokeInput(BaseModel):
    """Parameters for the isolated Local round-trip smoke benchmark."""

    payload_size_bytes: int = Field(256, ge=0, description="Deterministic payload size per job.")
    latency_sample_limit: int = Field(1_000, ge=0, description="Maximum retained latency samples.")


class _RoundTripConsumer(Consumer):
    def __init__(self) -> None:
        super().__init__()
        self.received_ids: list[str] = []

    def run(self, job_dict: dict) -> dict:
        self.received_ids.append(str(job_dict.get("id", "")))
        return {}


class JobsRoundTripSmokeSuite(BenchTestSuite):
    """Exercise repeated publish/consume round trips on an isolated Local backend."""

    suite_id = "jobs.smoke.round_trip"
    title = "Jobs smoke — Local publish/consume round trip"
    description = "Publishes and consumes deterministic jobs for one second using an isolated Local backend."
    tags = frozenset({"smoke", "jobs", "local"})
    requires = ("local_disk",)
    safety = "Uses a unique temporary Local backend and removes it after the run by default."
    task_schema = TaskSchema(name=suite_id, input_schema=JobsRoundTripSmokeInput, output_schema=BenchResultSchema)
    profiles = MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 1.0,
                "payload_size_bytes": 256,
                "latency_sample_limit": 1_000,
            },
            "stress": {
                "duration_seconds": 1.0,
                "payload_size_bytes": 256,
                "latency_sample_limit": 1_000,
            },
        }
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        payload_size = int(config.parameters.get("payload_size_bytes", 256))
        sample_limit = int(config.parameters.get("latency_sample_limit", 1_000))
        payload = payload_text(payload_size)
        stats = WorkerStats(latency_sample_limit=sample_limit)
        runtime = create_local_runtime(config)
        consumer = _RoundTripConsumer()
        consumer.connect_to_orchestrator(runtime.orchestrator, runtime.queue_name)
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        measurement_start = time.perf_counter()
        deadline = reporter.deadline(config.duration_seconds)
        sequence = 0

        try:
            while time.perf_counter() < deadline and not reporter.is_cancelled():
                job = make_job(runtime.queue_name, sequence=sequence, payload=payload)
                op_start = time.perf_counter()
                try:
                    runtime.orchestrator.publish(runtime.queue_name, job)
                    attempted = consumer.consume(num_messages=1, block=True)
                    received_id = consumer.received_ids[-1] if consumer.received_ids else None
                    if attempted != 1 or received_id != job.id:
                        raise RuntimeError(
                            f"Round-trip mismatch: attempted={attempted}, "
                            f"expected_id={job.id}, received_id={received_id}"
                        )
                except Exception as exc:  # noqa: BLE001 - benchmark records failures and continues.
                    stats.record(
                        success=False,
                        latency_seconds=time.perf_counter() - op_start,
                        bytes_processed=payload_size,
                        error=exc,
                    )
                else:
                    stats.record(
                        success=True,
                        latency_seconds=time.perf_counter() - op_start,
                        bytes_processed=payload_size,
                        item_id=job.id,
                    )
                sequence += 1
        finally:
            consumer.close()
            cleanup_local_runtime(runtime, keep_resources=config.keep_resources)

        return bench_result(
            config=config,
            started_at=started_at,
            duration_seconds=time.perf_counter() - measurement_start,
            stats=stats,
            metrics={
                "backend": "local",
                "mode": "round_trip",
                "payload_size_bytes": payload_size,
                "resources_retained": config.keep_resources,
                "local_root": str(runtime.root) if config.keep_resources else None,
            },
        )
