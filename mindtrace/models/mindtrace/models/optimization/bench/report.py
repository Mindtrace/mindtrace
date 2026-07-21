"""Benchmark result container and rendering utilities.

Defines :class:`BenchmarkReport`, the immutable result record produced by
:class:`mindtrace.models.optimization.bench.Benchmark`.  A report can render
itself as an aligned monospace table, serialize to a plain dict, log its
metrics to any :class:`mindtrace.models.tracking.Tracker`-compatible object,
and be compared side by side with other reports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

_METRIC_ROWS: tuple[tuple[str, str], ...] = (
    ("p50_ms", "p50 (ms)"),
    ("p95_ms", "p95 (ms)"),
    ("mean_ms", "mean (ms)"),
    ("fps", "fps"),
    ("cold_start_ms", "cold start (ms)"),
    ("size_mb", "size (MB)"),
    ("peak_rss_mb", "peak RSS (MB)"),
    ("iterations", "iterations"),
    ("sustained", "sustained"),
)


def _fmt(value: Any) -> str:
    """Format a metric value for table rendering.

    Args:
        value: Metric value (float, int, bool, or ``None``).

    Returns:
        Human-readable string; ``"n/a"`` for ``None``.
    """
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


@dataclass
class BenchmarkReport:
    """Result of a single benchmark run.

    Attributes:
        runtime: Runtime that was benchmarked (``"torch"``, ``"onnxruntime"``,
            ``"openvino"``, or ``"callable"``).
        artifact: Human-readable identifier of the benchmarked artifact
            (file path, module class name, or callable name).
        input_shape: Input tensor shape used for inference.
        p50_ms: Median per-inference latency in milliseconds.
        p95_ms: 95th-percentile per-inference latency in milliseconds.
        mean_ms: Mean per-inference latency in milliseconds.
        fps: Throughput in inferences per second (``1000 / mean_ms``).
        size_mb: Artifact size in megabytes, or ``None`` when the artifact
            has no measurable size (e.g. a plain callable).
        peak_rss_mb: Peak resident set size of the process in megabytes.
        cold_start_ms: Time to build the session and run the first
            inference, in milliseconds.
        iterations: Number of timed iterations actually executed.
        sustained: ``True`` when the run timed for a wall-clock duration
            rather than a fixed iteration count.
        meta: Extra run metadata (device, dtype, warmup count, providers...).
    """

    runtime: str
    artifact: str
    input_shape: tuple
    p50_ms: float
    p95_ms: float
    mean_ms: float
    fps: float
    size_mb: float | None
    peak_rss_mb: float
    cold_start_ms: float
    iterations: int
    sustained: bool
    meta: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def table(self) -> str:
        """Render the report as an aligned monospace metric table.

        Returns:
            Multi-line string with one ``label  value`` row per metric.
        """
        rows: list[tuple[str, str]] = [
            ("runtime", self.runtime),
            ("artifact", self.artifact),
            ("input shape", str(tuple(self.input_shape))),
        ]
        rows.extend((label, _fmt(getattr(self, name))) for name, label in _METRIC_ROWS)

        label_w = max(len(label) for label, _ in rows)
        value_w = max(len(value) for _, value in rows)
        sep = "-" * (label_w + 2 + value_w)
        lines = [f"{label:<{label_w}}  {value:>{value_w}}" for label, value in rows]
        return "\n".join(["Benchmark Report", sep, *lines])

    def to_dict(self) -> dict:
        """Serialize the report to a plain dictionary.

        Returns:
            Dict with all dataclass fields; ``input_shape`` is kept as a
            tuple and ``meta`` is shallow-copied.
        """
        data = asdict(self)
        data["input_shape"] = tuple(self.input_shape)
        return data

    # ------------------------------------------------------------------
    # Tracker integration
    # ------------------------------------------------------------------

    def log_to(self, tracker: Any, step: int | None = None) -> None:
        """Log the numeric metrics to an experiment tracker.

        The tracker is duck-typed against
        :class:`mindtrace.models.tracking.Tracker`: it only needs a
        ``log(metrics: dict, step=...)`` method.  Metric keys are prefixed
        with ``"bench/"`` (e.g. ``"bench/p50_ms"``).  ``size_mb`` is omitted
        when it is ``None``.

        Args:
            tracker: Object exposing ``log(metrics, step=...)``.
            step: Optional global step to associate with the metrics.
        """
        metrics: dict[str, float] = {
            "bench/p50_ms": self.p50_ms,
            "bench/p95_ms": self.p95_ms,
            "bench/mean_ms": self.mean_ms,
            "bench/fps": self.fps,
            "bench/cold_start_ms": self.cold_start_ms,
            "bench/peak_rss_mb": self.peak_rss_mb,
            "bench/iterations": float(self.iterations),
        }
        if self.size_mb is not None:
            metrics["bench/size_mb"] = self.size_mb
        tracker.log(metrics, step=step)

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    @staticmethod
    def compare(reports: Iterable["BenchmarkReport"]) -> str:
        """Render multiple reports as a side-by-side variant table.

        Each report becomes one column; metric names label the rows.
        Duplicate runtime names are disambiguated with an index suffix.

        Args:
            reports: Reports to compare (at least one).

        Returns:
            Multi-line aligned monospace table string.

        Raises:
            ValueError: If ``reports`` is empty.
        """
        reports = list(reports)
        if not reports:
            raise ValueError("BenchmarkReport.compare requires at least one report.")

        headers = ["metric"]
        seen: dict[str, int] = {}
        for report in reports:
            seen[report.runtime] = seen.get(report.runtime, 0) + 1
            count = seen[report.runtime]
            headers.append(report.runtime if count == 1 else f"{report.runtime}#{count}")

        rows: list[list[str]] = [["input shape"] + [str(tuple(r.input_shape)) for r in reports]]
        rows.extend([label] + [_fmt(getattr(r, name)) for r in reports] for name, label in _METRIC_ROWS)

        widths = [len(header) for header in headers]
        for row in rows:
            for col, cell in enumerate(row):
                widths[col] = max(widths[col], len(cell))

        def render(cells: list[str]) -> str:
            first = f"{cells[0]:<{widths[0]}}"
            rest = [f"{cell:>{widths[i + 1]}}" for i, cell in enumerate(cells[1:])]
            return "  ".join([first, *rest])

        sep = "-" * len(render(headers))
        return "\n".join([render(headers), sep, *(render(row) for row in rows)])


__all__ = ["BenchmarkReport"]
