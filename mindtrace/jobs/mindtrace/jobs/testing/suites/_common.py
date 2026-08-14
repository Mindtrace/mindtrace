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
from typing import Any, Callable
from uuid import uuid4

from pydantic import BaseModel, Field

from mindtrace.core import BenchResult, BenchSuiteConfig, utcnow_iso
from mindtrace.core.testing.workloads import deterministic_payload
from mindtrace.jobs import Job, LocalClient, Orchestrator, RabbitMQClient

_QUEUE_COMPONENT = re.compile(r"[^a-zA-Z0-9_.-]+")


class RabbitMQBenchResources(BaseModel):
    """Connection settings used by RabbitMQ benchmark suites."""

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
class RabbitMQRuntime:
    """Owned RabbitMQ resources for one benchmark variant."""

    client: RabbitMQClient
    orchestrator: Orchestrator
    queue_name: str


@dataclass(frozen=True)
class LocalRuntime:
    """Owned Local backend resources for one benchmark invocation."""

    client: LocalClient
    orchestrator: Orchestrator
    queue_name: str
    root: Path


def queue_name_for(config: BenchSuiteConfig, suffix: str = "work") -> str:
    """Return a RabbitMQ-safe queue name unique to a suite invocation."""

    raw = f"mindtrace.bench.{config.run_id}.{config.suite_id}.{suffix}.{uuid4().hex}"
    return _QUEUE_COMPONENT.sub("-", raw)[:220]


def rabbitmq_kwargs(config: BenchSuiteConfig) -> dict[str, Any]:
    """Resolve RabbitMQ client settings from benchmark resources."""

    return {
        "host": str(config.resources.get("rabbitmq_host", "localhost")),
        "port": int(config.resources.get("rabbitmq_port", 5672)),
        "username": str(config.resources.get("rabbitmq_username", "user")),
        "password": str(config.resources.get("rabbitmq_password", "password")),
    }


def create_rabbitmq_runtime(config: BenchSuiteConfig, *, suffix: str = "work") -> RabbitMQRuntime:
    """Create a unique durable RabbitMQ queue and its orchestrator."""

    client = RabbitMQClient(**rabbitmq_kwargs(config))
    queue_name = queue_name_for(config, suffix)
    declaration = client.declare_queue(queue_name, durable=True, auto_delete=False)
    if declaration.get("status") != "success":
        close_rabbitmq_client(client)
        raise RuntimeError(f"Failed to declare RabbitMQ benchmark queue {queue_name!r}: {declaration}")
    return RabbitMQRuntime(client=client, orchestrator=Orchestrator(client), queue_name=queue_name)


def cleanup_rabbitmq_runtime(runtime: RabbitMQRuntime, *, keep_resources: bool) -> None:
    """Delete the benchmark queue unless the caller asked to retain it."""

    try:
        if not keep_resources:
            runtime.client.delete_queue(runtime.queue_name)
    finally:
        close_rabbitmq_client(runtime.client)


def create_local_runtime(config: BenchSuiteConfig) -> LocalRuntime:
    """Create an isolated Local backend for the smoke benchmark."""

    root = Path(mkdtemp(prefix="mindtrace-jobs-bench-"))
    client = LocalClient(client_dir=root)
    queue_name = queue_name_for(config, "local")
    client.declare_queue(queue_name)
    return LocalRuntime(client=client, orchestrator=Orchestrator(client), queue_name=queue_name, root=root)


def cleanup_local_runtime(runtime: LocalRuntime, *, keep_resources: bool) -> None:
    """Remove the Local benchmark directory unless retention was requested."""

    if not keep_resources:
        rmtree(runtime.root, ignore_errors=True)


def close_rabbitmq_client(client: RabbitMQClient) -> None:
    """Close persistent resources retained by a RabbitMQ client."""

    channel = getattr(client, "_channel", None)
    if channel is not None and getattr(channel, "is_open", False):
        channel.close()
    connection = getattr(client, "_connection", None)
    if connection is not None:
        connection.close()


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
        make_job(queue_name, sequence=start + offset, payload=payload, sent_at_ns=sent_at_ns)
        for offset in range(count)
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
