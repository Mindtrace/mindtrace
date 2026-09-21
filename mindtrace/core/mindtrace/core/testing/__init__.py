"""Bench / stress-suite registry primitives shipped with ``mindtrace-core``."""

from __future__ import annotations

from mindtrace.core.testing.bench_framework import (
    BenchReporter,
    BenchResult,
    BenchResultSchema,
    BenchSuiteConfig,
    CancellationToken,
    latency_summary,
    utcnow_iso,
)
from mindtrace.core.testing.bench_suite import BenchTestSuite, build_bench_suite_config, coerce_bench_config
from mindtrace.core.testing.matrix import expand_param_matrix
from mindtrace.core.testing.minio import (
    TEST_STACK_MINIO_ENDPOINT,
    TEST_STACK_MINIO_RESOURCES,
    MinioBenchResources,
    ResolvedMinioBenchConnection,
    resolve_minio_bench_connection,
)
from mindtrace.core.testing.runner import TestRunner
from mindtrace.core.testing.test_suite import TestSuite
from mindtrace.core.testing.types import (
    OverallStatus,
    ProgressEvent,
    RunOutcome,
    SuiteContribution,
    SuiteExecutionResult,
    SuiteRun,
    SuiteSchema,
    UnknownSuiteIdError,
    validate_suite_id,
)
from mindtrace.core.testing.workloads import deterministic_payload, parse_size_bytes, run_threaded_until_deadline

__all__ = [
    "BenchReporter",
    "BenchResult",
    "BenchResultSchema",
    "BenchSuiteConfig",
    "BenchTestSuite",
    "CancellationToken",
    "OverallStatus",
    "ProgressEvent",
    "RunOutcome",
    "SuiteContribution",
    "SuiteExecutionResult",
    "SuiteRun",
    "SuiteSchema",
    "TestRunner",
    "TestSuite",
    "UnknownSuiteIdError",
    "build_bench_suite_config",
    "coerce_bench_config",
    "deterministic_payload",
    "expand_param_matrix",
    "MinioBenchResources",
    "ResolvedMinioBenchConnection",
    "TEST_STACK_MINIO_ENDPOINT",
    "TEST_STACK_MINIO_RESOURCES",
    "resolve_minio_bench_connection",
    "latency_summary",
    "parse_size_bytes",
    "run_threaded_until_deadline",
    "utcnow_iso",
    "validate_suite_id",
]
