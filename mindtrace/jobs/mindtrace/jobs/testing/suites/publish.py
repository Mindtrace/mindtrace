"""Configurable Jobs publication throughput benchmark."""

from __future__ import annotations

import threading
import time
from types import MappingProxyType

from pydantic import BaseModel, Field, model_validator

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema
from mindtrace.jobs import Orchestrator
from mindtrace.jobs.testing.suites._common import (
    BackendName,
    JobsBenchResources,
    WorkerStats,
    bench_result,
    cleanup_backend_runtime,
    close_backend_client,
    create_backend_runtime,
    create_backend_worker_client,
    make_jobs,
    merge_worker_stats,
    payload_text,
    redis_background_errors,
    validate_parameters,
    validate_resources,
    wait_for_deadline,
)


class JobsPublishCeilingInput(BaseModel):
    """Parameters for sustained batch publication."""

    backend: BackendName = Field("rabbitmq", description="Jobs backend to exercise.")
    payload_size_bytes: int = Field(256, ge=0, description="Deterministic payload size per job.")
    batch_size: int = Field(250, ge=1, description="Messages submitted by each publish API call.")
    producer_count: int = Field(1, ge=1, description="Independent producer workers and clients.")
    latency_sample_limit: int = Field(10_000, ge=0, description="Maximum retained batch-latency samples.")
    join_timeout_seconds: float = Field(15.0, gt=0, description="Maximum post-deadline worker join time.")

    @model_validator(mode="after")
    def validate_backend_concurrency(self) -> "JobsPublishCeilingInput":
        if self.backend == "local" and self.producer_count != 1:
            raise ValueError("Local publish benchmarks require producer_count=1")
        return self


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
                    f"Batch published {result.success_count}/{len(jobs)} messages; errors={result.errors}"
                ),
                operations=rejected,
            )
            return


class JobsPublishCeilingSuite(BenchTestSuite):
    """Measure sustained publication through the public batch API."""

    suite_id = "jobs.stress.publish_ceiling"
    title = "Jobs stress — publish ceiling"
    description = "Measures sustained batch publication using a selected Jobs backend."
    tags = frozenset({"stress", "jobs", "publish"})
    requires = ()
    safety = "Creates one uniquely named queue and generates sustained traffic for the selected backend."
    task_schema = TaskSchema(name=suite_id, input_schema=JobsPublishCeilingInput, output_schema=BenchResultSchema)
    resource_schema = JobsBenchResources
    profiles = MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 1.0,
                "backend": "local",
                "payload_size_bytes": 128,
                "batch_size": 25,
                "producer_count": 1,
            },
            "stress": {
                "duration_seconds": 10.0,
                "backend": "rabbitmq",
                "payload_size_bytes": 256,
                "batch_size": 250,
                "producer_count": 1,
                "latency_sample_limit": 10_000,
                "join_timeout_seconds": 15.0,
            },
        }
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        parameters = validate_parameters(config, JobsPublishCeilingInput)
        resources = validate_resources(config)
        payload = payload_text(parameters.payload_size_bytes)
        runtime = create_backend_runtime(config, backend=parameters.backend, suffix="publish")
        clients = [runtime.client] if parameters.backend == "local" else []
        try:
            for _ in range(len(clients), parameters.producer_count):
                clients.append(create_backend_worker_client(runtime, resources))
        except BaseException:
            for client in clients:
                if client is not runtime.client:
                    close_backend_client(client)
            cleanup_backend_runtime(runtime, keep_resources=False)
            raise
        orchestrators = [Orchestrator(client) for client in clients]
        worker_stats = [
            WorkerStats(latency_sample_limit=parameters.latency_sample_limit) for _ in range(parameters.producer_count)
        ]
        worker_batches = [
            make_jobs(
                runtime.queue_name,
                start=index * parameters.batch_size,
                count=parameters.batch_size,
                payload=payload,
            )
            for index in range(parameters.producer_count)
        ]
        api_calls = [0] * parameters.producer_count
        start_event = threading.Event()
        stop_event = threading.Event()
        validation_errors: list[str] = []
        background_errors: list[str] = []
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
                    "payload_size": parameters.payload_size_bytes,
                    "deadline": deadline,
                    "start_event": start_event,
                    "stop_event": stop_event,
                    "is_cancelled": reporter.is_cancelled,
                    "stats": worker_stats[index],
                    "api_calls": api_calls,
                    "worker_index": index,
                },
                name=f"jobs-publish-{parameters.backend}-{index}",
                daemon=True,
            )
            for index in range(parameters.producer_count)
        ]

        try:
            for thread in threads:
                thread.start()
            start_event.set()
            wait_for_deadline(deadline, is_cancelled=reporter.is_cancelled)
            stop_event.set()
            for thread in threads:
                thread.join(timeout=parameters.join_timeout_seconds)
                if thread.is_alive():
                    validation_errors.append(
                        f"Producer thread {thread.name} did not stop within {parameters.join_timeout_seconds}s"
                    )
        finally:
            stop_event.set()
            for thread in threads:
                if thread.is_alive():
                    thread.join(timeout=parameters.join_timeout_seconds)
            background_errors = redis_background_errors(runtime.client, *clients)
            validation_errors.extend(background_errors)
            for client, thread in zip(clients, threads, strict=True):
                if client is not runtime.client and not thread.is_alive():
                    close_backend_client(client)
            resources_retained = config.keep_resources or any(thread.is_alive() for thread in threads)
            cleanup_backend_runtime(
                runtime,
                keep_resources=resources_retained,
                close_client=not any(thread.is_alive() for thread in threads),
            )

        elapsed = time.perf_counter() - measurement_start
        stats = merge_worker_stats(worker_stats, latency_sample_limit=parameters.latency_sample_limit)
        return bench_result(
            config=config,
            started_at=started_at,
            duration_seconds=elapsed,
            stats=stats,
            validation_errors=validation_errors,
            metrics={
                "backend": parameters.backend,
                "mode": "publish_batch",
                "payload_size_bytes": parameters.payload_size_bytes,
                "batch_size": parameters.batch_size,
                "producer_count": parameters.producer_count,
                "publish_api_calls": sum(api_calls),
                "messages_published": stats.successes,
                "messages_per_second": stats.successes / elapsed if elapsed > 0 else 0.0,
                "latency_kind": "publish_batch_api_call",
                "background_errors": background_errors,
                "resources_retained": resources_retained,
                "queue_name": runtime.queue_name if resources_retained else None,
            },
        )
