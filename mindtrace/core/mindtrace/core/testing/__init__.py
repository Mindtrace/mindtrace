"""Bench / stress-suite registry primitives shipped with ``mindtrace-core``."""

from __future__ import annotations

from mindtrace.core.testing.bench_framework import (
    BenchReporter,
    BenchResult,
    BenchSuiteConfig,
    CancellationToken,
    latency_summary,
    utc_now_iso,
)
from mindtrace.core.testing.bench_suite import BenchTestSuite, build_bench_suite_config, coerce_bench_config
from mindtrace.core.testing.driver import bench_execution_wrapper, run_registered_benches, suite_ids_for_profile
from mindtrace.core.testing.matrix import expand_param_matrix
from mindtrace.core.testing.runner import TestRunner
from mindtrace.core.testing.test_suite import TestSuite
from mindtrace.core.testing.types import (
    OverallStatus,
    ProgressEvent,
    RunOutcome,
    SuiteContribution,
    SuiteExecutionResult,
    SuiteRun,
    UnknownSuiteIdError,
    validate_suite_id,
)
from mindtrace.core.testing.workloads import deterministic_payload, parse_size_bytes, run_threaded_until_deadline

__all__ = [
    "BenchReporter",
    "BenchResult",
    "BenchSuiteConfig",
    "BenchTestSuite",
    "CancellationToken",
    "OverallStatus",
    "ProgressEvent",
    "RunOutcome",
    "SuiteContribution",
    "SuiteExecutionResult",
    "SuiteRun",
    "TestRunner",
    "TestSuite",
    "UnknownSuiteIdError",
    "bench_execution_wrapper",
    "build_bench_suite_config",
    "coerce_bench_config",
    "deterministic_payload",
    "expand_param_matrix",
    "latency_summary",
    "parse_size_bytes",
    "run_registered_benches",
    "run_threaded_until_deadline",
    "suite_ids_for_profile",
    "utc_now_iso",
    "validate_suite_id",
]
