"""Shared helpers for Jobs benchmark suites."""

from __future__ import annotations

import random
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from typing import Any, Callable, Literal, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

from mindtrace.core import BenchResult, BenchSuiteConfig, utcnow_iso
from mindtrace.core.testing.workloads import deterministic_payload
from mindtrace.jobs import Job, LocalClient, Orchestrator, RabbitMQClient, RedisClient
from mindtrace.jobs.base.orchestrator_backend import OrchestratorBackend
from mindtrace.jobs.redis.connection import RedisConnection

BackendName = Literal["local", "redis", "rabbitmq"]
_QUEUE_COMPONENT = re.compile(r"[^a-zA-Z0-9_.-]+")
_InputModel = TypeVar("_InputModel", bound=BaseModel)


class JobsBenchResources(BaseModel):
    """Optional connection settings for every supported Jobs backend."""

    local_base_dir: Path | None = Field(
        None,
        description="Optional parent directory for the isolated Local benchmark directory.",
    )
    redis_host: str = Field("localhost", description="Redis server hostname.")
    redis_port: int = Field(6379, ge=1, le=65535, description="Redis server port.")
    redis_db: int = Field(0, ge=0, description="Redis database number.")
    rabbitmq_host: str = Field("localhost", description="RabbitMQ server hostname.")
    rabbitmq_port: int = Field(5672, ge=1, le=65535, description="RabbitMQ server port.")
    rabbitmq_username: str = Field("user", description="RabbitMQ username.")
    rabbitmq_password: str = Field(
        "password",
        description="RabbitMQ password.",
        json_schema_extra={"secret": True},
    )


@dataclass
class WorkerStats:
    """Worker-local counters with bounded reservoir latency sampling."""

    latency_sample_limit: int = 10_000
    operations: int = 0
    successes: int = 0
    failures: int = 0
    bytes_processed: int = 0
    latency_seconds: list[float] = field(default_factory=list)
    error_counts: Counter[str] = field(default_factory=Counter)
    seen_ids: set[str] = field(default_factory=set)
    duplicate_ids: int = 0
    _latencies_seen: int = 0
    _random: random.Random = field(default_factory=lambda: random.Random(0), repr=False)

    def record(
        self,
        *,
        success: bool,
        latency_seconds: float,
        bytes_processed: int = 0,
        error: BaseException | None = None,
        item_id: str | None = None,
        operations: int = 1,
    ) -> None:
        """Record one logical operation or a batch of equivalent operations."""

        self.operations += operations
        self.bytes_processed += bytes_processed
        if success:
            self.successes += operations
        else:
            self.failures += operations
            if error is not None:
                self.error_counts[type(error).__name__] += operations
        if item_id:
            if item_id in self.seen_ids:
                self.duplicate_ids += 1
            else:
                self.seen_ids.add(item_id)
        self._record_latency(latency_seconds)

    def _record_latency(self, latency_seconds: float) -> None:
        self._latencies_seen += 1
        if self.latency_sample_limit <= 0:
            return
        if len(self.latency_seconds) < self.latency_sample_limit:
            self.latency_seconds.append(latency_seconds)
            return
        replacement = self._random.randrange(self._latencies_seen)
        if replacement < self.latency_sample_limit:
            self.latency_seconds[replacement] = latency_seconds


def merge_worker_stats(stats: list[WorkerStats], *, latency_sample_limit: int) -> WorkerStats:
    """Merge worker-local counters and retain a bounded combined sample."""

    merged = WorkerStats(latency_sample_limit=latency_sample_limit)
    for worker in stats:
        merged.operations += worker.operations
        merged.successes += worker.successes
        merged.failures += worker.failures
        merged.bytes_processed += worker.bytes_processed
        merged.error_counts.update(worker.error_counts)
        merged.duplicate_ids += worker.duplicate_ids
        for item_id in worker.seen_ids:
            if item_id in merged.seen_ids:
                merged.duplicate_ids += 1
            else:
                merged.seen_ids.add(item_id)
        for latency in worker.latency_seconds:
            merged._record_latency(latency)
    return merged


@dataclass(frozen=True)
class BackendRuntime:
    """Resources owned by one benchmark variant."""

    backend: BackendName
    client: OrchestratorBackend
    orchestrator: Orchestrator
    queue_name: str
    local_root: Path | None = None


def validate_parameters(config: BenchSuiteConfig, model: type[_InputModel]) -> _InputModel:
    """Validate resolved workload parameters through the declared input model."""

    return model.model_validate(config.parameters)


def validate_resources(config: BenchSuiteConfig) -> JobsBenchResources:
    """Validate resolved backend resources."""

    return JobsBenchResources.model_validate(config.resources)


def queue_name_for(config: BenchSuiteConfig, suffix: str = "work") -> str:
    """Return a backend-safe queue name unique to a suite invocation."""

    raw = f"mindtrace.bench.{config.run_id}.{config.suite_id}.{suffix}.{uuid4().hex}"
    return _QUEUE_COMPONENT.sub("-", raw)[:220]


def create_backend_client(
    backend: BackendName,
    resources: JobsBenchResources,
    *,
    local_root: Path | None = None,
) -> OrchestratorBackend:
    """Create one client for the selected backend."""

    if backend == "local":
        if local_root is None:
            raise ValueError("local_root is required when creating a Local benchmark client")
        return LocalClient(client_dir=local_root)
    if backend == "redis":
        return RedisClient(host=resources.redis_host, port=resources.redis_port, db=resources.redis_db)
    return RabbitMQClient(
        host=resources.rabbitmq_host,
        port=resources.rabbitmq_port,
        username=resources.rabbitmq_username,
        password=resources.rabbitmq_password,
    )


def create_backend_runtime(
    config: BenchSuiteConfig,
    *,
    backend: BackendName,
    suffix: str = "work",
) -> BackendRuntime:
    """Create an isolated queue and orchestrator for the selected backend."""

    resources = validate_resources(config)
    local_root: Path | None = None
    if backend == "local":
        base_dir = resources.local_base_dir
        if base_dir is not None:
            base_dir.mkdir(parents=True, exist_ok=True)
        local_root = Path(
            mkdtemp(
                prefix="mindtrace-jobs-bench-",
                dir=str(base_dir) if base_dir is not None else None,
            )
        )

    client = create_backend_client(backend, resources, local_root=local_root)
    queue_name = queue_name_for(config, f"{backend}-{suffix}")
    try:
        declaration = client.declare_queue(queue_name, queue_type="fifo", durable=True, auto_delete=False)
        if declaration.get("status") != "success":
            raise RuntimeError(f"Failed to declare benchmark queue {queue_name!r}: {declaration}")
    except BaseException:
        close_backend_client(client)
        if local_root is not None:
            rmtree(local_root, ignore_errors=True)
        raise

    return BackendRuntime(
        backend=backend,
        client=client,
        orchestrator=Orchestrator(client),
        queue_name=queue_name,
        local_root=local_root,
    )


def create_backend_worker_client(
    runtime: BackendRuntime,
    resources: JobsBenchResources,
) -> OrchestratorBackend:
    """Create a worker client and attach it to the runtime's existing queue."""

    client = create_backend_client(runtime.backend, resources, local_root=runtime.local_root)
    if runtime.backend == "rabbitmq":
        # RabbitMQ queues are broker-owned. Batch publication opens and closes
        # its operation-local connection in the worker thread, so the client's
        # coordinator-owned bootstrap channel does not need to redeclare it.
        return client
    try:
        declaration = client.declare_queue(
            runtime.queue_name,
            queue_type="fifo",
            durable=True,
            auto_delete=False,
        )
        if declaration.get("status") != "success":
            raise RuntimeError(
                f"Failed to attach worker client to benchmark queue {runtime.queue_name!r}: {declaration}"
            )
    except BaseException:
        close_backend_client(client)
        raise
    return client


def cleanup_backend_runtime(
    runtime: BackendRuntime,
    *,
    keep_resources: bool,
    close_client: bool = True,
) -> None:
    """Delete only resources created by this benchmark invocation."""

    try:
        if not keep_resources:
            runtime.client.delete_queue(runtime.queue_name)
    finally:
        if close_client:
            close_backend_client(runtime.client)
        if runtime.local_root is not None and not keep_resources:
            rmtree(runtime.local_root, ignore_errors=True)


def close_backend_client(client: OrchestratorBackend) -> None:
    """Close backend-specific resources without assuming a common close API."""

    if isinstance(client, RedisClient):
        client.close()
    elif isinstance(client, RabbitMQClient):
        close_rabbitmq_client(client)


def close_rabbitmq_client(client: RabbitMQClient) -> None:
    """Close persistent resources retained by a RabbitMQ client."""

    channel = getattr(client, "_channel", None)
    if channel is not None and getattr(channel, "is_open", False):
        channel.close()
    connection = getattr(client, "_connection", None)
    if connection is not None:
        connection.close()


def redis_background_errors(*owners: object) -> list[str]:
    """Return unexpected Redis listener failures owned by benchmark resources."""

    errors: list[str] = []
    seen_connections: set[int] = set()
    for owner in owners:
        connection = owner if isinstance(owner, RedisConnection) else getattr(owner, "connection", None)
        if not isinstance(connection, RedisConnection) or id(connection) in seen_connections:
            continue
        seen_connections.add(id(connection))
        error = connection.event_listener_error
        if error is not None:
            errors.append(
                f"Redis event listener {connection.host}:{connection.port}/{connection.db} raised "
                f"{type(error).__name__}: {error}"
            )
    return errors


def connect_consumer(consumer, runtime: BackendRuntime, *, prefetch_count: int) -> None:
    """Connect a consumer with only backend-supported options."""

    kwargs: dict[str, Any] = {}
    if runtime.backend == "rabbitmq":
        kwargs["prefetch_count"] = prefetch_count
    elif runtime.backend == "redis":
        kwargs["poll_timeout"] = 1
    else:
        kwargs["poll_timeout"] = 0.1
    consumer.connect_to_orchestrator(runtime.orchestrator, runtime.queue_name, **kwargs)


def delivery_transport(backend: BackendName, consume_mode: str) -> str:
    """Describe the backend mechanism used by a consume workload."""

    if backend == "rabbitmq":
        return "basic_consume" if consume_mode == "push" else "basic_get"
    if backend == "redis":
        return "redis_pop"
    return "local_pop"


def payload_text(size_bytes: int) -> str:
    """Return deterministic JSON-safe text with approximately the requested size."""

    return deterministic_payload(max(0, size_bytes)).decode("ascii")


def make_job(queue_name: str, *, sequence: int, payload: str, sent_at_ns: int | None = None) -> Job:
    """Build a deterministic benchmark job with unique identity and timing metadata."""

    return Job(
        id=uuid4().hex,
        name=queue_name,
        schema_name=queue_name,
        payload={
            "sequence": sequence,
            "sent_at_ns": sent_at_ns if sent_at_ns is not None else time.perf_counter_ns(),
            "payload_size_bytes": len(payload),
            "data": payload,
        },
        created_at=utcnow_iso(),
    )


def make_jobs(queue_name: str, *, start: int, count: int, payload: str) -> list[Job]:
    """Build one ordered benchmark batch."""

    sent_at_ns = time.perf_counter_ns()
    return [
        make_job(queue_name, sequence=start + offset, payload=payload, sent_at_ns=sent_at_ns) for offset in range(count)
    ]


def wait_for_deadline(deadline: float, *, is_cancelled: Callable[[], bool]) -> None:
    """Wait cooperatively for a monotonic deadline."""

    import threading

    waiter = threading.Event()
    while not is_cancelled():
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        waiter.wait(min(remaining, 0.05))


def bench_result(
    *,
    config: BenchSuiteConfig,
    started_at: str,
    duration_seconds: float,
    stats: WorkerStats,
    metrics: dict[str, Any],
    validation_errors: list[str] | None = None,
) -> BenchResult:
    """Build a standard Jobs benchmark result."""

    errors = list(validation_errors or [])
    status = "passed" if stats.operations > 0 and stats.failures == 0 and not errors else "failed"
    return BenchResult(
        suite_id=config.suite_id,
        status=status,
        started_at=started_at,
        ended_at=utcnow_iso(),
        duration_seconds=max(duration_seconds, 0.0),
        operations=stats.operations,
        successes=stats.successes,
        failures=stats.failures + len(errors),
        bytes_processed=stats.bytes_processed,
        latency_seconds=stats.latency_seconds,
        error_counts=dict(stats.error_counts),
        metrics={
            **metrics,
            "latency_samples": len(stats.latency_seconds),
            "latency_sample_limit": stats.latency_sample_limit,
            "duplicate_ids": stats.duplicate_ids,
            "validation_errors": errors,
        },
    )
