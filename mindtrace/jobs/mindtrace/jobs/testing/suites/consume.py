"""RabbitMQ push and pull consumption ceiling benchmarks."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema
from mindtrace.jobs import Consumer
from mindtrace.jobs.testing.suites._common import (
    RabbitMQBenchResources,
    WorkerStats,
    bench_result,
    cleanup_rabbitmq_runtime,
    create_rabbitmq_runtime,
    make_jobs,
    payload_text,
    wait_for_deadline,
)

ConsumeMode = Literal["iterative_pull_one", "steady_pull", "push"]


class JobsConsumeCeilingInput(BaseModel):
    """Parameters shared by RabbitMQ consume ceiling modes."""

    payload_size_bytes: int = Field(256, ge=0, description="Deterministic payload size per job.")
    backlog_messages: int = Field(100_000, ge=1, description="Messages preloaded before measurement.")
    preload_batch_size: int = Field(1_000, ge=1, description="Messages per preload publication call.")
    prefetch_count: int = Field(1, ge=1, description="RabbitMQ consumer prefetch count.")
    latency_sample_limit: int = Field(10_000, ge=0, description="Maximum retained callback-latency samples.")
    join_timeout_seconds: float = Field(15.0, gt=0, description="Maximum post-deadline consumer join time.")


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


def _profiles() -> MappingProxyType:
    return MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 1.0,
                "payload_size_bytes": 128,
                "backlog_messages": 1_000,
                "preload_batch_size": 250,
                "prefetch_count": 1,
            },
            "stress": {
                "duration_seconds": 10.0,
                "payload_size_bytes": 256,
                "backlog_messages": 100_000,
                "preload_batch_size": 1_000,
                "prefetch_count": 1,
                "latency_sample_limit": 10_000,
                "join_timeout_seconds": 15.0,
                "resources": {
                    "rabbitmq_host": "localhost",
                    "rabbitmq_port": 5672,
                    "rabbitmq_username": "user",
                    "rabbitmq_password": "password",
                },
            },
        }
    )


def _preload_jobs(*, runtime, message_count: int, batch_size: int, payload: str) -> None:
    sequence = 0
    while sequence < message_count:
        count = min(batch_size, message_count - sequence)
        jobs = make_jobs(runtime.queue_name, start=sequence, count=count, payload=payload)
        result = runtime.orchestrator.publish_batch(runtime.queue_name, jobs)
        if not result.all_succeeded:
            raise RuntimeError(
                f"RabbitMQ preload failed at sequence {sequence}: "
                f"successes={result.success_count}, errors={result.errors}, unattempted={result.unattempted_count}"
            )
        sequence += count


class _RabbitMQConsumeCeilingSuite(BenchTestSuite):
    mode: ClassVar[ConsumeMode]
    tags = frozenset({"stress", "jobs", "rabbitmq", "consume"})
    requires = ("rabbitmq",)
    safety = "Creates, fills, and deletes one uniquely named durable RabbitMQ queue."
    task_schema: ClassVar[TaskSchema]
    resource_schema = RabbitMQBenchResources
    profiles = _profiles()

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        payload_size = int(config.parameters.get("payload_size_bytes", 256))
        backlog_messages = int(config.parameters.get("backlog_messages", 100_000))
        preload_batch_size = int(config.parameters.get("preload_batch_size", 1_000))
        prefetch_count = int(config.parameters.get("prefetch_count", 1))
        sample_limit = int(config.parameters.get("latency_sample_limit", 10_000))
        join_timeout = float(config.parameters.get("join_timeout_seconds", 15.0))
        payload = payload_text(payload_size)
        runtime = create_rabbitmq_runtime(config, suffix=self.mode)
        stats = WorkerStats(latency_sample_limit=sample_limit)
        consumer = _RecordingConsumer(stats)
        consumer.connect_to_orchestrator(
            runtime.orchestrator,
            runtime.queue_name,
            prefetch_count=prefetch_count,
        )
        outcome = _ConsumeOutcome()
        thread = threading.Thread(
            target=_consume_worker,
            args=(consumer, self.mode, outcome),
            name=f"jobs-consume-{self.mode}",
            daemon=True,
        )
        validation_errors: list[str] = []
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        elapsed = 0.0
        remaining_messages: int | None = None
        resources_retained = config.keep_resources

        try:
            _preload_jobs(
                runtime=runtime,
                message_count=backlog_messages,
                batch_size=preload_batch_size,
                payload=payload,
            )
            measurement_start = time.perf_counter()
            deadline = reporter.deadline(config.duration_seconds)
            thread.start()
            wait_for_deadline(deadline, is_cancelled=reporter.is_cancelled)
            consumer.stop()
            thread.join(timeout=join_timeout)
            elapsed = time.perf_counter() - measurement_start

            if thread.is_alive():
                validation_errors.append(f"Consumer thread did not stop within {join_timeout}s")
            if outcome.error is not None:
                validation_errors.append(f"Consumer raised {type(outcome.error).__name__}: {outcome.error}")
            if outcome.attempted != stats.operations:
                validation_errors.append(
                    f"Attempted-delivery count {outcome.attempted} did not match callback count {stats.operations}"
                )
            if stats.duplicate_ids:
                validation_errors.append(f"Observed {stats.duplicate_ids} duplicate job IDs")

            remaining_messages = runtime.orchestrator.count_queue_messages(runtime.queue_name)
            expected_remaining = backlog_messages - outcome.attempted
            if remaining_messages != expected_remaining:
                validation_errors.append(
                    f"Queue count mismatch: expected {expected_remaining} remaining, observed {remaining_messages}"
                )
            if remaining_messages == 0:
                validation_errors.append(
                    "Preloaded backlog was exhausted before the deadline; increase backlog_messages for a ceiling run"
                )
        finally:
            if thread.is_alive():
                consumer.stop()
                thread.join(timeout=join_timeout)
            if not thread.is_alive():
                consumer.close()
            resources_retained = config.keep_resources or thread.is_alive()
            cleanup_rabbitmq_runtime(
                runtime,
                keep_resources=resources_retained,
            )

        return bench_result(
            config=config,
            started_at=started_at,
            duration_seconds=elapsed,
            stats=stats,
            validation_errors=validation_errors,
            metrics={
                "backend": "rabbitmq",
                "mode": self.mode,
                "payload_size_bytes": payload_size,
                "backlog_messages": backlog_messages,
                "remaining_messages": remaining_messages,
                "prefetch_count": prefetch_count,
                "attempted_deliveries": outcome.attempted,
                "consume_api_calls": outcome.consume_calls,
                "messages_per_second": stats.successes / elapsed if elapsed > 0 else 0.0,
                "latency_kind": "consumer_callback",
                "resources_retained": resources_retained,
                "queue_name": runtime.queue_name if resources_retained else None,
            },
        )


class JobsRabbitMQIterativePullOneSuite(_RabbitMQConsumeCeilingSuite):
    suite_id = "jobs.stress.rabbitmq_consume_iterative_pull_one"
    title = "Jobs stress — RabbitMQ iterative consume(1) ceiling"
    description = "Measures repeated public consume(num_messages=1) calls, including per-call connection lifecycle."
    mode = "iterative_pull_one"
    task_schema = TaskSchema(name=suite_id, input_schema=JobsConsumeCeilingInput, output_schema=BenchResultSchema)


class JobsRabbitMQSteadyPullSuite(_RabbitMQConsumeCeilingSuite):
    suite_id = "jobs.stress.rabbitmq_consume_steady_pull"
    title = "Jobs stress — RabbitMQ steady basic_get ceiling"
    description = "Measures one long finite consume operation using basic_get on one connection and channel."
    mode = "steady_pull"
    task_schema = TaskSchema(name=suite_id, input_schema=JobsConsumeCeilingInput, output_schema=BenchResultSchema)


class JobsRabbitMQPushSuite(_RabbitMQConsumeCeilingSuite):
    suite_id = "jobs.stress.rabbitmq_consume_push"
    title = "Jobs stress — RabbitMQ broker-push ceiling"
    description = "Measures bare blocking consume() using basic_consume and start_consuming."
    mode = "push"
    task_schema = TaskSchema(name=suite_id, input_schema=JobsConsumeCeilingInput, output_schema=BenchResultSchema)
