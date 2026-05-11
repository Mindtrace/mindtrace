"""Small framework primitives for fixed-duration stress suites.

The runner owns discovery, selection, output directories, and progress display.
Suites own workload setup/cleanup and report benchmark events through
:class:`StressReporter`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import median, quantiles
from time import perf_counter
from typing import Any, TextIO


def utc_now_iso() -> str:
    """Return a stable UTC timestamp for result files."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class StressSuiteConfig:
    """Resolved configuration passed to an individual stress suite."""

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


@dataclass
class StressResult:
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
        """Serialize the result with common aggregate metrics."""

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


def latency_summary(samples: list[float]) -> dict[str, float | None]:
    """Return p50/p95/p99 latency metrics for a list of second-based samples."""

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


class StressReporter:
    """Record suite events and metrics as JSONL-compatible dictionaries."""

    def __init__(self, suite_id: str, events_file: TextIO | None = None, error_file: TextIO | None = None):
        self.suite_id = suite_id
        self.events_file = events_file
        self.error_file = error_file
        self.operations = 0
        self.successes = 0
        self.failures = 0
        self.bytes_processed = 0
        self.latency_seconds: list[float] = []
        self.error_counts: dict[str, int] = {}
        self.metrics: dict[str, Any] = {}

    def event(self, event_type: str, **fields: Any) -> None:
        """Write an event to the JSONL stream when one is configured."""

        if self.events_file is None:
            return
        import json

        payload = {"timestamp": utc_now_iso(), "suite_id": self.suite_id, "event": event_type, **fields}
        self.events_file.write(json.dumps(payload, default=str) + "\n")
        self.events_file.flush()

    def error(self, error: BaseException, **fields: Any) -> None:
        """Write a failure event to the dedicated run-level error log."""

        if self.error_file is None:
            return
        import json

        payload = {
            "timestamp": utc_now_iso(),
            "suite_id": self.suite_id,
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
        """Record one measured operation."""

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
        """Return a monotonic deadline for duration-based measurement loops."""

        return perf_counter() + max(duration_seconds, 0.0)
