"""Embedded benchmark suites for ``mindtrace-jobs``.

Use :func:`register_benchmark_suites` directly or discover it through the
``mindtrace.benchmark_suites`` entry point group.
"""

from __future__ import annotations

from mindtrace.core import TestRunner


def register_benchmark_suites(*, runner: TestRunner | None = None, replace: bool = True) -> None:
    """Register Jobs benchmark suites on ``runner`` or the default runner."""

    from mindtrace.jobs.testing.suites import JOBS_BENCHMARK_SUITES

    target = runner or TestRunner.default()
    for suite_cls in JOBS_BENCHMARK_SUITES:
        if replace or suite_cls.suite_id not in target.registered_suites():
            target.register_test_suite(suite_cls, replace=replace)


__all__ = ["register_benchmark_suites"]
