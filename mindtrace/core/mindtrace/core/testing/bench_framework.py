"""Primitives for timed benchmark suites embedded in Mindtrace libraries.

Runners own discovery and aggregation; suites measure operations via :class:`BenchReporter`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import median, quantiles
from time import perf_counter
from typing import Any, Callable, Protocol, TextIO

from pydantic import BaseModel, Field


class CancellationToken(Protocol):
    """Minimal protocol for cooperative cancellation."""

    def is_cancelled(self) -> bool: ...


def utc_now_iso() -> str:
    """Return a stable UTC timestamp for result payloads."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class BenchSuiteConfig:
    """Resolved configuration passed to one benchmark suite invocation."""

    suite_id: str
    label: str
    profile: str
    duration_seconds: float
    warmup_seconds: float = 0.0
    cooldown_seconds: float = 0.0
    parameters: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)
    output_dir: Path = Path(".stress-results")
    run_id: str = "local"
    keep_resources: bool = False
    variant_id: str | None = None
    base_suite_id: str | None = None
    requires: list[str] = field(default_factory=list)
    safety: str | None = None
    cancellation_token: CancellationToken | None = None

    def is_cancelled(self) -> bool:
        return bool(self.cancellation_token and self.cancellation_token.is_cancelled())


@dataclass
class BenchResult:
    """Final summary for one suite."""

    suite_id: str
    status: str
    started_at: str
    ended_at: str
    duration_seconds: float
    operations: int = 0
    successes: int = 0
    failures: int = 0
    bytes_processed: int = 0
    latency_seconds: list[float] = field(default_factory=list)
    error_counts: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result with aggregate throughput metrics."""

        throughput_ops = self.operations / self.duration_seconds if self.duration_seconds > 0 else 0.0
        throughput_bytes = self.bytes_processed / self.duration_seconds if self.duration_seconds > 0 else 0.0
        payload: dict[str, Any] = {
            "suite_id": self.suite_id,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "operations": self.operations,
            "successes": self.successes,
            "failures": self.failures,
            "bytes_processed": self.bytes_processed,
            "throughput_ops_per_second": throughput_ops,
            "throughput_bytes_per_second": throughput_bytes,
            "error_counts": self.error_counts,
            "metrics": self.metrics,
            "artifacts": self.artifacts,
        }
        payload.update(latency_summary(self.latency_seconds))
        return payload


class BenchResultSchema(BaseModel):
    """Pydantic output contract for serialized benchmark results."""

    suite_id: str
    status: str
    started_at: str
    ended_at: str
    duration_seconds: float
    operations: int = 0
    successes: int = 0
    failures: int = 0
    bytes_processed: int = 0
    throughput_ops_per_second: float | None = None
    throughput_bytes_per_second: float | None = None
    latency_p50_seconds: float | None = None
    latency_p95_seconds: float | None = None
    latency_p99_seconds: float | None = None
    error_counts: dict[str, int] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)


def latency_summary(samples: list[float]) -> dict[str, float | None]:
    """Return p50/p95/p99 latency metrics for second-based samples."""

    if not samples:
        return {"latency_p50_seconds": None, "latency_p95_seconds": None, "latency_p99_seconds": None}

    ordered = sorted(samples)
    if len(ordered) == 1:
        p50 = p95 = p99 = ordered[0]
    else:
        p50 = median(ordered)
        percentile_values = quantiles(ordered, n=100, method="inclusive")
        p95 = percentile_values[94]
        p99 = percentile_values[98]
    return {"latency_p50_seconds": p50, "latency_p95_seconds": p95, "latency_p99_seconds": p99}


class BenchReporter:
    """Record suite events and per-operation latency."""

    def __init__(
        self,
        suite_id: str,
        events_file: TextIO | None = None,
        error_file: TextIO | None = None,
        *,
        run_id: str | None = None,
        variant_id: str | None = None,
        event_sink: Callable[[str, dict[str, Any]], None] | None = None,
        cancellation_token: CancellationToken | None = None,
    ):
        self.suite_id = suite_id
        self.variant_id = variant_id or suite_id
        self.run_id = run_id
        self.events_file = events_file
        self.error_file = error_file
        self.event_sink = event_sink
        self.cancellation_token = cancellation_token
        self.operations = 0
        self.successes = 0
        self.failures = 0
        self.bytes_processed = 0
        self.latency_seconds: list[float] = []
        self.error_counts: dict[str, int] = {}
        self.metrics: dict[str, Any] = {}

    def is_cancelled(self) -> bool:
        return bool(self.cancellation_token and self.cancellation_token.is_cancelled())

    def event(self, event_type: str, **fields: Any) -> None:
        import json

        payload = {"timestamp": utc_now_iso(), "suite_id": self.suite_id, "event": event_type, **fields}
        if self.run_id:
            payload["run_id"] = self.run_id
        if self.variant_id:
            payload["variant_id"] = self.variant_id
        if self.events_file is not None:
            self.events_file.write(json.dumps(payload, default=str) + "\n")
            self.events_file.flush()
        if self.event_sink is not None:
            sink_payload = dict(fields)
            sink_payload.setdefault("suite_event", event_type)
            self.event_sink(event_type, sink_payload)

    def error(self, error: BaseException, **fields: Any) -> None:
        if self.error_file is None:
            return
        import json

        payload = {
            "timestamp": utc_now_iso(),
            "suite_id": self.suite_id,
            "variant_id": self.variant_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
            **fields,
        }
        self.error_file.write(json.dumps(payload, default=str) + "\n")
        self.error_file.flush()

    def record_operation(
        self,
        *,
        success: bool,
        latency_seconds: float,
        bytes_processed: int = 0,
        error: BaseException | None = None,
        **metrics: Any,
    ) -> None:
        self.operations += 1
        self.bytes_processed += bytes_processed
        self.latency_seconds.append(latency_seconds)
        self.metrics.update(metrics)
        if success:
            self.successes += 1
        else:
            self.failures += 1
            if error is not None:
                key = type(error).__name__
                self.error_counts[key] = self.error_counts.get(key, 0) + 1
                self.error(error, latency_seconds=latency_seconds, bytes_processed=bytes_processed, metrics=metrics)
        self.event(
            "operation",
            success=success,
            latency_seconds=latency_seconds,
            bytes_processed=bytes_processed,
            error_type=type(error).__name__ if error else None,
            error_message=str(error) if error else None,
            metrics=metrics,
        )

    def set_metric(self, key: str, value: Any) -> None:
        self.metrics[key] = value
        self.event("metric", key=key, value=value)

    def deadline(self, duration_seconds: float) -> float:
        return perf_counter() + max(duration_seconds, 0.0)
