"""Stress-style suite discovery (setuptools plugins + explicit registration)."""

from __future__ import annotations

from mindtrace.testing.runner import (
    ENTRY_POINT_GROUP,
    TestRunner,
    default_test_runner,
    normalize_loader_payload,
    reset_default_test_runner,
)
from mindtrace.testing.types import (
    DuplicateSuiteIdError,
    PluginLoadError,
    ResolvedSuite,
    SuiteContribution,
    SuiteRun,
    UnknownSuiteIdError,
    validate_suite_id,
)

__all__ = [
    "DuplicateSuiteIdError",
    "ENTRY_POINT_GROUP",
    "PluginLoadError",
    "ResolvedSuite",
    "SuiteContribution",
    "SuiteRun",
    "TestRunner",
    "UnknownSuiteIdError",
    "default_test_runner",
    "normalize_loader_payload",
    "reset_default_test_runner",
    "validate_suite_id",
]
