"""Stress runner compatibility shim — canonical implementations live in ``mindtrace-core``."""

from __future__ import annotations

from mindtrace.core.testing.bench_framework import (
    BenchReporter as StressReporter,
)
from mindtrace.core.testing.bench_framework import (
    BenchResult as StressResult,
)
from mindtrace.core.testing.bench_framework import (
    BenchSuiteConfig as StressSuiteConfig,
)
from mindtrace.core.testing.bench_framework import (
    CancellationToken,
    latency_summary,
    utc_now_iso,
)

__all__ = [
    "CancellationToken",
    "StressReporter",
    "StressResult",
    "StressSuiteConfig",
    "latency_summary",
    "utc_now_iso",
]
