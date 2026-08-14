"""Configurable Jobs round-trip smoke benchmark."""

from __future__ import annotations

import time
from types import MappingProxyType

from pydantic import BaseModel, Field

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema
from mindtrace.jobs import Consumer
from mindtrace.jobs.testing.suites._common import (
    BackendName,
    JobsBenchResources,
    WorkerStats,
    bench_result,
    cleanup_backend_runtime,
    connect_consumer,
    create_backend_runtime,
    make_job,
    payload_text,
    validate_parameters,
)


class JobsRoundTripSmokeInput(BaseModel):
    """Parameters for a short publish/consume round-trip benchmark."""

    backend: BackendName = Field("local", description="Jobs backend to exercise.")
    payload_size_bytes: int = Field(256, ge=0, description="Deterministic payload size per job.")
    prefetch_count: int = Field(1, ge=1, description="RabbitMQ prefetch count; ignored by other backends.")
    latency_sample_limit: int = Field(1_000, ge=0, description="Maximum retained latency samples.")


class _RoundTripConsumer(Consumer):
    def __init__(self) -> None:
        super().__init__()
        self.last_received_id: str | None = None

    def run(self, job_dict: dict) -> dict:
        self.last_received_id = str(job_dict.get("id", ""))
        return {}


class JobsRoundTripSmokeSuite(BenchTestSuite):
    """Exercise repeated publish/consume round trips on a selected backend."""

    suite_id = "jobs.smoke.round_trip"
    title = "Jobs smoke — publish/consume round trip"
    description = "Publishes and consumes deterministic jobs for one second using a selected Jobs backend."
    tags = frozenset({"smoke", "jobs", "round_trip"})
    requires = ()
    safety = "Creates one uniquely named queue and removes only resources owned by the run."
    task_schema = TaskSchema(name=suite_id, input_schema=JobsRoundTripSmokeInput, output_schema=BenchResultSchema)
    resource_schema = JobsBenchResources
    profiles = MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 1.0,
                "backend": "local",
                "payload_size_bytes": 256,
                "prefetch_count": 1,
                "latency_sample_limit": 1_000,
            },
            "stress": {
                "duration_seconds": 10.0,
                "backend": "rabbitmq",
                "payload_size_bytes": 256,
                "prefetch_count": 1,
                "latency_sample_limit": 10_000,
            },
        }
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        parameters = validate_parameters(config, JobsRoundTripSmokeInput)
        payload = payload_text(parameters.payload_size_bytes)
        stats = WorkerStats(latency_sample_limit=parameters.latency_sample_limit)
        runtime = create_backend_runtime(config, backend=parameters.backend, suffix="round-trip")
        consumer = _RoundTripConsumer()
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        measurement_start = 0.0
        sequence = 0

        try:
            connect_consumer(consumer, runtime, prefetch_count=parameters.prefetch_count)
            measurement_start = time.perf_counter()
            deadline = reporter.deadline(config.duration_seconds)
            while time.perf_counter() < deadline and not reporter.is_cancelled():
                job = make_job(runtime.queue_name, sequence=sequence, payload=payload)
                op_start = time.perf_counter()
                try:
                    runtime.orchestrator.publish(runtime.queue_name, job)
                    attempted = consumer.consume(num_messages=1, block=True)
                    received_id = consumer.last_received_id
                    if attempted != 1 or received_id != job.id:
                        raise RuntimeError(
                            f"Round-trip mismatch: attempted={attempted}, "
                            f"expected_id={job.id}, received_id={received_id}"
                        )
                except Exception as exc:  # noqa: BLE001 - benchmark records failures and continues.
                    stats.record(
                        success=False,
                        latency_seconds=time.perf_counter() - op_start,
                        bytes_processed=parameters.payload_size_bytes,
                        error=exc,
                    )
                else:
                    stats.record(
                        success=True,
                        latency_seconds=time.perf_counter() - op_start,
                        bytes_processed=parameters.payload_size_bytes,
                        item_id=job.id,
                    )
                sequence += 1
        finally:
            consumer.close()
            cleanup_backend_runtime(runtime, keep_resources=config.keep_resources)

        elapsed = time.perf_counter() - measurement_start
        retained_path = str(runtime.local_root) if config.keep_resources and runtime.local_root is not None else None
        return bench_result(
            config=config,
            started_at=started_at,
            duration_seconds=elapsed,
            stats=stats,
            metrics={
                "backend": parameters.backend,
                "mode": "round_trip",
                "payload_size_bytes": parameters.payload_size_bytes,
                "messages_per_second": stats.successes / elapsed if elapsed > 0 else 0.0,
                "resources_retained": config.keep_resources,
                "queue_name": runtime.queue_name if config.keep_resources else None,
                "local_root": retained_path,
            },
        )
