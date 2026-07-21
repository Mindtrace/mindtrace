"""Latency / memory / size benchmarking harness for edge deployment.

Public API:
    Benchmark       — run a model artifact under a chosen runtime and time it.
    BenchmarkReport — the resulting metrics record with table rendering,
                      tracker logging, and side-by-side comparison.
"""

from mindtrace.models.optimization.bench.benchmark import Benchmark
from mindtrace.models.optimization.bench.report import BenchmarkReport

__all__ = ["Benchmark", "BenchmarkReport"]
