"""RabbitMQ Jobs publication throughput benchmark."""

from __future__ import annotations

import threading
import time
from types import MappingProxyType

from pydantic import BaseModel, Field

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema
from mindtrace.jobs import Orchestrator, RabbitMQClient
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


class JobsPublishCeilingInput(BaseModel):
    """Parameters for sustained RabbitMQ batch publication."""

    payload_size_bytes: int = Field(256, ge=0, description="Deterministic payload size per job.")
    batch_size: int = Field(250, ge=1, description="Messages submitted by each publish API call.")
    producer_count: int = Field(1, ge=1, description="Independent producer threads and connections.")
    latency_sample_limit: int = Field(10_000, ge=0, description="Maximum retained batch-latency samples.")
    join_timeout_seconds: float = Field(15.0, gt=0, description="Maximum post-deadline worker join time.")


def _publish_until_deadline(
    *,
    orchestrator: Orchestrator,
    queue_name: str,
    jobs,
    payload_size: int,
    deadline: float,
    start_event: threading.Event,
    stop_event: threading.Event,
    is_cancelled,
    stats: WorkerStats,
    api_calls: list[int],
    worker_index: int,
) -> None:
    start_event.wait()
    while time.perf_counter() < deadline and not stop_event.is_set() and not is_cancelled():
        op_start = time.perf_counter()
        try:
            result = orchestrator.publish_batch(queue_name, jobs)
        except Exception as exc:  # noqa: BLE001 - benchmark records backend failures.
            stats.record(
                success=False,
                latency_seconds=time.perf_counter() - op_start,
                error=exc,
                operations=len(jobs),
            )
            api_calls[worker_index] += 1
            return

        latency = time.perf_counter() - op_start
        api_calls[worker_index] += 1
        if result.success_count:
            stats.record(
                success=True,
                latency_seconds=latency,
                bytes_processed=result.success_count * payload_size,
                operations=result.success_count,
            )
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


class JobsRabbitMQPublishCeilingSuite(BenchTestSuite):
    """Measure sustained RabbitMQ publication through the public batch API."""

    suite_id = "jobs.stress.rabbitmq_publish_ceiling"
    title = "Jobs stress — RabbitMQ publish ceiling"
    description = "Measures sustained RabbitMQ batch publication using independent producer connections."
    tags = frozenset({"stress", "jobs", "rabbitmq", "publish"})
    requires = ("rabbitmq",)
    safety = "Creates and deletes one uniquely named durable RabbitMQ queue; stress traffic is unbounded by rate."
    task_schema = TaskSchema(name=suite_id, input_schema=JobsPublishCeilingInput, output_schema=BenchResultSchema)
    resource_schema = RabbitMQBenchResources
    profiles = MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 1.0,
                "payload_size_bytes": 256,
                "batch_size": 25,
                "producer_count": 1,
            },
            "stress": {
                "duration_seconds": 10.0,
                "payload_size_bytes": 256,
                "batch_size": 250,
                "producer_count": 1,
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

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        payload_size = int(config.parameters.get("payload_size_bytes", 256))
        batch_size = int(config.parameters.get("batch_size", 250))
        producer_count = int(config.parameters.get("producer_count", 1))
        sample_limit = int(config.parameters.get("latency_sample_limit", 10_000))
        join_timeout = float(config.parameters.get("join_timeout_seconds", 15.0))
        payload = payload_text(payload_size)
        runtime = create_rabbitmq_runtime(config, suffix="publish")
        clients = [RabbitMQClient(**rabbitmq_kwargs(config)) for _ in range(producer_count)]
        orchestrators = [Orchestrator(client) for client in clients]
        worker_stats = [WorkerStats(latency_sample_limit=sample_limit) for _ in range(producer_count)]
        worker_batches = [
            make_jobs(runtime.queue_name, start=index * batch_size, count=batch_size, payload=payload)
            for index in range(producer_count)
        ]
        api_calls = [0] * producer_count
        start_event = threading.Event()
        stop_event = threading.Event()
        validation_errors: list[str] = []
        resources_retained = config.keep_resources
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        measurement_start = time.perf_counter()
        deadline = reporter.deadline(config.duration_seconds)
        threads = [
            threading.Thread(
                target=_publish_until_deadline,
                kwargs={
                    "orchestrator": orchestrators[index],
                    "queue_name": runtime.queue_name,
                    "jobs": worker_batches[index],
                    "payload_size": payload_size,
                    "deadline": deadline,
                    "start_event": start_event,
                    "stop_event": stop_event,
                    "is_cancelled": reporter.is_cancelled,
                    "stats": worker_stats[index],
                    "api_calls": api_calls,
                    "worker_index": index,
                },
                name=f"jobs-publish-{index}",
                daemon=True,
            )
            for index in range(producer_count)
        ]

        try:
            for thread in threads:
                thread.start()
            start_event.set()
            wait_for_deadline(deadline, is_cancelled=reporter.is_cancelled)
            stop_event.set()
            for thread in threads:
                thread.join(timeout=join_timeout)
                if thread.is_alive():
                    validation_errors.append(f"Producer thread {thread.name} did not stop within {join_timeout}s")
        finally:
            stop_event.set()
            for thread in threads:
                if thread.is_alive():
                    thread.join(timeout=join_timeout)
            for client, thread in zip(clients, threads, strict=True):
                if not thread.is_alive():
                    close_rabbitmq_client(client)
            resources_retained = config.keep_resources or any(thread.is_alive() for thread in threads)
            cleanup_rabbitmq_runtime(
                runtime,
                keep_resources=resources_retained,
            )

        elapsed = time.perf_counter() - measurement_start
        stats = merge_worker_stats(worker_stats, latency_sample_limit=sample_limit)
        return bench_result(
            config=config,
            started_at=started_at,
            duration_seconds=elapsed,
            stats=stats,
            validation_errors=validation_errors,
            metrics={
                "backend": "rabbitmq",
                "mode": "publish_batch",
                "payload_size_bytes": payload_size,
                "batch_size": batch_size,
                "producer_count": producer_count,
                "publish_api_calls": sum(api_calls),
                "messages_published": stats.successes,
                "messages_per_second": stats.successes / elapsed if elapsed > 0 else 0.0,
                "latency_kind": "publish_batch_api_call",
                "resources_retained": resources_retained,
                "queue_name": runtime.queue_name if resources_retained else None,
            },
        )
