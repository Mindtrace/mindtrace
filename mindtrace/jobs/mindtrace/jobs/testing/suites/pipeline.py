"""Configurable Jobs end-to-end pipeline scaling benchmark."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from types import MappingProxyType

from pydantic import BaseModel, Field, model_validator

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema
from mindtrace.jobs import Consumer, Orchestrator
from mindtrace.jobs.testing.suites._common import (
    BackendName,
    JobsBenchResources,
    WorkerStats,
    bench_result,
    cleanup_backend_runtime,
    close_backend_client,
    connect_consumer,
    create_backend_runtime,
    create_backend_worker_client,
    delivery_transport,
    make_jobs,
    merge_worker_stats,
    payload_text,
    redis_background_errors,
    validate_parameters,
    validate_resources,
    wait_for_deadline,
)


class JobsPipelineScalingInput(BaseModel):
    """Parameters for concurrent producer/consumer throughput."""

    backend: BackendName = Field("rabbitmq", description="Jobs backend to exercise.")
    payload_size_bytes: int = Field(256, ge=0, description="Deterministic payload size per job.")
    batch_size: int = Field(250, ge=1, description="Messages submitted by each producer API call.")
    producer_count: int = Field(1, ge=1, description="Independent producer threads and clients.")
    consumer_count: int = Field(1, ge=1, description="Independent consumer threads.")
    prefetch_count: int = Field(1, ge=1, description="RabbitMQ prefetch count; ignored by other backends.")
    consumer_startup_seconds: float = Field(0.5, ge=0, description="Consumer startup time before producers begin.")
    latency_sample_limit: int = Field(10_000, ge=0, description="Maximum retained end-to-end latency samples.")
    join_timeout_seconds: float = Field(15.0, gt=0, description="Maximum post-deadline worker join time.")

    @model_validator(mode="after")
    def validate_backend_concurrency(self) -> "JobsPipelineScalingInput":
        if self.backend == "local":
            raise ValueError(
                "Local pipeline benchmarks are unsupported because registry-backed queues are not safe for "
                "concurrent producer/consumer access"
            )
        return self


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


def _run_pipeline_consumer(consumer: _PipelineConsumer, outcome: _PipelineConsumeOutcome) -> None:
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
                    f"Batch published {result.success_count}/{len(jobs)} messages; errors={result.errors}"
                ),
                operations=rejected,
            )
            return
        sequence += batch_size


class JobsPipelineScalingSuite(BenchTestSuite):
    """Measure end-to-end pipeline scaling on a selected Jobs backend."""

    suite_id = "jobs.stress.pipeline_scaling"
    title = "Jobs stress — pipeline scaling"
    description = "Measures concurrent publication, consumption, and work distribution on a selected backend."
    tags = frozenset({"stress", "jobs", "pipeline", "scaling"})
    requires = ()
    safety = "Creates and deletes one uniquely named queue and generates sustained traffic."
    task_schema = TaskSchema(name=suite_id, input_schema=JobsPipelineScalingInput, output_schema=BenchResultSchema)
    resource_schema = JobsBenchResources
    profiles = MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 1.0,
                "backend": "redis",
                "payload_size_bytes": 128,
                "batch_size": 25,
                "producer_count": 1,
                "consumer_count": 1,
                "prefetch_count": 1,
                "consumer_startup_seconds": 0.1,
            },
            "stress": {
                "duration_seconds": 10.0,
                "backend": "rabbitmq",
                "payload_size_bytes": 256,
                "batch_size": 250,
                "producer_count": 1,
                "consumer_count": 1,
                "prefetch_count": 1,
                "consumer_startup_seconds": 0.5,
                "latency_sample_limit": 10_000,
                "join_timeout_seconds": 15.0,
            },
        }
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        parameters = validate_parameters(config, JobsPipelineScalingInput)
        resources = validate_resources(config)
        payload = payload_text(parameters.payload_size_bytes)
        runtime = create_backend_runtime(config, backend=parameters.backend, suffix="pipeline")
        producer_clients = [runtime.client] if parameters.backend == "local" else []
        producer_orchestrators = [runtime.orchestrator] if parameters.backend == "local" else []
        producer_stats = [
            WorkerStats(latency_sample_limit=parameters.latency_sample_limit) for _ in range(parameters.producer_count)
        ]
        consumer_stats = [
            WorkerStats(latency_sample_limit=parameters.latency_sample_limit) for _ in range(parameters.consumer_count)
        ]
        api_calls = [0] * parameters.producer_count
        consumers: list[_PipelineConsumer] = []
        consume_outcomes: list[_PipelineConsumeOutcome] = []
        consumer_threads: list[threading.Thread] = []
        producer_threads: list[threading.Thread] = []
        producer_start = threading.Event()
        producer_stop = threading.Event()
        validation_errors: list[str] = []
        background_errors: list[str] = []
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        elapsed = 0.0
        remaining_messages: int | None = None
        resources_retained = config.keep_resources

        try:
            for _ in range(len(producer_clients), parameters.producer_count):
                client = create_backend_worker_client(runtime, resources)
                producer_clients.append(client)
                producer_orchestrators.append(Orchestrator(client))

            for index, stats in enumerate(consumer_stats):
                consumer = _PipelineConsumer(stats)
                try:
                    connect_consumer(consumer, runtime, prefetch_count=parameters.prefetch_count)
                except BaseException:
                    consumer.close()
                    raise
                consumers.append(consumer)
                outcome = _PipelineConsumeOutcome()
                consume_outcomes.append(outcome)
                consumer_threads.append(
                    threading.Thread(
                        target=_run_pipeline_consumer,
                        args=(consumer, outcome),
                        name=f"jobs-pipeline-{parameters.backend}-consumer-{index}",
                        daemon=True,
                    )
                )

            for thread in consumer_threads:
                thread.start()
            threading.Event().wait(parameters.consumer_startup_seconds)

            measurement_start = time.perf_counter()
            deadline = reporter.deadline(config.duration_seconds)
            producer_threads = [
                threading.Thread(
                    target=_run_pipeline_producer,
                    kwargs={
                        "orchestrator": producer_orchestrators[index],
                        "queue_name": runtime.queue_name,
                        "payload": payload,
                        "payload_size": parameters.payload_size_bytes,
                        "batch_size": parameters.batch_size,
                        "producer_index": index,
                        "deadline": deadline,
                        "start_event": producer_start,
                        "stop_event": producer_stop,
                        "stats": producer_stats[index],
                        "api_calls": api_calls,
                    },
                    name=f"jobs-pipeline-{parameters.backend}-producer-{index}",
                    daemon=True,
                )
                for index in range(parameters.producer_count)
            ]
            for thread in producer_threads:
                thread.start()
            producer_start.set()
            wait_for_deadline(deadline, is_cancelled=reporter.is_cancelled)
            producer_stop.set()
            for thread in producer_threads:
                thread.join(timeout=parameters.join_timeout_seconds)
                if thread.is_alive():
                    validation_errors.append(
                        f"Producer thread {thread.name} did not stop within {parameters.join_timeout_seconds}s"
                    )
            for consumer in consumers:
                consumer.stop()
            for thread in consumer_threads:
                thread.join(timeout=parameters.join_timeout_seconds)
                if thread.is_alive():
                    validation_errors.append(
                        f"Consumer thread {thread.name} did not stop within {parameters.join_timeout_seconds}s"
                    )
            elapsed = time.perf_counter() - measurement_start

            for index, outcome in enumerate(consume_outcomes):
                if outcome.error is not None:
                    validation_errors.append(f"Consumer {index} raised {type(outcome.error).__name__}: {outcome.error}")
                if outcome.attempted != consumer_stats[index].operations:
                    validation_errors.append(
                        f"Consumer {index} attempted {outcome.attempted} deliveries but recorded "
                        f"{consumer_stats[index].operations} callbacks"
                    )

            published = merge_worker_stats(
                producer_stats,
                latency_sample_limit=parameters.latency_sample_limit,
            )
            processed = merge_worker_stats(
                consumer_stats,
                latency_sample_limit=parameters.latency_sample_limit,
            )
            unknown_ids = processed.seen_ids.difference(published.seen_ids)
            if unknown_ids:
                validation_errors.append(f"Consumed {len(unknown_ids)} job IDs not published by this run")
            if processed.duplicate_ids:
                validation_errors.append(f"Observed {processed.duplicate_ids} duplicate deliveries")
            if published.failures:
                validation_errors.append(f"Failed or skipped {published.failures} publication attempts")

            if not any(thread.is_alive() for thread in [*producer_threads, *consumer_threads]):
                remaining_messages = runtime.orchestrator.count_queue_messages(runtime.queue_name)
                expected_remaining = published.successes - processed.successes
                if remaining_messages != expected_remaining:
                    validation_errors.append(
                        f"Pipeline balance mismatch: published={published.successes}, "
                        f"processed={processed.successes}, expected_remaining={expected_remaining}, "
                        f"observed_remaining={remaining_messages}"
                    )
        finally:
            producer_stop.set()
            producer_start.set()
            for consumer in consumers:
                if not consumer.consumer_backend.stopped:
                    consumer.stop()
            for thread in producer_threads:
                if thread.is_alive():
                    thread.join(timeout=parameters.join_timeout_seconds)
            for thread in consumer_threads:
                if thread.is_alive():
                    thread.join(timeout=parameters.join_timeout_seconds)
            background_errors = redis_background_errors(
                runtime.client,
                *producer_clients,
                *(getattr(consumer, "consumer_backend", None) for consumer in consumers),
            )
            validation_errors.extend(background_errors)
            for consumer, thread in zip(consumers, consumer_threads, strict=True):
                if not thread.is_alive():
                    consumer.close()
            for index, client in enumerate(producer_clients):
                thread = producer_threads[index] if index < len(producer_threads) else None
                if client is not runtime.client and (thread is None or not thread.is_alive()):
                    close_backend_client(client)
            all_threads = [*producer_threads, *consumer_threads]
            all_stopped = not any(thread.is_alive() for thread in all_threads)
            resources_retained = config.keep_resources or not all_stopped
            cleanup_backend_runtime(
                runtime,
                keep_resources=resources_retained,
                close_client=all_stopped,
            )

        published = merge_worker_stats(producer_stats, latency_sample_limit=parameters.latency_sample_limit)
        processed = merge_worker_stats(consumer_stats, latency_sample_limit=parameters.latency_sample_limit)
        return bench_result(
            config=config,
            started_at=started_at,
            duration_seconds=elapsed,
            stats=processed,
            validation_errors=validation_errors,
            metrics={
                "backend": parameters.backend,
                "mode": "pipeline",
                "delivery_transport": delivery_transport(
                    parameters.backend,
                    "push" if parameters.backend == "rabbitmq" else "steady_pull",
                ),
                "payload_size_bytes": parameters.payload_size_bytes,
                "batch_size": parameters.batch_size,
                "producer_count": parameters.producer_count,
                "consumer_count": parameters.consumer_count,
                "prefetch_count": parameters.prefetch_count if parameters.backend == "rabbitmq" else None,
                "publish_api_calls": sum(api_calls),
                "messages_published": published.successes,
                "messages_processed": processed.successes,
                "remaining_messages": remaining_messages,
                "per_consumer_messages": [stats.successes for stats in consumer_stats],
                "messages_per_second": processed.successes / elapsed if elapsed > 0 else 0.0,
                "latency_kind": "publish_to_consumer_end_to_end",
                "background_errors": background_errors,
                "resources_retained": resources_retained,
                "queue_name": runtime.queue_name if resources_retained else None,
            },
        )
