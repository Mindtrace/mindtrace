"""Bench / stress-suite registry primitives shipped with ``mindtrace-core``."""

from __future__ import annotations

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

__all__ = [
    "OverallStatus",
    "ProgressEvent",
    "RunOutcome",
    "SuiteContribution",
    "SuiteExecutionResult",
    "SuiteRun",
    "TestRunner",
    "TestSuite",
    "UnknownSuiteIdError",
    "validate_suite_id",
]
