"""Configurable Jobs consumption ceiling benchmark."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema
from mindtrace.jobs import Consumer
from mindtrace.jobs.testing.suites._common import (
    BackendName,
    BackendRuntime,
    JobsBenchResources,
    WorkerStats,
    bench_result,
    cleanup_backend_runtime,
    connect_consumer,
    create_backend_runtime,
    delivery_transport,
    make_jobs,
    payload_text,
    redis_background_errors,
    validate_parameters,
    wait_for_deadline,
)

ConsumeMode = Literal["iterative_pull_one", "steady_pull", "push"]


class JobsConsumeCeilingInput(BaseModel):
    """Parameters for sustained consumption from a preloaded queue."""

    backend: BackendName = Field("rabbitmq", description="Jobs backend to exercise.")
    consume_mode: ConsumeMode = Field("push", description="Public consumption pattern to benchmark.")
    payload_size_bytes: int = Field(256, ge=0, description="Deterministic payload size per job.")
    backlog_messages: int = Field(100_000, ge=1, description="Messages preloaded before measurement.")
    preload_batch_size: int = Field(1_000, ge=1, description="Messages per preload publication call.")
    prefetch_count: int = Field(1, ge=1, description="RabbitMQ prefetch count; ignored by other backends.")
    latency_sample_limit: int = Field(10_000, ge=0, description="Maximum retained callback-latency samples.")
    join_timeout_seconds: float = Field(15.0, gt=0, description="Maximum post-deadline consumer join time.")

    @model_validator(mode="after")
    def validate_backend_mode(self) -> "JobsConsumeCeilingInput":
        if self.consume_mode == "push" and self.backend != "rabbitmq":
            raise ValueError("consume_mode='push' requires backend='rabbitmq'")
        return self


class _RecordingConsumer(Consumer):
    def __init__(self, stats: WorkerStats) -> None:
        super().__init__()
        self.stats = stats

    def run(self, job_dict: dict) -> dict:
        op_start = time.perf_counter()
        payload = job_dict.get("payload")
        payload_size = int(payload.get("payload_size_bytes", 0)) if isinstance(payload, dict) else 0
        self.stats.record(
            success=True,
            latency_seconds=time.perf_counter() - op_start,
            bytes_processed=payload_size,
            item_id=str(job_dict.get("id", "")),
        )
        return {}


@dataclass
class _ConsumeOutcome:
    attempted: int = 0
    consume_calls: int = 0
    error: BaseException | None = None


def _consume_worker(consumer: _RecordingConsumer, mode: ConsumeMode, outcome: _ConsumeOutcome) -> None:
    try:
        if mode == "iterative_pull_one":
            while not consumer.consumer_backend.stopped:
                outcome.consume_calls += 1
                outcome.attempted += consumer.consume(num_messages=1, block=True)
        elif mode == "steady_pull":
            outcome.consume_calls = 1
            outcome.attempted = consumer.consume(num_messages=2**63 - 1, block=True)
        else:
            outcome.consume_calls = 1
            outcome.attempted = consumer.consume(num_messages=0, block=True)
    except BaseException as exc:  # noqa: BLE001 - surfaced in benchmark result.
        outcome.error = exc


def _preload_jobs(*, runtime: BackendRuntime, message_count: int, batch_size: int, payload: str) -> None:
    sequence = 0
    while sequence < message_count:
        count = min(batch_size, message_count - sequence)
        jobs = make_jobs(runtime.queue_name, start=sequence, count=count, payload=payload)
        result = runtime.orchestrator.publish_batch(runtime.queue_name, jobs)
        if not result.all_succeeded:
            raise RuntimeError(
                f"Preload failed at sequence {sequence}: successes={result.success_count}, "
                f"errors={result.errors}, unattempted={result.unattempted_count}"
            )
        sequence += count


class JobsConsumeCeilingSuite(BenchTestSuite):
    """Measure selected pull or push consumption over a preloaded queue."""

    suite_id = "jobs.stress.consume_ceiling"
    title = "Jobs stress — consume ceiling"
    description = "Measures iterative, steady, or broker-pushed consumption using a selected Jobs backend."
    tags = frozenset({"stress", "jobs", "consume"})
    requires = ()
    safety = "Creates, fills, and deletes one uniquely named queue on the selected backend."
    task_schema = TaskSchema(name=suite_id, input_schema=JobsConsumeCeilingInput, output_schema=BenchResultSchema)
    resource_schema = JobsBenchResources
    profiles = MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 1.0,
                "backend": "local",
                "consume_mode": "steady_pull",
                "payload_size_bytes": 128,
                "backlog_messages": 500,
                "preload_batch_size": 250,
                "prefetch_count": 1,
            },
            "stress": {
                "duration_seconds": 10.0,
                "backend": "rabbitmq",
                "consume_mode": "push",
                "payload_size_bytes": 256,
                "backlog_messages": 100_000,
                "preload_batch_size": 1_000,
                "prefetch_count": 1,
                "latency_sample_limit": 10_000,
                "join_timeout_seconds": 15.0,
            },
        }
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        parameters = validate_parameters(config, JobsConsumeCeilingInput)
        payload = payload_text(parameters.payload_size_bytes)
        runtime = create_backend_runtime(
            config,
            backend=parameters.backend,
            suffix=f"consume-{parameters.consume_mode}",
        )
        stats = WorkerStats(latency_sample_limit=parameters.latency_sample_limit)
        consumer = _RecordingConsumer(stats)
        outcome = _ConsumeOutcome()
        thread = threading.Thread(
            target=_consume_worker,
            args=(consumer, parameters.consume_mode, outcome),
            name=f"jobs-consume-{parameters.backend}-{parameters.consume_mode}",
            daemon=True,
        )
        validation_errors: list[str] = []
        background_errors: list[str] = []
        resources_retained = config.keep_resources
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        elapsed = 0.0
        remaining_messages: int | None = None

        try:
            connect_consumer(consumer, runtime, prefetch_count=parameters.prefetch_count)
            _preload_jobs(
                runtime=runtime,
                message_count=parameters.backlog_messages,
                batch_size=parameters.preload_batch_size,
                payload=payload,
            )
            measurement_start = time.perf_counter()
            deadline = reporter.deadline(config.duration_seconds)
            thread.start()
            wait_for_deadline(deadline, is_cancelled=reporter.is_cancelled)
            consumer.stop()
            thread.join(timeout=parameters.join_timeout_seconds)
            elapsed = time.perf_counter() - measurement_start

            if thread.is_alive():
                validation_errors.append(f"Consumer thread did not stop within {parameters.join_timeout_seconds}s")
            if outcome.error is not None:
                validation_errors.append(f"Consumer raised {type(outcome.error).__name__}: {outcome.error}")
            if outcome.attempted != stats.operations:
                validation_errors.append(
                    f"Attempted-delivery count {outcome.attempted} did not match callback count {stats.operations}"
                )
            if stats.duplicate_ids:
                validation_errors.append(f"Observed {stats.duplicate_ids} duplicate job IDs")

            if not thread.is_alive():
                remaining_messages = runtime.orchestrator.count_queue_messages(runtime.queue_name)
                expected_remaining = parameters.backlog_messages - outcome.attempted
                if remaining_messages != expected_remaining:
                    validation_errors.append(
                        f"Queue count mismatch: expected {expected_remaining} remaining, observed {remaining_messages}"
                    )
                if remaining_messages == 0:
                    validation_errors.append(
                        "Preloaded backlog was exhausted before the deadline; "
                        "increase backlog_messages for a ceiling run"
                    )
        finally:
            if thread.is_alive():
                consumer.stop()
                thread.join(timeout=parameters.join_timeout_seconds)
            background_errors = redis_background_errors(
                runtime.client,
                getattr(consumer, "consumer_backend", None),
            )
            validation_errors.extend(background_errors)
            if not thread.is_alive():
                consumer.close()
            resources_retained = config.keep_resources or thread.is_alive()
            cleanup_backend_runtime(
                runtime,
                keep_resources=resources_retained,
                close_client=not thread.is_alive(),
            )

        return bench_result(
            config=config,
            started_at=started_at,
            duration_seconds=elapsed,
            stats=stats,
            validation_errors=validation_errors,
            metrics={
                "backend": parameters.backend,
                "consume_mode": parameters.consume_mode,
                "delivery_transport": delivery_transport(parameters.backend, parameters.consume_mode),
                "payload_size_bytes": parameters.payload_size_bytes,
                "backlog_messages": parameters.backlog_messages,
                "remaining_messages": remaining_messages,
                "prefetch_count": parameters.prefetch_count if parameters.backend == "rabbitmq" else None,
                "attempted_deliveries": outcome.attempted,
                "consume_api_calls": outcome.consume_calls,
                "messages_per_second": stats.successes / elapsed if elapsed > 0 else 0.0,
                "latency_kind": "consumer_callback",
                "background_errors": background_errors,
                "resources_retained": resources_retained,
                "queue_name": runtime.queue_name if resources_retained else None,
            },
        )
