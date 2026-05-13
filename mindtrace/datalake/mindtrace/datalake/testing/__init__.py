"""Embedded benchmark suites for ``mindtrace-datalake``.

Import this module (or run ``mindtrace-bench datalake``) to register workloads on
:class:`~mindtrace.core.TestRunner`.
"""

from __future__ import annotations

from mindtrace.core import TestRunner
from mindtrace.datalake.testing.bootstrap import prioritize_wheel_datalake_sources


def register_benchmark_suites(*, replace: bool = True) -> None:
    """Register datalake benchmark suites (idempotent; safe after ``TestRunner.clear_registry()``)."""

    prioritize_wheel_datalake_sources()

    from mindtrace.datalake.testing.suites.create_asset import DatalakeCreateAssetFromObjectSuite
    from mindtrace.datalake.testing.suites.mongo_insert import DatalakeMongoInsertCeilingSuite
    from mindtrace.datalake.testing.suites.payload_write import DatalakePayloadWriteCeilingSuite
    from mindtrace.datalake.testing.suites.smoke import DatalakeSmokeSuite

    for cls in (
        DatalakeSmokeSuite,
        DatalakePayloadWriteCeilingSuite,
        DatalakeMongoInsertCeilingSuite,
        DatalakeCreateAssetFromObjectSuite,
    ):
        if cls.suite_id not in TestRunner.registered_suites():
            TestRunner.register_test_suite(cls, replace=replace)


register_benchmark_suites()
