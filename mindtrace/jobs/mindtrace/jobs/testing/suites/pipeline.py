"""RabbitMQ end-to-end producer/consumer scaling benchmarks."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar

from pydantic import BaseModel, Field

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema
from mindtrace.jobs import Consumer, Orchestrator, RabbitMQClient
from mindtrace.jobs.testing.suites._common import (
    RabbitMQBenchResources,
    WorkerStats,
    bench_result,
    cleanup_rabbitmq_runtime,
    close_rabbitmq_client,
    create_rabbitmq_runtime,
    make_jobs,
    merge_worker_stats,
    payload_text,
    rabbitmq_kwargs,
    wait_for_deadline,
)


class JobsPipelineScalingInput(BaseModel):
    """Parameters for concurrent RabbitMQ producer/consumer throughput."""

    payload_size_bytes: int = Field(256, ge=0, description="Deterministic payload size per job.")
    batch_size: int = Field(250, ge=1, description="Messages submitted by each producer API call.")
    producer_count: int = Field(1, ge=1, description="Independent producer threads and connections.")
    prefetch_count: int = Field(1, ge=1, description="RabbitMQ prefetch count per consumer.")
    consumer_startup_seconds: float = Field(0.5, ge=0, description="Consumer registration time before producers start.")
    latency_sample_limit: int = Field(10_000, ge=0, description="Maximum retained end-to-end latency samples.")
    join_timeout_seconds: float = Field(15.0, gt=0, description="Maximum post-deadline worker join time.")


class _PipelineConsumer(Consumer):
    def __init__(self, stats: WorkerStats) -> None:
        super().__init__()
        self.stats = stats

    def run(self, job_dict: dict) -> dict:
        received_at_ns = time.perf_counter_ns()
        payload = job_dict.get("payload")
        payload_size = int(payload.get("payload_size_bytes", 0)) if isinstance(payload, dict) else 0
        sent_at_ns = int(payload.get("sent_at_ns", received_at_ns)) if isinstance(payload, dict) else received_at_ns
        self.stats.record(
            success=True,
            latency_seconds=max(0, received_at_ns - sent_at_ns) / 1_000_000_000,
            bytes_processed=payload_size,
            item_id=str(job_dict.get("id", "")),
        )
        return {}


@dataclass
class _PipelineConsumeOutcome:
    attempted: int = 0
    error: BaseException | None = None


def _run_push_consumer(consumer: _PipelineConsumer, outcome: _PipelineConsumeOutcome) -> None:
    try:
        outcome.attempted = consumer.consume(num_messages=0, block=True)
    except BaseException as exc:  # noqa: BLE001 - surfaced in benchmark result.
        outcome.error = exc


def _run_pipeline_producer(
    *,
    orchestrator: Orchestrator,
    queue_name: str,
    payload: str,
    payload_size: int,
    batch_size: int,
    producer_index: int,
    deadline: float,
    start_event: threading.Event,
    stop_event: threading.Event,
    stats: WorkerStats,
    api_calls: list[int],
) -> None:
    sequence = producer_index * 1_000_000_000
    start_event.wait()
    while time.perf_counter() < deadline and not stop_event.is_set():
        jobs = make_jobs(queue_name, start=sequence, count=batch_size, payload=payload)
        op_start = time.perf_counter()
        try:
            result = orchestrator.publish_batch(queue_name, jobs)
        except Exception as exc:  # noqa: BLE001 - benchmark records backend failures.
            stats.record(
                success=False,
                latency_seconds=time.perf_counter() - op_start,
                error=exc,
                operations=batch_size,
            )
            api_calls[producer_index] += 1
            return

        latency = time.perf_counter() - op_start
        api_calls[producer_index] += 1
        if result.success_count:
            stats.record(
                success=True,
                latency_seconds=latency,
                bytes_processed=result.success_count * payload_size,
                operations=result.success_count,
            )
            for index in result.successful_indices:
                stats.seen_ids.add(jobs[index].id)
        rejected = result.failure_count + result.unattempted_count
        if rejected:
            stats.record(
                success=False,
                latency_seconds=latency,
                error=RuntimeError(
                    f"RabbitMQ batch published {result.success_count}/{len(jobs)} messages; errors={result.errors}"
                ),
                operations=rejected,
            )
            return
        sequence += batch_size


def _profiles(consumer_count: int) -> MappingProxyType:
    return MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 1.0,
                "payload_size_bytes": 128,
                "batch_size": 25,
                "producer_count": 1,
                "prefetch_count": 1,
                "consumer_startup_seconds": 0.1,
            },
            "stress": {
                "duration_seconds": 10.0,
                "payload_size_bytes": 256,
                "batch_size": 250,
                "producer_count": 1,
                "consumer_count": consumer_count,
                "prefetch_count": 1,
                "consumer_startup_seconds": 0.5,
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


class _RabbitMQPipelineScalingSuite(BenchTestSuite):
    consumer_count: ClassVar[int]
    tags = frozenset({"stress", "jobs", "rabbitmq", "pipeline", "scaling"})
    requires = ("rabbitmq",)
    safety = "Creates and deletes one uniquely named durable RabbitMQ queue and generates sustained traffic."
    task_schema: ClassVar[TaskSchema]
    resource_schema = RabbitMQBenchResources

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        payload_size = int(config.parameters.get("payload_size_bytes", 256))
        batch_size = int(config.parameters.get("batch_size", 250))
        producer_count = int(config.parameters.get("producer_count", 1))
        consumer_count = int(config.parameters.get("consumer_count", self.consumer_count))
        prefetch_count = int(config.parameters.get("prefetch_count", 1))
        startup_seconds = float(config.parameters.get("consumer_startup_seconds", 0.5))
        sample_limit = int(config.parameters.get("latency_sample_limit", 10_000))
        join_timeout = float(config.parameters.get("join_timeout_seconds", 15.0))
        payload = payload_text(payload_size)
        runtime = create_rabbitmq_runtime(config, suffix=f"pipeline-{consumer_count}")
        producer_clients = [RabbitMQClient(**rabbitmq_kwargs(config)) for _ in range(producer_count)]
        producer_orchestrators = [Orchestrator(client) for client in producer_clients]
        producer_stats = [WorkerStats(latency_sample_limit=sample_limit) for _ in range(producer_count)]
        api_calls = [0] * producer_count
        consumer_stats = [WorkerStats(latency_sample_limit=sample_limit) for _ in range(consumer_count)]
        consumers = [_PipelineConsumer(stats) for stats in consumer_stats]
        for consumer in consumers:
            consumer.connect_to_orchestrator(
                runtime.orchestrator,
                runtime.queue_name,
                prefetch_count=prefetch_count,
            )
        consume_outcomes = [_PipelineConsumeOutcome() for _ in consumers]
        consumer_threads = [
            threading.Thread(
                target=_run_push_consumer,
                args=(consumer, consume_outcomes[index]),
                name=f"jobs-pipeline-consumer-{index}",
                daemon=True,
            )
            for index, consumer in enumerate(consumers)
        ]
        producer_start = threading.Event()
        producer_stop = threading.Event()
        validation_errors: list[str] = []
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        elapsed = 0.0
        remaining_messages: int | None = None
        producer_threads: list[threading.Thread] = []
        resources_retained = config.keep_resources

        try:
            for thread in consumer_threads:
                thread.start()
            threading.Event().wait(startup_seconds)

            measurement_start = time.perf_counter()
            deadline = reporter.deadline(config.duration_seconds)
            producer_threads = [
                threading.Thread(
                    target=_run_pipeline_producer,
                    kwargs={
                        "orchestrator": producer_orchestrators[index],
                        "queue_name": runtime.queue_name,
                        "payload": payload,
                        "payload_size": payload_size,
                        "batch_size": batch_size,
                        "producer_index": index,
                        "deadline": deadline,
                        "start_event": producer_start,
                        "stop_event": producer_stop,
                        "stats": producer_stats[index],
                        "api_calls": api_calls,
                    },
                    name=f"jobs-pipeline-producer-{index}",
                    daemon=True,
                )
                for index in range(producer_count)
            ]
            for thread in producer_threads:
                thread.start()
            producer_start.set()
            wait_for_deadline(deadline, is_cancelled=reporter.is_cancelled)
            producer_stop.set()
            for thread in producer_threads:
                thread.join(timeout=join_timeout)
                if thread.is_alive():
                    validation_errors.append(f"Producer thread {thread.name} did not stop within {join_timeout}s")
            for consumer in consumers:
                consumer.stop()
            for thread in consumer_threads:
                thread.join(timeout=join_timeout)
                if thread.is_alive():
                    validation_errors.append(f"Consumer thread {thread.name} did not stop within {join_timeout}s")
            elapsed = time.perf_counter() - measurement_start

            for index, outcome in enumerate(consume_outcomes):
                if outcome.error is not None:
                    validation_errors.append(
                        f"Consumer {index} raised {type(outcome.error).__name__}: {outcome.error}"
                    )
                if outcome.attempted != consumer_stats[index].operations:
                    validation_errors.append(
                        f"Consumer {index} attempted {outcome.attempted} deliveries but recorded "
                        f"{consumer_stats[index].operations} callbacks"
                    )

            published = merge_worker_stats(producer_stats, latency_sample_limit=sample_limit)
            processed = merge_worker_stats(consumer_stats, latency_sample_limit=sample_limit)
            unknown_ids = processed.seen_ids.difference(published.seen_ids)
            if unknown_ids:
                validation_errors.append(f"Consumed {len(unknown_ids)} job IDs that were not published by this run")
            if processed.duplicate_ids:
                validation_errors.append(f"Observed {processed.duplicate_ids} duplicate deliveries")
            if published.failures:
                validation_errors.append(f"Failed or skipped {published.failures} publication attempts")

            remaining_messages = runtime.orchestrator.count_queue_messages(runtime.queue_name)
            expected_remaining = published.successes - processed.successes
            if remaining_messages != expected_remaining:
                validation_errors.append(
                    f"Pipeline balance mismatch: published={published.successes}, processed={processed.successes}, "
                    f"expected_remaining={expected_remaining}, observed_remaining={remaining_messages}"
                )
        finally:
            producer_stop.set()
            for consumer in consumers:
                if not consumer.consumer_backend.stopped:
                    consumer.stop()
            for thread in producer_threads:
                if thread.is_alive():
                    thread.join(timeout=join_timeout)
            for thread in consumer_threads:
                if thread.is_alive():
                    thread.join(timeout=join_timeout)
            for index, client in enumerate(producer_clients):
                thread = producer_threads[index] if index < len(producer_threads) else None
                if thread is None or not thread.is_alive():
                    close_rabbitmq_client(client)
            for consumer, thread in zip(consumers, consumer_threads, strict=True):
                if not thread.is_alive():
                    consumer.close()
            all_stopped = not any(thread.is_alive() for thread in [*producer_threads, *consumer_threads])
            resources_retained = config.keep_resources or not all_stopped
            cleanup_rabbitmq_runtime(
                runtime,
                keep_resources=resources_retained,
            )

        published = merge_worker_stats(producer_stats, latency_sample_limit=sample_limit)
        processed = merge_worker_stats(consumer_stats, latency_sample_limit=sample_limit)
        per_consumer = [stats.successes for stats in consumer_stats]
        return bench_result(
            config=config,
            started_at=started_at,
            duration_seconds=elapsed,
            stats=processed,
            validation_errors=validation_errors,
            metrics={
                "backend": "rabbitmq",
                "mode": "push_pipeline",
                "payload_size_bytes": payload_size,
                "batch_size": batch_size,
                "producer_count": producer_count,
                "consumer_count": consumer_count,
                "prefetch_count": prefetch_count,
                "publish_api_calls": sum(api_calls),
                "messages_published": published.successes,
                "messages_processed": processed.successes,
                "remaining_messages": remaining_messages,
                "per_consumer_messages": per_consumer,
                "messages_per_second": processed.successes / elapsed if elapsed > 0 else 0.0,
                "latency_kind": "publish_to_consumer_end_to_end",
                "resources_retained": resources_retained,
                "queue_name": runtime.queue_name if resources_retained else None,
            },
        )


class JobsRabbitMQPipelineOneConsumerSuite(_RabbitMQPipelineScalingSuite):
    suite_id = "jobs.stress.rabbitmq_pipeline_one_consumer"
    title = "Jobs stress — RabbitMQ pipeline with one consumer"
    description = "Measures broker-pushed end-to-end throughput and latency with one consumer."
    consumer_count = 1
    task_schema = TaskSchema(name=suite_id, input_schema=JobsPipelineScalingInput, output_schema=BenchResultSchema)
    profiles = _profiles(consumer_count)


class JobsRabbitMQPipelineFourConsumersSuite(_RabbitMQPipelineScalingSuite):
    suite_id = "jobs.stress.rabbitmq_pipeline_four_consumers"
    title = "Jobs stress — RabbitMQ pipeline with four consumers"
    description = "Measures broker-pushed end-to-end throughput, latency, and distribution across four consumers."
    consumer_count = 4
    task_schema = TaskSchema(name=suite_id, input_schema=JobsPipelineScalingInput, output_schema=BenchResultSchema)
    profiles = _profiles(consumer_count)
