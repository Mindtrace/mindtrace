"""Unit tests for the mindtrace.models.optimization.bench sub-package.

Covers:
- Benchmark with the "torch" runtime (sane latency stats, table rendering)
- Benchmark with the "onnxruntime" runtime on a tiny inline-exported model
- Benchmark with the "callable" runtime (including sustained mode)
- BenchmarkReport.compare side-by-side rendering
- BenchmarkReport.log_to against a stub tracker
- Input validation errors
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
import torch.nn as nn

from mindtrace.models.optimization.bench import Benchmark, BenchmarkReport


class TinyCNN(nn.Module):
    """Minimal convolutional model for fast CPU benchmarking."""

    def __init__(self) -> None:
        super().__init__()
        self.conv = nn.Conv2d(1, 2, kernel_size=3, padding=1)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Linear(2, 3)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.pool(torch.relu(self.conv(x)))
        return self.fc(x.flatten(1))


def _make_report(runtime: str = "torch", p50: float = 1.0) -> BenchmarkReport:
    """Build a synthetic report without running a benchmark."""
    return BenchmarkReport(
        runtime=runtime,
        artifact="TinyCNN",
        input_shape=(1, 1, 8, 8),
        p50_ms=p50,
        p95_ms=p50 * 2,
        mean_ms=p50 * 1.5,
        fps=1000.0 / (p50 * 1.5),
        size_mb=0.5,
        peak_rss_mb=100.0,
        cold_start_ms=10.0,
        iterations=20,
        sustained=False,
        meta={"device": "cpu"},
    )


class TestTorchRuntime:
    def test_torch_runtime_sane_report(self) -> None:
        report = Benchmark(
            runtime="torch",
            artifact=TinyCNN(),
            input_shape=(1, 1, 8, 8),
            warmup=2,
            iterations=15,
        ).run()

        assert report.runtime == "torch"
        assert report.artifact == "TinyCNN"
        assert report.input_shape == (1, 1, 8, 8)
        assert report.iterations == 15
        assert report.sustained is False
        assert 0 < report.p50_ms <= report.p95_ms
        assert report.mean_ms > 0
        assert report.fps > 0
        assert report.cold_start_ms > 0
        assert report.peak_rss_mb > 0
        assert report.size_mb is not None and report.size_mb > 0

        table = report.table()
        assert "p50" in table
        assert "torch" in table

    def test_to_dict_round_trip(self) -> None:
        report = _make_report()
        data = report.to_dict()
        assert data["runtime"] == "torch"
        assert data["input_shape"] == (1, 1, 8, 8)
        assert data["p50_ms"] == report.p50_ms
        assert data["meta"] == {"device": "cpu"}


class TestOnnxRuntime:
    def test_onnxruntime_runtime(self, tmp_path: Path) -> None:
        onnx_path = tmp_path / "tiny.onnx"
        model = TinyCNN().eval()
        torch.onnx.export(
            model,
            (torch.rand(1, 1, 8, 8),),
            str(onnx_path),
            input_names=["input"],
            output_names=["output"],
            dynamo=False,  # Legacy exporter: no onnxscript dependency.
        )
        assert onnx_path.exists()

        report = Benchmark(
            runtime="onnxruntime",
            artifact=str(onnx_path),
            input_shape=(1, 1, 8, 8),
            warmup=2,
            iterations=10,
        ).run()

        assert report.runtime == "onnxruntime"
        assert report.iterations == 10
        assert 0 < report.p50_ms <= report.p95_ms
        assert report.fps > 0
        assert report.size_mb is not None and report.size_mb > 0


class TestCallableRuntime:
    def test_callable_runtime(self) -> None:
        def double(x: np.ndarray) -> np.ndarray:
            return x * 2.0

        report = Benchmark(
            runtime="callable",
            artifact=double,
            input_shape=(4, 4),
            warmup=1,
            iterations=10,
        ).run()

        assert report.runtime == "callable"
        assert report.artifact == "double"
        assert report.size_mb is None
        assert report.iterations == 10
        assert report.p50_ms <= report.p95_ms
        assert report.fps > 0

    def test_callable_runtime_sustained(self) -> None:
        import time as time_module

        def slow_call(x):
            time_module.sleep(0.005)
            return x

        report = Benchmark(
            runtime="callable",
            artifact=slow_call,
            input_shape=(2, 2),
            warmup=0,
            iterations=3,  # decoy: sustained mode must ignore the fixed count
            sustained_seconds=0.1,
        ).run()

        assert report.sustained is True
        assert report.iterations != 3  # deadline loop ran, not the decoy count
        assert report.iterations >= 10  # ~0.1s / 5ms per call
        # The measured window roughly covers the sustained duration.
        assert report.iterations * report.mean_ms == pytest.approx(100.0, rel=0.8)

    def test_peak_rss_is_per_run_not_lifetime(self) -> None:
        import resource as resource_module

        import numpy as np_module

        # Inflate the process lifetime RSS peak by 512 MB, then free it
        # (large allocations are mmap-backed and returned to the OS on del).
        ballast = np_module.ones((512, 1024, 1024), dtype=np_module.uint8)
        assert ballast[0, 0, 0] == 1  # touch so pages are resident
        del ballast
        lifetime_peak_mb = resource_module.getrusage(resource_module.RUSAGE_SELF).ru_maxrss / 1024.0

        report = Benchmark(
            runtime="callable",
            artifact=lambda x: x,
            input_shape=(2, 2),
            warmup=0,
            iterations=5,
        ).run()

        if report.meta["rss_method"] == "statm":
            # Per-run RSS must sit well below the ballast-inflated lifetime
            # peak (the old ru_maxrss implementation reported exactly it).
            assert report.peak_rss_mb < lifetime_peak_mb - 300
        else:  # non-linux fallback keeps the old semantics
            assert report.peak_rss_mb > 0


class TestReportRendering:
    def test_compare_side_by_side(self) -> None:
        a = _make_report("torch", p50=1.0)
        b = _make_report("onnxruntime", p50=0.5)
        text = BenchmarkReport.compare([a, b])

        header = text.splitlines()[0]
        assert "torch" in header
        assert "onnxruntime" in header
        p50_lines = [line for line in text.splitlines() if line.startswith("p50")]
        assert len(p50_lines) == 1
        assert "1.000" in p50_lines[0]
        assert "0.500" in p50_lines[0]

    def test_compare_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one report"):
            BenchmarkReport.compare([])


class TestTrackerLogging:
    def test_log_to_stub_tracker(self) -> None:
        class StubTracker:
            def __init__(self) -> None:
                self.calls: list[tuple[dict, Any]] = []

            def log(self, metrics: dict, step: int | None = None) -> None:
                self.calls.append((metrics, step))

        tracker = StubTracker()
        _make_report().log_to(tracker, step=7)

        assert len(tracker.calls) == 1
        metrics, step = tracker.calls[0]
        assert step == 7
        for key in (
            "bench/p50_ms",
            "bench/p95_ms",
            "bench/mean_ms",
            "bench/fps",
            "bench/cold_start_ms",
            "bench/peak_rss_mb",
            "bench/size_mb",
        ):
            assert key in metrics
        assert metrics["bench/p50_ms"] == 1.0

    def test_log_to_omits_none_size(self) -> None:
        report = _make_report()
        report.size_mb = None

        class StubTracker:
            def __init__(self) -> None:
                self.metrics: dict = {}

            def log(self, metrics: dict, step: int | None = None) -> None:
                self.metrics = metrics

        tracker = StubTracker()
        report.log_to(tracker)
        assert "bench/size_mb" not in tracker.metrics


class TestValidation:
    def test_unknown_runtime_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown runtime"):
            Benchmark(runtime="tensorrt", artifact=lambda x: x, input_shape=(1,))

    def test_torch_runtime_requires_module(self) -> None:
        bench = Benchmark(runtime="torch", artifact="not_a_module", input_shape=(1,), warmup=0, iterations=1)
        with pytest.raises(ValueError, match="nn.Module"):
            bench.run()
