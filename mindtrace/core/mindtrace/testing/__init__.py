"""Mindtrace test suite registry (class-level registration, no entry points)."""

from __future__ import annotations

from mindtrace.testing.runner import TestRunner
from mindtrace.testing.types import (
    ProgressEvent,
    RunOutcome,
    SuiteContribution,
    SuiteExecutionResult,
    SuiteRun,
    UnknownSuiteIdError,
    validate_suite_id,
)

__all__ = [
    "ProgressEvent",
    "RunOutcome",
    "SuiteContribution",
    "SuiteExecutionResult",
    "SuiteRun",
    "TestRunner",
    "UnknownSuiteIdError",
    "validate_suite_id",
]
